#!/bin/zsh
cd "$(dirname "$0")" || exit 1
export AUTOSEG_DEV=1
export AUTOSEG_BASE="$PWD"
export GESTAO_BANCO="$PWD/dados_teste/autoseg_teste.db"
export AUTOSEG_WEB_ACCESS=0
mkdir -p "$PWD/dados_teste" || exit 1
if [[ ! -x "$PWD/.venv-gtk/bin/python" ]]; then
  echo 'Ambiente GTK .venv-gtk não encontrado. Use INICIAR_AUTOSEG_GTK.command para criá-lo.'
  exit 1
fi
printf 'AUTOSEG DEV — modo local\nBanco: %s\nSem portais e sem túnel.\n' "$GESTAO_BANCO"
exec "$PWD/INICIAR_AUTOSEG_GTK.command" "$@"
