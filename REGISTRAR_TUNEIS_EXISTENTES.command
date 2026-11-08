#!/bin/bash
set -Eeuo pipefail
cd "$(dirname "$0")"
PY=".venv/bin/python"
if [[ ! -x "$PY" ]]; then PY=python3; fi
"$PY" flavors/autoseg/modules/gerenciar_tuneis.py registrar
