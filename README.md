# RAG de fornecedores da cadeia do café

Busca híbrida (SQLite + FTS5 + embeddings **bge-m3**) e resposta do **Qwen3.5-4B**, configurados para **GPU de 8 GB**.

```
pergunta ─► interpretação (cidade/região/UF, comprar×contratar)
         ─► filtro SQL (ativos) ─► BM25 (FTS5) + cosseno (bge-m3 na CPU)
         ─► relevância por tipo + rerank (localização, avaliação bayesiana)
         ─► top-5 em contexto enxuto ─► Qwen3.5-4B 4-bit no SGLang (GPU, :30000) ─► resposta citando [n]
```

## Como os dois modelos cabem em 8 GB

| Modelo | Onde roda | Memória |
|---|---|---|
| `RedHatAI/Qwen3.5-4B-quantized.w4a16` | GPU, via SGLang | ~5,2 GB de pesos + cache KV (fração de 0,80 da VRAM) |
| `BAAI/bge-m3` | CPU, dentro do `rag.py` | ~2,5 GB de RAM; ~0,1–0,3 s por pergunta |

Os dois ficam carregados ao mesmo tempo. O bge-m3 só precisa embeddar a pergunta do usuário, um texto curto,
então a CPU dá conta. Os documentos são embeddados uma única vez, no `indexar.py`.
A versão 4-bit do Qwen mantém ~98% do desempenho do original (MMLU-Pro).

## Arquivos

| Arquivo | O que faz |
|---|---|
| `schema.sql` / `gerar_dados.py` | Schema e gerador dos dados mockados: 1500 fornecedores, 70 tipos, 106 cidades (`--total` muda o tamanho) |
| `servir_llm.sh` | Sobe o Qwen3.5-4B 4-bit no SGLang (porta 30000) |
| `servir_embeddings.sh` | **Opcional**, para GPUs maiores: bge-m3 no SGLang (porta 30001) |
| `embeddings.py` | Backends de embedding: `st` (padrão, bge-m3 na CPU), `sglang`, `lsa` (offline) |
| `indexar.py` | Cria o índice FTS5 e a tabela `embeddings` dentro do `.db` |
| `busca.py` | Busca híbrida (só recuperação, sem LLM) |
| `rag.py` | RAG completo: busca + resposta do LLM, em modo conversa ou pergunta única |
| `avaliar.py` | 26 perguntas de teste (Hit@1, P@3, Hit@5, localização), só da recuperação |

## 1. Instalar

São **dois ambientes Python**:
- `.venv` para o RAG, em qualquer versão do Python
- `.venv-sglang` para o servidor do LLM, que precisa de **Python 3.10 a 3.13**

O SGLang ainda não tem pacote para o Python 3.14. O jeito mais fácil de criar o segundo ambiente é com o
[uv](https://docs.astral.sh/uv/), que baixa o Python 3.12 sozinho.

O SGLang precisa de **Linux com GPU NVIDIA** (no Windows, use **WSL2**). O kernel 4-bit (Marlin) exige
**RTX série 30 ou mais nova**.

```bash
# instala o uv (uma vez)
curl -LsSf https://astral.sh/uv/install.sh | sh

# ambiente do RAG
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# ambiente do SGLang (Python 3.12) — o servir_llm.sh usa esse ambiente automaticamente
uv venv --python 3.12 .venv-sglang
uv pip install --python .venv-sglang sglang
```

O SGLang compila alguns kernels na primeira execução (JIT), então também precisa do **CUDA Toolkit** (`nvcc`),
que não vem com o driver. No Fedora (o driver 580 aceita qualquer toolkit 13.x):

```bash
sudo dnf install gcc-c++
sudo dnf config-manager addrepo --from-repofile=https://developer.download.nvidia.com/compute/cuda/repos/fedora$(rpm -E %fedora)/x86_64/cuda-fedora$(rpm -E %fedora).repo
sudo dnf install cuda-toolkit-13-2
uv pip install --python .venv-sglang ninja
```

Instale só o `cuda-toolkit`, e não o pacote `cuda` completo, que tentaria trocar o driver.
O `servir_llm.sh` encontra o toolkit em `/usr/local/cuda` sozinho.

Confira se o SGLang enxerga a GPU:

```bash
.venv-sglang/bin/python -c "import sglang, torch; print(sglang.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

## 2. Indexar (uma vez, e sempre que o banco mudar)

```bash
python indexar.py          # baixa o bge-m3 (~2,3 GB) na 1ª vez e embedda os fornecedores na CPU
python avaliar.py -v       # confere a qualidade da recuperação
```

## 3. Subir o LLM e usar

```bash
CUDA_GRAPH_PREFILL=256 ./servir_llm.sh                                            # terminal 1 — espere "The server is fired up"
python rag.py                                              # terminal 2 — modo conversa
python rag.py "preciso podar meu café em Varginha" --fontes
python busca.py "onde compro adubo no sul de minas"        # só a recuperação, para depurar
```

### Se der falta de memória (OOM) na GPU

1. Feche o que mais estiver usando a GPU (navegador com aceleração, jogos). No WSL, o Windows também reserva VRAM.
2. **Não baixe `MEM_LLM` de 0,80:** o Qwen3.5 é híbrido e o estado da atenção linear precisa desse espaço
   (abaixo disso o servidor nem sobe: `state cache is too small`).
3. Se o servidor cair na primeira resposta com `NCCL error ... Failed to CUDA calloc`, faltou memória **fora** da reserva
   (a saída JSON com esquema inicializa a NCCL, que aloca ~512 MB). Reduza os CUDA graphs de prefill com
   `CUDA_GRAPH_PREFILL=256 ./servir_llm.sh` ou use `JSON_SCHEMA=0` no `rag.py`.
4. Ainda não coube? Use o Qwen3.5-2B: `MODELO=Qwen/Qwen3.5-2B ./servir_llm.sh`. O `rag.py` não muda,
   porque o nome servido continua `qwen3.5-4b`.

## Saída para o bot de WhatsApp

O `rag.py` não devolve texto livre. `RAG().responder(pergunta)` devolve um `RespostaBot`:

| Campo | Conteúdo |
|---|---|
| `texto` | corpo da mensagem com formatação do WhatsApp (`*negrito*`, `_itálico_`) |
| `botoes` | até 3 `Botao(id="contatar:<id>", titulo≤20 caracteres, fornecedor_id)` |
| `fornecedores` | dados **públicos** dos recomendados (sem telefone) |
| `para_whatsapp(numero)` | payload pronto da WhatsApp Cloud API (mensagem interativa com botões) |

Como a resposta é montada:
1. O LLM recebe só dados públicos e devolve **JSON com formato garantido** pelo SGLang (`response_format` json_schema):
   uma introdução e quais fornecedores recomendar, com o motivo.
2. O código valida os números (descarta inválidos e repetidos) e monta a mensagem com **nome, cidade, avaliação e preço
   vindos do banco**. O modelo escreve só a introdução e os motivos, então não tem como inventar preço ou avaliação.
3. **O telefone nunca sai do servidor:** não vai para o prompt, para a resposta nem para o `busca.py --json`.
   Quando o usuário toca no botão, o webhook recebe `button_reply.id = "contatar:<id>"`;
   `fornecedor_do_botao(id)` devolve o id do fornecedor para o bot abrir a conversa mediada.

```bash
Abrir o servidor: CUDA_GRAPH_PREFILL=256 ./servir_llm.sh
Rodar o chat: python rag.py 
python rag.py "preciso podar meu café em Varginha" --fontes    # prévia da mensagem e dos botões
python rag.py "preciso podar meu café em Varginha" --whatsapp  # payload JSON da Cloud API
```

## Banco mockado

`python gerar_dados.py` recria o banco do zero (seed fixa: sempre o mesmo banco). **Depois, rode `python indexar.py` de novo.**

- 1500 fornecedores (802 serviços, 698 produtos), 70 tipos, 11 regiões cafeeiras e 106 cidades.
- Todo tipo aparece em todas as regiões. O restante segue o peso de cada região (Sul de Minas tem ~3x o Oeste da Bahia).
- A quantidade por tipo segue a frequência real: colhedores e agrônomos têm ~39, revendas de colhedora têm ~16.
- As descrições misturam frases do tipo com frases genéricas (nota fiscal, pagamento, atendimento), então nenhuma se repete.

Resultado da avaliação com 1500 registros (backend offline `lsa`):
**Hit@1 96% · P@3 95% · Hit@5 100% · 97% dos resultados certos dentro da área pedida.**

## Decisões importantes

- **Thinking desligado:** o Qwen3.5 pensa antes de responder por padrão. O `rag.py` manda
  `chat_template_kwargs={"enable_thinking": false}`, o que deixa a resposta mais rápida e sem blocos `<think>`.
- **Temperatura 0,3:** mais baixa que a sugerida pelo Qwen (0,7), porque a resposta precisa se ater ao contexto.
- **Contexto enxuto:** o LLM recebe só fatos estruturados de 5 fornecedores (~1,5 k tokens). Modelos de 4B erram menos assim.
- **Guarda contra alucinação:** o LLM só escolhe fornecedores da lista, por número, e os fatos exibidos vêm do banco.
- **No máximo 3 resultados do mesmo tipo no top 5** (`MAX_POR_TIPO`): em perguntas ambíguas, como
  "EPI para aplicação de agrotóxico", o LLM recebe as duas leituras (loja de EPI e aplicador) e escolhe.
- **Bônus quando a pergunta cita o nome do tipo** (`BONUS_NOME_TIPO`): "EPI", "poda", "crédito" (sinônimo de financiamento).
- **Localização como preferência forte:** quem está fora da área só aparece se for bem mais relevante,
  e vai marcado para o LLM avisar o usuário. Use `--estrito` para excluir essas opções no SQL.
- **O bge-m3 não usa prefixo** (`query:`/`passage:`), diferente do e5.
- **bge-m3 na CPU por padrão:** com mais VRAM, use `EMBED_DEVICE=cuda` ou o servidor opcional `servir_embeddings.sh`
  com `python indexar.py --backend sglang`.

## Variáveis de ambiente

| Variável | Padrão |
|---|---|
| `LLM_URL` | `http://127.0.0.1:30000/v1` |
| `LLM_MODELO` | `qwen3.5-4b` (nome servido pelo `servir_llm.sh`) |
| `EMBED_DEVICE` | `cpu` |
| `EMBED_URL` | `http://127.0.0.1:30001/v1` (só no backend `sglang`) |

## Começar sem GPU

O banco (`fornecedores_cafe.db`) não vai no repositório, porque é gerado pelos scripts:

```bash
python gerar_dados.py            # cria o banco mockado (seed fixa)
python indexar.py --backend lsa  # índice offline, sem baixar modelos
python busca.py "onde compro adubo no sul de minas"
```

Depois, rode `python indexar.py` para trocar pelos embeddings do bge-m3.
