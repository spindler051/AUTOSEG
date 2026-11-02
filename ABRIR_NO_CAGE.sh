#!/usr/bin/env bash
# Compatibilidade: este nome não inicia mais o Cage aninhado em X11.
# O caminho suportado é o display nativo via DRM/Wayland.
set -euo pipefail
exec "$(dirname "$0")/ABRIR_NO_DRM.sh" "$@"
