"""
Busca híbrida de fornecedores da cadeia do café.

Pipeline:
  1. Interpretação da pergunta (regras): extrai cidade / região / UF e se o usuário
     quer contratar serviço ou comprar produto.
  2. Filtro SQL: só fornecedores ativos que atendem a localização pedida
     (cidade atendida, mesma região/UF ou abrangência nacional).
  3. Busca lexical (FTS5 + BM25) e busca semântica (cosseno nos embeddings),
     ambas restritas aos candidatos do filtro.
  4. Fusão por Reciprocal Rank Fusion (RRF) + rerank com bônus de localização,
     avaliação (média bayesiana) e tipo de cadastro.

Uso:
    python busca.py "preciso de alguém para podar meu café em Varginha"
    python busca.py "onde compro adubo no sul de minas" -k 8 --json
"""
import argparse
import json
import re
import sqlite3
import unicodedata

import numpy as np

from embeddings import carregar_embedder

DB_PATH = "fornecedores_cafe.db"

# ---------------------------------------------------------------------------
# Pesos (ajuste aqui)
# ---------------------------------------------------------------------------
ALPHA_LEXICAL = 0.5          # relevância = ALPHA*lexical + (1-ALPHA)*semântica (ambas em 0..1)
PESO_TIPO = 0.75             # relevância final = PESO_TIPO*relevância do tipo + (1-PESO_TIPO)*a do registro
                             # (relevância do tipo = máxima entre os registros daquele tipo). Assim a pergunta
                             # decide QUAL tipo de fornecedor serve, e localização/avaliação decidem QUEM.
# nível de localização -> bônus
#   4 = atende a cidade/região/UF pedida | 3 = mesma região da cidade | 2 = mesma UF
#   1 = abrangência nacional            | 0 = fora da área (só aparece se for bem mais relevante)
BONUS_LOCAL = {4: 0.20, 3: 0.14, 2: 0.06, 1: 0.08, 0: -0.20}
BONUS_TIPO_CADASTRO = 0.08
BONUS_NOME_TIPO = 0.15
MAX_POR_TIPO = 3             # no máximo N resultados do mesmo tipo no top-k: garante alternativas ao LLM
                             # quando a pergunta é ambígua (ex.: "EPI para aplicação" -> loja de EPI x aplicador)       # termo da pergunta (ou sinônimo) aparece no NOME do tipo ("EPI", "poda", "crédito")
PESO_AVALIACAO = 0.10
BAYES_C = 15                 # "avaliações fantasma" da média bayesiana

# Sinônimos do domínio (chaves e valores sem acento, minúsculos)
SINONIMOS = {
    "adubo": ["fertilizante", "adubacao"], "adubar": ["adubacao", "fertilizante"],
    "fertilizante": ["adubo"], "agrotoxico": ["defensivo"], "agrotoxicos": ["defensivo"],
    "veneno": ["defensivo"], "colher": ["colheita", "colhedor"], "gente": ["turma"],
    "trabalhadores": ["turma"], "funcionarios": ["turma"], "podar": ["poda"],
    "consertar": ["manutencao", "conserto"], "conserto": ["manutencao"], "arrumar": ["manutencao"],
    "quebrou": ["manutencao"], "irrigar": ["irrigacao"], "financiamento": ["credito"],
    "emprestimo": ["credito"], "imposto": ["contabilidade", "renda"],
    "qualidade": ["classificacao", "sensorial", "prova"], "especial": ["especiais"],
    "provar": ["prova"], "nota": ["pontuacao"], "vender": ["venda", "intermediacao"],
    "secar": ["secagem", "secador"], "trator": ["tratores"], "mato": ["capina", "rocada"],
    "limpar": ["capina", "rocada"], "praga": ["pragas"], "doenca": ["doencas"],
    "analise": ["laboratorio"], "mudas": ["viveiro"], "muda": ["viveiro"], "plantar": ["plantio"],
    "ensacar": ["sacaria", "sacos"], "saco": ["sacaria"], "sacos": ["sacaria"],
    "torrar": ["torra", "torrefacao"], "certificado": ["certificacao"], "licenca": ["licenciamento"],
    "caminhao": ["frete", "transporte"], "levar": ["frete", "transporte"], "drone": ["drones"],
}

# ---------------------------------------------------------------------------
# Vocabulário para interpretar a pergunta
# ---------------------------------------------------------------------------
ALIAS_REGIAO = {
    "sul de minas": "Sul de Minas", "sul mineiro": "Sul de Minas",
    "cerrado mineiro": "Cerrado Mineiro", "cerrado": "Cerrado Mineiro",
    "triangulo mineiro": "Cerrado Mineiro", "alto paranaiba": "Cerrado Mineiro",
    "matas de minas": "Matas de Minas", "zona da mata": "Matas de Minas",
    "campo das vertentes": "Campo das Vertentes", "vertentes": "Campo das Vertentes",
    "mogiana": "Mogiana", "alta mogiana": "Mogiana", "media mogiana": "Mogiana",
    "montanhas do espirito santo": "Montanhas do Espírito Santo",
    "montanhas capixabas": "Montanhas do Espírito Santo",
    "norte do espirito santo": "Norte do Espírito Santo", "norte capixaba": "Norte do Espírito Santo",
    "chapada diamantina": "Chapada Diamantina", "chapada": "Chapada Diamantina",
    "oeste da bahia": "Oeste da Bahia", "oeste baiano": "Oeste da Bahia",
    "norte pioneiro": "Norte Pioneiro do Paraná",
    "matas de rondonia": "Matas de Rondônia",
}
NOMES_UF = {"minas gerais": "MG", "minas": "MG", "sao paulo": "SP", "espirito santo": "ES",
            "bahia": "BA", "parana": "PR", "rondonia": "RO"}

PISTAS_PRODUTO = ["comprar", "compro", "compra ", "loja", "revenda", "vende ", "vendem", "vendedor",
                  "adquirir", "preco de", "onde encontro", "fornecedor de"]
PISTAS_SERVICO = ["contratar", "contrato ", "servico", "prestador", "profissional", "alguem para",
                  "alguem pra", "mao de obra", "consultoria", "terceirizar", "diarista", "turma"]

STOPWORDS = set("""
a o as os um uma uns umas de do da dos das em no na nos nas por pelo pela para pra pro com sem
e ou que se me meu minha meus minhas eu nos voce voces ele ela seu sua isso esse essa este esta
ao aos como qual quais quem onde quando porque mais muito muita bem ja nao sim ter tenho tem
preciso precisando quero queria gostaria procuro procurando busco alguem algum alguma alguns
contratar comprar compro compra encontrar achar indicar indica indique recomenda recomendar
servico servicos produto produtos empresa empresas profissional profissionais fornecedor fornecedores
cafe cafes lavoura lavouras fazenda sitio propriedade produtor rural regiao cidade perto proximo
bom boa bons boas melhor melhores barato barata hectare hectares ha fazer faz ajudar ajuda
sou estou vou pode podem poderia algo coisa coisas ai la aqui
""".split())


def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def raiz(token):
    """Stemming simples por prefixo: 'podar'->'poda*', 'secador'->'seca*', 'colheita'->'colhe*'."""
    return token if len(token) < 5 else token[:max(4, len(token) - 3)]


class Buscador:
    def __init__(self, db=DB_PATH):
        self.con = sqlite3.connect(db)
        self.con.row_factory = sqlite3.Row

        modelo = self.con.execute("SELECT modelo FROM embeddings LIMIT 1").fetchone()[0]
        self.embedder = carregar_embedder(modelo)
        rows = self.con.execute("SELECT fornecedor_id, vetor FROM embeddings ORDER BY fornecedor_id").fetchall()
        self.pos = {r[0]: i for i, r in enumerate(rows)}
        self.matriz = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rows])

        self.media_aval = self.con.execute("SELECT AVG(avaliacao) FROM fornecedores").fetchone()[0]
        self._monta_gazetteer()

    # ------------------------------------------------------------------ interpretação
    def _monta_gazetteer(self):
        regiao_uf = {r[0]: r[1] for r in self.con.execute("SELECT DISTINCT regiao, uf FROM fornecedores")}
        self.cidade_info = {}
        for r in self.con.execute("SELECT DISTINCT cidade_sede, uf, regiao FROM fornecedores"):
            self.cidade_info[r[0]] = (r[1], r[2])

        padroes = [(norm(c), "cidade", c) for c in self.cidade_info]
        padroes += [(norm(reg), "regiao", reg) for reg in regiao_uf]
        padroes += [(alias, "regiao", reg) for alias, reg in ALIAS_REGIAO.items()]
        padroes += [(nome, "uf", uf) for nome, uf in NOMES_UF.items()]
        padroes += [(uf.lower(), "uf", uf) for uf in set(regiao_uf.values())]
        # mais longos primeiro: "espirito santo do pinhal" antes de "espirito santo"
        self.padroes = sorted(set(padroes), key=lambda p: -len(p[0]))

    def interpretar(self, pergunta):
        q = norm(pergunta)
        livre = f" {q} "
        cidades, regioes, ufs = [], [], []
        for pad, tipo, valor in self.padroes:
            m = re.search(rf"(?<![a-z0-9]){re.escape(pad)}(?![a-z0-9])", livre)
            if not m:
                continue
            livre = livre[:m.start()] + " " + livre[m.end():]
            {"cidade": cidades, "regiao": regioes, "uf": ufs}[tipo].append(valor)

        tipo_cadastro = None
        if any(p in f" {q} " for p in PISTAS_PRODUTO):
            tipo_cadastro = "produto"
        elif any(p in f" {q} " for p in PISTAS_SERVICO):
            tipo_cadastro = "servico"

        tokens = re.findall(r"[a-z0-9]+", livre)
        termos = list(dict.fromkeys(t for t in tokens if t not in STOPWORDS and len(t) >= 3))
        return {"cidades": cidades, "regioes": regioes, "ufs": ufs,
                "tipo_cadastro": tipo_cadastro, "termos": termos}

    @staticmethod
    def _consulta_fts(termos):
        """Cada termo vira (termo OR raiz*) + sinônimos. O termo exato soma mais no BM25 que só o prefixo."""
        partes = []
        for t in termos:
            for w in [t, *SINONIMOS.get(t, [])]:
                r = raiz(w)
                partes.append(w if r == w else f"{w} OR {r}*")
        return " OR ".join(dict.fromkeys(partes))

    # ------------------------------------------------------------------ filtro SQL
    def _candidatos(self, it, estrito):
        """Sempre filtra ativos. Com estrito=True, filtra também por localização no SQL."""
        where, params = ["ativo = 1"], []
        regioes = list(dict.fromkeys(it["regioes"] + [self.cidade_info[c][1] for c in it["cidades"]]))
        if estrito and (it["cidades"] or regioes or it["ufs"]):
            ors = ["abrangencia = 'nacional'"]
            for c in it["cidades"]:
                ors.append("(',' || replace(cidades_atendidas, ', ', ',') || ',') LIKE ?")
                params.append(f"%,{c},%")
            for r in regioes:
                ors.append("regiao = ?")
                params.append(r)
            for u in it["ufs"]:
                ors.append("uf = ?")
                params.append(u)
            where.append("(" + " OR ".join(ors) + ")")
        sql = f"SELECT * FROM fornecedores WHERE {' AND '.join(where)}"
        return [dict(r) for r in self.con.execute(sql, params)], regioes

    def _nivel_local(self, r, it, regioes):
        if not (it["cidades"] or it["regioes"] or it["ufs"]):
            return None
        atendidas = [c.strip() for c in (r["cidades_atendidas"] or "").split(",")]
        ufs_pedidas = set(it["ufs"]) | {self.cidade_info[c][0] for c in it["cidades"]}
        if it["cidades"]:
            if r["cidade_sede"] in it["cidades"] or any(c in atendidas for c in it["cidades"]):
                return 4
            if r["regiao"] in regioes:
                return 3
        elif it["regioes"] and r["regiao"] in regioes:
            return 4
        elif it["ufs"] and r["uf"] in it["ufs"]:
            return 4
        if r["abrangencia"] == "nacional":
            return 1
        if r["uf"] in ufs_pedidas:
            return 2
        return 0

    # ------------------------------------------------------------------ busca
    def buscar(self, pergunta, k=5, estrito=False):
        it = self.interpretar(pergunta)
        cands, regioes = self._candidatos(it, estrito)
        if not cands:
            return it, []
        ids = [c["id"] for c in cands]
        idset = set(ids)

        # lexical (BM25; no FTS5 quanto mais negativo, melhor)
        lex = {}
        if it["termos"]:
            for rid, s in self.con.execute(
                    "SELECT rowid, bm25(fornecedores_fts, 10.0, 5.0, 1.0) FROM fornecedores_fts "
                    "WHERE fornecedores_fts MATCH ?", (self._consulta_fts(it["termos"]),)):
                if rid in idset:
                    lex[rid] = -s
        lmax = max(lex.values(), default=0) or 1.0

        # semântica (cosseno), normalizada entre a mediana e o máximo
        qv = self.embedder.query(pergunta)
        sims = self.matriz[[self.pos[i] for i in ids]] @ qv
        p50, smax = float(np.median(sims)), float(sims.max())
        sem = np.clip((sims - p50) / (smax - p50 + 1e-9), 0, 1)

        rel = {c["id"]: ALPHA_LEXICAL * lex.get(c["id"], 0) / lmax + (1 - ALPHA_LEXICAL) * s_norm
               for c, s_norm in zip(cands, sem.tolist())}
        rel_tipo = {}
        for c in cands:
            rel_tipo[c["tipo"]] = max(rel_tipo.get(c["tipo"], 0), rel[c["id"]])
        raizes = {raiz(w) for t in it["termos"] for w in [t, *SINONIMOS.get(t, [])]}
        for tipo in rel_tipo:
            palavras = re.findall(r"[a-z0-9]+", norm(tipo))
            if any(p.startswith(r) for r in raizes for p in palavras if len(p) >= 3):
                rel_tipo[tipo] += BONUS_NOME_TIPO

        resultados = []
        for c, sim in zip(cands, sims.tolist()):
            relevancia = PESO_TIPO * rel_tipo[c["tipo"]] + (1 - PESO_TIPO) * rel[c["id"]]
            nivel = self._nivel_local(c, it, regioes)
            bayes = ((c["total_avaliacoes"] * c["avaliacao"] + BAYES_C * self.media_aval) /
                     (c["total_avaliacoes"] + BAYES_C))
            score = relevancia + PESO_AVALIACAO * (bayes - 3) / 2
            if nivel is not None:
                score += BONUS_LOCAL[nivel]
            if it["tipo_cadastro"] and c["tipo_cadastro"] == it["tipo_cadastro"]:
                score += BONUS_TIPO_CADASTRO
            resultados.append({**c, "score": round(score, 4), "relevancia": round(relevancia, 4),
                               "nivel_local": nivel, "fora_da_area": nivel == 0,
                               "similaridade": round(sim, 4), "avaliacao_bayes": round(bayes, 2)})

        resultados.sort(key=lambda r: -r["score"])
        escolhidos, por_tipo = [], {}
        for r in resultados:
            if por_tipo.get(r["tipo"], 0) < MAX_POR_TIPO:
                escolhidos.append(r)
                por_tipo[r["tipo"]] = por_tipo.get(r["tipo"], 0) + 1
            if len(escolhidos) == k:
                break
        return it, escolhidos


# ---------------------------------------------------------------------------
# Contexto para o LLM (próxima etapa do RAG)
# ---------------------------------------------------------------------------
def fmt_preco(r):
    if "%" in r["unidade_preco"]:
        return f"{r['preco_medio']:g}% ({r['unidade_preco']})"
    v = f"{r['preco_medio']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {v} por {r['unidade_preco']}"


def _atende(r):
    if r["abrangencia"] == "nacional":
        return "todo o Brasil"
    if r["abrangencia"] == "regional":
        return f"toda a região {r['regiao']} (raio de {r['raio_atendimento_km']} km)"
    return f"{r['cidades_atendidas']} (raio de {r['raio_atendimento_km']} km)"


def montar_contexto(resultados):
    """Contexto enxuto para o LLM: só fatos estruturados, um fornecedor por bloco numerado."""
    blocos = []
    for n, r in enumerate(resultados, 1):
        linhas = [
            f"[{n}] {r['nome']} — {r['tipo']} ({'empresa' if r['natureza'] == 'empresa' else 'autônomo'})",
            f"Especialidades: {r['especialidades']}",
            f"Sede: {r['cidade_sede']}/{r['uf']} | Atende: {_atende(r)}",
            f"Avaliação: {r['avaliacao']} de 5 ({r['total_avaliacoes']} avaliações) | Preço médio: {fmt_preco(r)}",
            f"Disponibilidade: {r['disponibilidade']}",
        ]
        if r["certificacoes"]:
            linhas.append(f"Registros: {r['certificacoes']}")
        if r.get("fora_da_area"):
            linhas.append("ATENÇÃO: fica FORA da área que o usuário pediu.")
        blocos.append("\n".join(linhas))
    return "\n\n".join(blocos)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pergunta")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--contexto", action="store_true", help="imprime o contexto que iria para o LLM")
    ap.add_argument("--estrito", action="store_true", help="exclui no SQL quem não atende a localização")
    args = ap.parse_args()

    b = Buscador(args.db)
    it, res = b.buscar(args.pergunta, args.k, estrito=args.estrito)
    if args.json:
        publicos = [{c: v for c, v in r.items() if c != "telefone"} for r in res]  # contato nunca sai
        print(json.dumps({"interpretacao": it, "resultados": publicos}, ensure_ascii=False, indent=2))
        return
    if args.contexto:
        print(montar_contexto(res))
        return

    loc = it["cidades"] or it["regioes"] or it["ufs"] or ["qualquer lugar"]
    print(f"Local: {', '.join(loc)} | Quer: {it['tipo_cadastro'] or 'não indicado'} | Termos: {it['termos']}")
    print(f"FTS: {b._consulta_fts(it['termos'])}\n")
    if not res:
        print("Nenhum fornecedor encontrado para essa localização.")
    for n, r in enumerate(res, 1):
        print(f"{n}. {r['nome']} — {r['tipo']}")
        print(f"   {r['cidade_sede']}/{r['uf']} ({r['regiao']}, {r['abrangencia']}) | "
              f"★ {r['avaliacao']} ({r['total_avaliacoes']}) | {fmt_preco(r)}")
        fora = "  ⚠ FORA DA ÁREA PEDIDA" if r["fora_da_area"] else ""
        print(f"   score={r['score']} relevância={r['relevancia']} local={r['nivel_local']}{fora}")


if __name__ == "__main__":
    main()
