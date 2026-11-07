#!/bin/zsh
# Abre o AUTOSEG GTK em modo totalmente local: sem portas 8765/8766 e sem túnel.
set -e
cd "$(dirname "$0")"
exec ./INICIAR_AUTOSEG.command --no-web
