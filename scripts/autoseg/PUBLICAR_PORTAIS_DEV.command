#!/bin/zsh
set -eu
cd "$(dirname "$0")/../.." || exit 1
export AUTOSEG_DEV=1
PY="$PWD/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo 'Ambiente virtual .venv ausente. Inicie o AUTOSEG DEV primeiro.'
  exit 1
fi
export AUTOSEG_SERVER_DATA="$("$PY" -c 'from officina.core import runtime_config; print(runtime_config.server_data_dir())')"
exec "$PY" flavors/autoseg/modules/tuneis_dev.py iniciar
