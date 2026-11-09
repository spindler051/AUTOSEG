#!/bin/zsh
cd "$(dirname "$0")/../.." || exit 1
export AUTOSEG_DEV=1
PYTHON="$PWD/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo 'ERRO: ambiente .venv ausente. Crie o ambiente e instale requirements.txt.'
  exit 1
fi
"$PWD/scripts/autoseg/RODAR_TESTES.command" -q || exit 1
"$PYTHON" -m compileall -q officina flavors tests workaholic/src || exit 1
if command -v node >/dev/null 2>&1; then
  node --check flavors/autoseg/web/portal.js || exit 1
fi
echo 'AUTOSEG DEV: testes automatizados aprovados. Verifique também a interface real no Mac.'
