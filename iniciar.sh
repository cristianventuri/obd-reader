#!/usr/bin/env bash
# Inicia o leitor.  ./iniciar.sh            -> só o terminal
#                   ./iniciar.sh --painel   -> terminal + painel web em http://localhost:8080
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Preparando o ambiente Python (só na primeira vez)..." >&2
  python3 -m venv .venv
fi
# Reinstala só quando o requirements.txt muda.
if [ requirements.txt -nt .venv/.dependencias ]; then
  .venv/bin/pip install -q -r requirements.txt >&2
  touch .venv/.dependencias
fi
exec .venv/bin/python -m leitor "$@"
