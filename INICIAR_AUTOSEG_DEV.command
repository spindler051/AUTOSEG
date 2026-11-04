#!/bin/zsh
cd "$(dirname "$0")" || exit 1
export AUTOSEG_DEV=1
export AUTOSEG_BASE="$PWD"
export GESTAO_BANCO="$PWD/dados_teste/autoseg_teste.db"
export PRESTADOR_PORT=8866
export PRESTADOR_BIND=127.0.0.1
export CLIENTE_PORT=8865
export CLIENTE_BIND=127.0.0.1
mkdir -p "$PWD/dados_teste" || exit 1
if [[ ! -x "$PWD/.venv-gtk/bin/python" ]]; then
  echo 'Ambiente GTK .venv-gtk não encontrado. Use INICIAR_AUTOSEG_GTK.command para criá-lo.'
  exit 1
fi
printf 'AUTOSEG DEV\nBanco: %s\nPortas locais: cliente 8865 / prestador 8866\n' "$GESTAO_BANCO"
exec "$PWD/INICIAR_AUTOSEG_GTK.command" "$@"
