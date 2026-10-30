#!/bin/zsh

cd "/Users/idkosx/GestaoServicos_DEV" || exit 1

export GESTAO_BANCO="/Users/idkosx/GestaoServicos_DEV/dados_teste/autoseg_teste.db"

export AUTOSEG_DEV=1
export PRESTADOR_PORT=8866
export PRESTADOR_BIND=127.0.0.1
export CLIENTE_PORT=8865
export CLIENTE_BIND=127.0.0.1

echo "=================================="
echo "AUTOSEG - AMBIENTE DE DESENVOLVIMENTO"
echo "Banco: $GESTAO_BANCO"
echo "=================================="

exec "/Users/idkosx/GestaoServicos_DEV/.venv/bin/python" app.py
