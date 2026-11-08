#!/bin/zsh
set -eu
cd /Users/idkosx/GestaoServicos_DEV || exit 1
export AUTOSEG_DEV=1
/Users/idkosx/GestaoServicos_DEV/.venv/bin/python /Users/idkosx/GestaoServicos_DEV/flavors/autoseg/modules/tuneis_dev.py parar
