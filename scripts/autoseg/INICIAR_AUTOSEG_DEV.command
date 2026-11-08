#!/bin/zsh
cd "$(dirname "$0")/../.." || exit 1
export AUTOSEG_DEV=1
export AUTOSEG_BASE="$PWD/data"
export GESTAO_BANCO="$PWD/data/dados_teste/autoseg_teste.db"
export AUTOSEG_CONNECTION_MODE=remote
export AUTOSEG_SERVER_URL="${AUTOSEG_SERVER_URL:-http://127.0.0.1:8766}"
export AUTOSEG_WEB_ACCESS=0
mkdir -p "$PWD/dados_teste" || exit 1
if [[ ! -x "$PWD/.venv-gtk/bin/python" ]]; then
  echo 'Ambiente GTK .venv-gtk não encontrado. Use INICIAR_AUTOSEG_GTK.command para criá-lo.'
  exit 1
fi
printf 'AUTOSEG DEV — modo servidor\nServidor: %s\nBanco do servidor: %s\n' \
  "$AUTOSEG_SERVER_URL" "$GESTAO_BANCO"
printf 'Inicie o servidor antes: ./INICIAR_SERVIDOR_DEV.command\n'
exec "$PWD/scripts/autoseg/INICIAR_AUTOSEG_GTK.command" "$@"
