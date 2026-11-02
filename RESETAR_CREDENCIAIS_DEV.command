#!/bin/zsh
# Restaura as credenciais fictícias do ambiente DEV (nunca usar em produção).
cd "$(dirname "$0")" || exit 1
if [[ ! -x .venv/bin/python ]]; then
    echo "Ambiente .venv ausente."
    exit 1
fi
exec .venv/bin/python RESETAR_CREDENCIAIS_DEV.py
