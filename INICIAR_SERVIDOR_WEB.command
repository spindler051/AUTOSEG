#!/bin/zsh
# Sobe Oficina Web (portais HTML) + API, sem GTK e sem Cloudflare.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" servidor_backend.py --web "$@"
