#!/bin/zsh
# Executa a suíte com dados temporários: nenhum teste toca o banco real.
set -eu
cd "$(dirname "$0")/../.." || exit 1
PYTHON="$PWD/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo 'ERRO: ambiente .venv ausente. Crie o ambiente e instale requirements.txt.'
  exit 1
fi
TMP="$(mktemp -d "${TMPDIR:-/tmp}/autoseg-testes.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
export AUTOSEG_BASE="$TMP/base"
export GESTAO_BANCO="$TMP/base/dados.db"
export AUTOSEG_USER_DATA="$TMP/user"
export AUTOSEG_SERVER_DATA="$TMP/server"
export AUTOSEG_LOCAL_DATA="$TMP/local"
"$PYTHON" -m unittest discover -s tests -p 'test_*.py' "$@"
