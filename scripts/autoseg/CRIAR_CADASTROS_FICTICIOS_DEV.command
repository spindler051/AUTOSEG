#!/bin/zsh
cd "$(dirname "$0")/../.." || exit 1
export AUTOSEG_DEV=1
PY="$PWD/.venv/bin/python"
export AUTOSEG_SERVER_DATA="$("$PY" -c 'from officina.core import runtime_config; print(runtime_config.server_data_dir())')"
export AUTOSEG_BASE="$AUTOSEG_SERVER_DATA"
export GESTAO_BANCO="$AUTOSEG_SERVER_DATA/dados_teste/autoseg_teste.db"
exec "$PY" flavors/autoseg/scripts/CRIAR_CADASTROS_FICTICIOS_DEV.py
