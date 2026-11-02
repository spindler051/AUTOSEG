#!/bin/bash
set -Eeuo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
    echo "Ambiente virtual ausente. Reinstale usando INSTALAR_NO_MAC.command."
    exit 1
fi
if ! .venv/bin/python -c 'import reportlab, PIL' >/dev/null 2>&1; then
    echo "Bibliotecas PDF ausentes no ambiente do AUTOSEG. Instalando..."
    .venv/bin/python -m pip install -r requirements.txt || {
        echo "Falha ao instalar ReportLab/Pillow. Confira conexão e execute o diagnóstico."; exit 1;
    }
fi
exec .venv/bin/python app.py
