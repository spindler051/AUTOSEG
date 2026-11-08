#!/bin/zsh
cd "$(dirname "$0")/../.."
export AUTOSEG_BASE="$PWD/data"
export GESTAO_BANCO="$PWD/data/dados_teste/autoseg_teste.db" || exit 1
export AUTOSEG_DEV=1
export GESTAO_BANCO="$PWD/dados_teste/autoseg_teste.db"
"$PWD/.venv/bin/python" flavors/autoseg/scripts/CRIAR_CADASTROS_FICTICIOS_DEV.py
