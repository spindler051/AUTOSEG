#!/bin/zsh
cd "$(dirname "$0")" || exit 1
export AUTOSEG_DEV=1
export GESTAO_BANCO="$PWD/dados_teste/autoseg_teste.db"
"$PWD/.venv/bin/python" CRIAR_CADASTROS_FICTICIOS_DEV.py
