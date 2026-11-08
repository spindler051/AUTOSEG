#!/bin/zsh
set -eu
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
/usr/bin/env python3 officina/core/versionador.py verificar
printf '\nPressione Enter para fechar...'
read -r
