#!/bin/zsh
# Servidor de dados do AUTOSEG DEV. Abra este terminal antes do app.
set -e
cd "$(dirname "$0")"
export AUTOSEG_DEV=1
export AUTOSEG_BASE="$PWD"
export GESTAO_BANCO="$PWD/dados_teste/autoseg_teste.db"
export AUTOSEG_WEB_ACCESS=0
mkdir -p "$PWD/dados_teste"
PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=.venv/bin/python
printf 'AUTOSEG DEV — servidor de dados\nBanco: %s\nAPI: http://127.0.0.1:8766/api/v1\n' \
  "$GESTAO_BANCO"
exec "$PY" flavors/autoseg/modules/servidor_backend.py --api --host 127.0.0.1 --port 8766 "$@"
