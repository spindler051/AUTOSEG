#!/bin/zsh
# Interface padrão: GTK4/libadwaita. O aplicativo Tkinter foi removido.
# O padrão é modo local, sem subir os portais. Para o comportamento antigo,
# use INICIAR_AUTOSEG_COM_WEB.command ou AUTOSEG_WEB_ACCESS=1.
set -e
cd "$(dirname "$0")"
export AUTOSEG_WEB_ACCESS="${AUTOSEG_WEB_ACCESS:-0}"
exec ./INICIAR_AUTOSEG_GTK.command "$@"
