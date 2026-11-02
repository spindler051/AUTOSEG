#!/bin/zsh
# O Tkinter está congelado; o app padrão agora é o GTK4/libadwaita.
# Fallback legado: INICIAR_AUTOSEG_TK.command
set -e
cd "$(dirname "$0")"
exec ./INICIAR_AUTOSEG_GTK.command "$@"
