#!/bin/bash
set -Eeuo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Ambiente virtual ausente. Rode o instalador da Gestão de Serviços.'
  exit 1
fi
if ! .venv/bin/python -c 'import yaml' >/dev/null 2>&1; then
  echo 'PyYAML não instalado. Execute: ~/GestaoServicos/.venv/bin/python -m pip install "PyYAML>=6,<7"'
  exit 1
fi
export PYTHONPATH="$(pwd)/workaholic/src${PYTHONPATH:+:$PYTHONPATH}"
exec .venv/bin/python -m workaholic.cli.main "$@"
