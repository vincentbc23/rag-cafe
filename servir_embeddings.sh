#!/usr/bin/env bash
# OPCIONAL — só para GPUs com mais VRAM (>= 12 GB). Com 8 GB, o bge-m3 roda na CPU dentro do rag.py.
# Se usar este servidor, indexe com: python indexar.py --backend sglang
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
  --model-path BAAI/bge-m3 \
  --is-embedding \
  --host 127.0.0.1 --port 30001 \
  --mem-fraction-static "${MEM_EMBED:-0.12}" \
  --disable-radix-cache
