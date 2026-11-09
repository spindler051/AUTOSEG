#!/bin/zsh
# Sobe a GUI do site em DEV: Portal do Cliente (8865) e Portal do Prestador (8866).
# Usa o banco de teste e não conflita com a API headless do GTK em 8766.
set -e
cd "$(dirname "$0")/../.."
export AUTOSEG_DEV=1
export CLIENTE_PORT="${CLIENTE_PORT:-8865}"
export PRESTADOR_PORT="${PRESTADOR_PORT:-8866}"
PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=.venv/bin/python
export AUTOSEG_SERVER_DATA="$("$PY" -c 'from officina.core import runtime_config; print(runtime_config.server_data_dir())')"
printf 'AUTOSEG DEV — GUI do site\n'
printf 'Cliente:  http://127.0.0.1:%s/\n' "$CLIENTE_PORT"
printf 'Prestador: http://127.0.0.1:%s/\n' "$PRESTADOR_PORT"
printf 'Dados: %s\n' "$AUTOSEG_SERVER_DATA"
exec "$PY" flavors/autoseg/modules/servidor_backend.py --site "$@"
