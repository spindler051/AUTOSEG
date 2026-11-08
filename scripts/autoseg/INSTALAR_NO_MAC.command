#!/bin/bash
# Wrapper para o instalador aditivo v9.4.
set -Eeuo pipefail
BASE="$(cd "$(dirname "$0")/../.." && pwd)"
exec bash "$BASE/ATUALIZAR_AUTOSEG_V9_4.command" "$@"
