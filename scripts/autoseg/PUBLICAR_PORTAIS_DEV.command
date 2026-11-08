#!/bin/zsh
set -eu
cd /Users/idkosx/GestaoServicos_DEV || exit 1
export AUTOSEG_DEV=1
export GESTAO_BANCO=/Users/idkosx/GestaoServicos_DEV/dados_teste/autoseg_teste.db
if [[ ! -x /Users/idkosx/GestaoServicos_DEV/.venv/bin/python ]]; then
  echo 'Ambiente virtual .venv ausente. Inicie o AUTOSEG DEV primeiro.'
  exit 1
fi
/Users/idkosx/GestaoServicos_DEV/.venv/bin/python /Users/idkosx/GestaoServicos_DEV/flavors/autoseg/modules/tuneis_dev.py iniciar
