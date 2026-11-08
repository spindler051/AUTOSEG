#!/bin/zsh
# Servidor de dados do AUTOSEG DEV. Abra este terminal antes do app.
set -e
cd "$(dirname "$0")/../.."
export AUTOSEG_DEV=1
export AUTOSEG_WEB_ACCESS=0
PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=.venv/bin/python
export AUTOSEG_SERVER_DATA="$("$PY" -c 'from officina.core import runtime_config; print(runtime_config.server_data_dir())')"
printf 'AUTOSEG DEV — servidor de dados\nDados: %s\nAPI: http://127.0.0.1:8766/api/v1\n' \
  "$AUTOSEG_SERVER_DATA"
exec "$PY" flavors/autoseg/modules/servidor_backend.py --api --host 127.0.0.1 --port 8766 "$@"
