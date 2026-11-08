#!/bin/bash
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
echo 'AUTOSEG - Diagnóstico PDF (não modifica banco nem OS)'
echo ''
if [[ ! -x .venv/bin/python ]]; then
    echo 'ERRO: ambiente .venv não existe. Execute o instalador da v6.'
    exit 1
fi
.venv/bin/python - <<'PY'
import sys,traceback
print('Python usado:',sys.executable)
for nome in ('reportlab','PIL'):
    try:
        mod=__import__(nome)
        print(nome,'OK',getattr(mod,'Version',getattr(mod,'__version__','?')))
    except Exception:
        print(nome,'ERRO')
        traceback.print_exc()
try:
    from reportlab.pdfgen import canvas
    from pathlib import Path
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix='autosseg_pdf_') as tmp:
        caminho=Path(tmp)/'teste.pdf'
        pdf=canvas.Canvas(str(caminho))
        pdf.drawString(55,760,'AUTOSEG - Verificacao de PDF')
        pdf.save()
        assert caminho.read_bytes().startswith(b'%PDF-')
        print('PDF de teste OK:',caminho.stat().st_size,'bytes')
except Exception:
    print('ERRO NA GERACAO PDF:')
    traceback.print_exc()
PY
echo ''
if [[ -f data/logs/portal_prestador.log ]]; then
    echo 'Últimos registros do portal (pode conter nomes de clientes, revise antes de enviar):'
    tail -n 15 data/logs/portal_prestador.log
fi
