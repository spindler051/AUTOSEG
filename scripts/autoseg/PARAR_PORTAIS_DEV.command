#!/bin/zsh
set -eu
cd "$(dirname "$0")/../.." || exit 1
export AUTOSEG_DEV=1
exec "$PWD/.venv/bin/python" "$PWD/flavors/autoseg/modules/tuneis_dev.py" parar
