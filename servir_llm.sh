#!/usr/bin/env bash
# LLM: Qwen3.5-4B quantizado em 4 bits (W4A16, ~5,2 GB) no SGLang, porta 30000.
# Configurado para GPU de 8 GB. O bge-m3 roda na CPU, dentro do rag.py, então a GPU fica só para o LLM.
#
# Variáveis opcionais:
#   MODELO   checkpoint (padrão RedHatAI/Qwen3.5-4B-quantized.w4a16)
#   MEM_LLM  fração da VRAM para pesos + cache KV + estado da atenção linear (padrão 0.80).
#            Abaixo de 0.80 não cabe o estado do Qwen3.5 (erro "state cache is too small").
#            Fora dessa reserva precisa sobrar ~0,6 GB: a saída JSON com esquema (xgrammar)
#            inicializa a NCCL, que aloca ~512 MB na primeira requisição.
#   CUDA_GRAPH_PREFILL  maior prefill capturado em CUDA graph (padrão 512; economiza VRAM, prompts maiores
#            rodam sem graph, só um pouco mais devagar)
#   CTX      contexto máximo (padrão 8192; o prompt do RAG usa ~1,5 k tokens)
set -e
# Usa o ambiente do SGLang (Python 3.12) se existir; senão, o python do PATH.
# Caminhos absolutos: o SGLang compila kernels a partir de outras pastas.
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -x "$DIR/.venv-sglang/bin/python" ]; then
  PY="${PYTHON:-$DIR/.venv-sglang/bin/python}"
else
  PY="${PYTHON:-python}"
fi
if ! "$PY" -c "import sglang" 2>/dev/null; then
  echo "SGLang não encontrado em: $PY"
  echo "Crie o ambiente com Python 3.12 (veja o README):"
  echo "  uv venv --python 3.12 .venv-sglang && uv pip install --python .venv-sglang sglang"
  exit 1
fi
# Ambiente para os kernels compilados na hora (JIT): ninja do venv + nvcc do CUDA Toolkit.
PYBIN="$(cd "$(dirname "$(command -v "$PY")")" && pwd)"
export PATH="$PYBIN:$PATH"
if [ -z "$CUDA_HOME" ]; then
  for d in /usr/local/cuda /usr/local/cuda-13* /opt/cuda; do
    if [ -x "$d/bin/nvcc" ]; then export CUDA_HOME="$d"; break; fi
  done
fi
[ -n "$CUDA_HOME" ] && export PATH="$CUDA_HOME/bin:$PATH"
if ! command -v ninja >/dev/null; then
  echo "ninja não encontrado. Rode: uv pip install --python .venv-sglang ninja"; exit 1
fi
if ! command -v nvcc >/dev/null; then
  echo "nvcc (CUDA Toolkit) não encontrado. Instale o CUDA Toolkit 13 (veja o README) ou defina CUDA_HOME."; exit 1
fi
# Prefere o comando "sglang serve" (recomendado); cai para launch_server em versões antigas.
SGLANG_BIN="$PYBIN/sglang"
if [ -x "$SGLANG_BIN" ]; then
  CMD=("$SGLANG_BIN" serve)
else
  CMD=("$PY" -m sglang.launch_server)
fi
"${CMD[@]}" \
  --model-path "${MODELO:-RedHatAI/Qwen3.5-4B-quantized.w4a16}" \
  --served-model-name qwen3.5-4b \
  --host 127.0.0.1 --port 30000 \
  --mem-fraction-static "${MEM_LLM:-0.80}" \
  --context-length "${CTX:-8192}" \
  --max-running-requests 1 \
  --cuda-graph-max-bs-decode 4 \
  --cuda-graph-max-bs-prefill "${CUDA_GRAPH_PREFILL:-512}" \
  --reasoning-parser qwen3 \
  ${LLM_EXTRA_ARGS}
