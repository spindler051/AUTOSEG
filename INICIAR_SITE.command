#!/bin/zsh
# Sobe a GUI do site (Officina Web). Hoje o mesmo processo também expõe a API;
# a separação completa entre site e servidor é uma fase posterior.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" flavors/autoseg/modules/servidor_backend.py --site "$@"
