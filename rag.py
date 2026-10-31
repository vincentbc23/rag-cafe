"""
RAG completo: busca híbrida + Qwen3.5-4B (4-bit, SGLang) -> resposta pronta para o bot de WhatsApp.

Como a resposta é montada:
  1. A busca híbrida recupera os K melhores fornecedores (busca.py).
  2. O LLM recebe só dados PÚBLICOS (sem telefone) e devolve JSON com formato garantido pelo SGLang
     (response_format json_schema): uma introdução curta e quais fornecedores recomendar (até 3), com o motivo.
  3. O código monta a mensagem final com os fatos vindos do BANCO (nome, cidade, avaliação, preço),
     não do LLM, então o modelo não tem como inventar preço ou avaliação. Cada fornecedor recomendado
     vira um botão "falar com o fornecedor", cujo id carrega o id do fornecedor.
  4. O telefone nunca sai do servidor: o contato acontece mediado pelo próprio bot.

Uso:
    python rag.py                                         # modo conversa
    python rag.py "preciso podar meu café em Varginha"    # prévia da mensagem + botões
    python rag.py "adubo no sul de minas" --whatsapp      # payload JSON da WhatsApp Cloud API
    JSON_SCHEMA=0 python rag.py "..."                     # sem json_schema (JSON pedido só pelo prompt)
"""
import argparse
import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass, field

from openai import APIConnectionError, OpenAI

from busca import Buscador, fmt_preco, montar_contexto

LLM_URL = os.getenv("LLM_URL", "http://127.0.0.1:30000/v1")
LLM_MODELO = os.getenv("LLM_MODELO", "qwen3.5-4b")   # = --served-model-name do servir_llm.sh
K_CONTEXTO = 5
# 1 = saída JSON garantida pelo SGLang (xgrammar). 0 = JSON pedido só pelo prompt e extraído do texto.
USAR_JSON_SCHEMA = os.getenv("JSON_SCHEMA", "1") != "0"
MAX_RECOMENDACOES = 3                                # limite de botões da WhatsApp Cloud API

GERACAO = dict(temperature=0.3, top_p=0.8, presence_penalty=1.0, max_tokens=600)
GERACAO_EXTRA = {"top_k": 20, "chat_template_kwargs": {"enable_thinking": False}}

# Campos que podem sair do servidor. Telefone (e qualquer contato) fica de fora de propósito.
CAMPOS_PUBLICOS = ("id", "nome", "tipo", "tipo_cadastro", "categoria", "natureza", "especialidades",
                   "avaliacao", "total_avaliacoes", "preco_medio", "unidade_preco", "cidade_sede", "uf",
                   "regiao", "abrangencia", "cidades_atendidas", "raio_atendimento_km", "anos_experiencia",
                   "certificacoes", "disponibilidade", "fora_da_area")

ESQUEMA = {
    "type": "object",
    "properties": {
        "introducao": {"type": "string", "maxLength": 300},
        "recomendacoes": {
            "type": "array",
            "maxItems": MAX_RECOMENDACOES,
            "items": {
                "type": "object",
                "properties": {
                    "fornecedor": {"type": "integer", "minimum": 1, "maximum": K_CONTEXTO},
                    "motivo": {"type": "string", "maxLength": 200},
                },
                "required": ["fornecedor", "motivo"],
            },
        },
    },
    "required": ["introducao", "recomendacoes"],
}

SISTEMA = """Você é o assistente de uma plataforma que conecta cafeicultores a prestadores de serviço e vendedores de produtos rurais. A conversa acontece no WhatsApp.

Responda SOMENTE com JSON no formato pedido:
- "introducao": 1 ou 2 frases curtas, em português do Brasil, respondendo ao pedido do usuário.
- "recomendacoes": até 3 fornecedores, do mais indicado para o menos indicado. "fornecedor" é o número entre colchetes na lista FORNECEDORES. "motivo" é 1 frase curta dizendo por que ele serve para ESTE pedido.

Regras:
1. Recomende SOMENTE fornecedores da lista. Ignore os que não têm relação com o pedido.
2. Não escreva cidade, preço, avaliação nem contato: o sistema acrescenta esses dados sozinho.
3. Se um fornecedor recomendado estiver FORA da área pedida, diga isso no motivo.
4. Se nenhum fornecedor servir, devolva "recomendacoes" vazio e explique na introdução que não encontrou ninguém adequado.
5. O usuário vai conversar com o fornecedor pelos botões da própria plataforma. Nunca peça para ele ligar ou procurar o contato."""


@dataclass
class Botao:
    id: str              # "contatar:<id do fornecedor>" -> o webhook do bot usa isso para abrir a conversa
    titulo: str          # até 20 caracteres (limite do WhatsApp)
    fornecedor_id: int


@dataclass
class RespostaBot:
    texto: str
    botoes: list = field(default_factory=list)
    fornecedores: list = field(default_factory=list)    # só campos públicos

    def para_whatsapp(self, destinatario):
        """Payload da WhatsApp Cloud API (mensagem interativa com botões de resposta)."""
        if not self.botoes:
            return {"messaging_product": "whatsapp", "recipient_type": "individual", "to": destinatario,
                    "type": "text", "text": {"body": self.texto[:4096]}}
        return {
            "messaging_product": "whatsapp", "recipient_type": "individual", "to": destinatario,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": self.texto[:1024]},
                "footer": {"text": "Toque para conversar pelo bot"},
                "action": {"buttons": [{"type": "reply", "reply": {"id": b.id, "title": b.titulo}}
                                       for b in self.botoes]},
            },
        }


def extrair_json(texto):
    """Lê o JSON da resposta; tolera cercas ```json e texto em volta (modo sem json_schema)."""
    texto = (texto or "").strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        ini, fim = texto.find("{"), texto.rfind("}")
        if ini == -1 or fim <= ini:
            raise
        return json.loads(texto[ini:fim + 1])


def dados_publicos(r):
    return {c: r[c] for c in CAMPOS_PUBLICOS if c in r}


def fornecedor_do_botao(botao_id):
    """Converte o id do botão clicado (vindo do webhook) no id do fornecedor. None se não for desse tipo."""
    prefixo, _, resto = botao_id.partition(":")
    return int(resto) if prefixo == "contatar" and resto.isdigit() else None


def _titulo_botao(n, nome):
    titulo = f"{n}. {nome}"
    return titulo if len(titulo) <= 20 else titulo[:19] + "…"


def montar_texto(introducao, escolhidos):
    """Monta o corpo da mensagem com os fatos do banco. Formatação de WhatsApp (*negrito*, _itálico_)."""
    linhas = [introducao.strip()]
    for n, (r, motivo) in enumerate(escolhidos, 1):
        linhas.append("")
        linhas.append(f"*{n}. {r['nome']}* — {r['tipo']}")
        linhas.append(f"📍 {r['cidade_sede']}/{r['uf']} · ⭐ {r['avaliacao']} ({r['total_avaliacoes']}) · "
                      f"💰 {fmt_preco(r)}")
        if r["fora_da_area"]:
            linhas.append("⚠️ Fica fora da região que você pediu")
        linhas.append(f"_{motivo.strip()}_")
    return "\n".join(linhas)


class RAG:
    def __init__(self, db="fornecedores_cafe.db"):
        self.buscador = Buscador(db)
        self.llm = OpenAI(base_url=LLM_URL, api_key=os.getenv("SGLANG_API_KEY", "EMPTY"))

    def _chamar_llm(self, pergunta, resultados):
        usuario = f"PERGUNTA DO USUÁRIO: {pergunta}\n\nFORNECEDORES:\n{montar_contexto(resultados)}"
        extra = {}
        if USAR_JSON_SCHEMA:
            extra["response_format"] = {"type": "json_schema",
                                        "json_schema": {"name": "resposta_rag", "schema": ESQUEMA}}
        else:
            usuario += ('\n\nResponda apenas com JSON, sem texto fora dele, no formato: '
                        '{"introducao": "...", "recomendacoes": [{"fornecedor": 1, "motivo": "..."}]}')
        resp = self.llm.chat.completions.create(
            model=LLM_MODELO,
            messages=[{"role": "system", "content": SISTEMA}, {"role": "user", "content": usuario}],
            extra_body=GERACAO_EXTRA, **extra, **GERACAO)
        return extrair_json(resp.choices[0].message.content)

    def responder(self, pergunta, k=K_CONTEXTO, estrito=False):
        _, resultados = self.buscador.buscar(pergunta, k, estrito=estrito)
        if not resultados:
            return RespostaBot("Não encontrei fornecedores para essa região. Pode me dizer outra cidade ou região?"), []

        try:
            saida = self._chamar_llm(pergunta, resultados)
        except (json.JSONDecodeError, KeyError, TypeError):
            saida = {"introducao": "", "recomendacoes": []}

        escolhidos, vistos = [], set()
        for rec in saida.get("recomendacoes", []):
            n = rec.get("fornecedor")
            if isinstance(n, int) and 1 <= n <= len(resultados) and n not in vistos:
                vistos.add(n)
                escolhidos.append((resultados[n - 1], rec.get("motivo", "")))
            if len(escolhidos) == MAX_RECOMENDACOES:
                break

        intro = saida.get("introducao") or ""
        if not escolhidos:
            intro = intro or ("Não encontrei um fornecedor adequado para esse pedido. "
                              "Pode me dar mais detalhes do que precisa?")
            return RespostaBot(intro), resultados

        botoes = [Botao(f"contatar:{r['id']}", _titulo_botao(n, r["nome"]), r["id"])
                  for n, (r, _) in enumerate(escolhidos, 1)]
        texto = montar_texto(intro or "Encontrei estas opções para você:", escolhidos)
        return RespostaBot(texto, botoes, [dados_publicos(r) for r, _ in escolhidos]), resultados


def mostrar_previa(resposta):
    print(resposta.texto)
    if resposta.botoes:
        print("\n" + "   ".join(f"[ {b.titulo} ]" for b in resposta.botoes))


def mostrar_fontes(resultados):
    print("\n--- Fornecedores recuperados pela busca ---")
    for n, r in enumerate(resultados, 1):
        fora = " ⚠ fora da área" if r["fora_da_area"] else ""
        print(f"[{n}] #{r['id']} {r['nome']} — {r['tipo']} | {r['cidade_sede']}/{r['uf']} | "
              f"★ {r['avaliacao']} | {fmt_preco(r)}{fora}")


def checar_servidores(db="fornecedores_cafe.db"):
    servidores = [("LLM", LLM_URL)]
    modelo_idx = sqlite3.connect(db).execute("SELECT modelo FROM embeddings LIMIT 1").fetchone()[0]
    if modelo_idx.startswith("sglang:"):
        servidores.append(("Embeddings", os.getenv("EMBED_URL", "http://127.0.0.1:30001/v1")))
    ok = True
    for nome, url in servidores:
        try:
            OpenAI(base_url=url, api_key="EMPTY", timeout=5, max_retries=0).models.list()
        except Exception as e:  # noqa: BLE001
            print(f"✗ Servidor de {nome} não respondeu em {url} ({type(e).__name__}).")
            ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pergunta", nargs="?")
    ap.add_argument("-k", type=int, default=K_CONTEXTO, help="fornecedores enviados ao LLM")
    ap.add_argument("--estrito", action="store_true", help="exclui quem não atende a localização")
    ap.add_argument("--fontes", action="store_true", help="mostra os fornecedores recuperados pela busca")
    ap.add_argument("--whatsapp", action="store_true", help="imprime o payload da WhatsApp Cloud API")
    args = ap.parse_args()

    if not checar_servidores():
        print("Suba o LLM com ./servir_llm.sh (veja o README).")
        sys.exit(1)

    print("Carregando o buscador e o modelo de embeddings...")
    rag = RAG()
    perguntas = [args.pergunta] if args.pergunta else None
    while True:
        if perguntas is not None:
            if not perguntas:
                break
            pergunta = perguntas.pop()
        else:
            try:
                pergunta = input("\nVocê: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if pergunta.lower() in {"sair", "exit", "quit"}:
                break
            if not pergunta:
                continue
        try:
            resposta, resultados = rag.responder(pergunta, args.k, args.estrito)
        except APIConnectionError:
            print(f"\n✗ O servidor do LLM caiu ou parou de responder ({LLM_URL}).")
            print("  Veja o erro no terminal do ./servir_llm.sh.")
            print("  Para testar sem a saída JSON garantida: JSON_SCHEMA=0 python rag.py ...")
            sys.exit(1)
        print()
        if args.whatsapp:
            print(json.dumps(resposta.para_whatsapp("<NUMERO_DO_USUARIO>"), ensure_ascii=False, indent=2))
        else:
            mostrar_previa(resposta)
        if args.fontes:
            mostrar_fontes(resultados)


if __name__ == "__main__":
    main()
