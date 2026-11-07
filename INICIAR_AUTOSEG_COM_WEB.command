#!/bin/zsh
# Abre o app GTK com os portais locais ligados (comportamento antigo).
# O padrão agora é local-only; use este atalho só se quiser que o próprio app
# suba o site. Para produção, prefira iniciar o servidor pelo terminal.
set -e
cd "$(dirname "$0")"
export AUTOSEG_WEB_ACCESS=1
exec ./INICIAR_AUTOSEG.command
