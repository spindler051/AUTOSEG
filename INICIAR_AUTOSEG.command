#!/bin/zsh
# Interface padrão: GTK4/libadwaita. O aplicativo Tkinter foi removido.
set -e
cd "$(dirname "$0")"
exec ./INICIAR_AUTOSEG_GTK.command "$@"
