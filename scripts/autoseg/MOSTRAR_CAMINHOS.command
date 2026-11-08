#!/bin/zsh
# Mostra os caminhos de dados sem criar banco nem iniciar serviços.
cd "$(dirname "$0")/../.." || exit 1
PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec env PYTHONPATH="$PWD" "$PY" "$PWD/scripts/autoseg/mostrar_caminhos.py" "$@"
