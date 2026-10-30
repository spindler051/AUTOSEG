#!/bin/bash
# AUTOSEG v9.2 - atualização conservadora em macOS Intel / Python >=3.10.
set -Eeuo pipefail
BASE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/GestaoServicos"
ARQUIVOS=(app.py prestadores_ext.py portal_prestador.py portal_negocios.py fluxo_os.py atendimento_os.py \
  cadastros_v9.py portal_v9.py desktop_v9.py pdf_cliente_v9.py links_publicos.py gerenciar_tuneis.py \
  portal.js requirements.txt INICIAR_AUTOSEG.command DIAGNOSTICAR_PDF.command \
  INICIAR_TUNEIS_TESTE.command PARAR_TUNEIS_TESTE.command REGISTRAR_TUNEIS_EXISTENTES.command)

echo '================================================='
echo ' AUTOSEG V9.2 — Atualização segura com backup'
echo '================================================='
if [[ ! -d "$DEST" || ! -f "$DEST/app.py" || ! -f "$DEST/banco.py" || ! -f "$DEST/servidor_web.py" || ! -f "$DEST/dados.db" ]]; then
  echo "ERRO: base original não localizada em $DEST (app.py, banco.py, servidor_web.py, dados.db)."
  echo 'Nenhum arquivo foi alterado.'
  exit 1
fi
for f in "${ARQUIVOS[@]}"; do
  if [[ ! -f "$BASE/$f" ]]; then echo "ERRO: falta no ZIP: $f";exit 1;fi
done
if ! command -v python3 >/dev/null 2>&1; then echo 'ERRO: instale Python 3.10 ou mais recente.';exit 1;fi
python3 - "$BASE" <<'PY'
import pathlib,sys,py_compile
if sys.version_info < (3,10):raise SystemExit('Requer Python 3.10+')
for p in pathlib.Path(sys.argv[1]).glob('*.py'):
    if p.name.startswith('test_'):continue
    py_compile.compile(str(p),doraise=True)
print('Código v9.1 compilado com sucesso.')
PY

if [[ ! -x "$DEST/.venv/bin/python" ]]; then
  echo 'Criando ambiente Python virtual no projeto...'
  python3 -m venv "$DEST/.venv"
fi
PYTHON="$DEST/.venv/bin/python"
if ! "$PYTHON" -c 'import reportlab,PIL' >/dev/null 2>&1; then
  "$PYTHON" -m pip install --disable-pip-version-check -r "$BASE/requirements.txt" || {
    echo 'Falha ao instalar ReportLab/Pillow. Nenhum código ou dado foi substituído.';exit 1;
  }
fi
if ! "$PYTHON" -c 'import tkinter,reportlab,PIL,sqlite3' >/dev/null 2>&1; then
  echo 'ERRO: dependências Python não estão prontas. Nenhum arquivo de código foi substituído.';exit 1
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$DEST/backups/antes_v9_2_$STAMP"
mkdir -p "$BACKUP"
# Backup consistente inclusive com banco em WAL.
"$PYTHON" - "$DEST/dados.db" "$BACKUP/dados.db" <<'PY'
import sqlite3,sys
src=sqlite3.connect(sys.argv[1],timeout=20);dst=sqlite3.connect(sys.argv[2])
try:
    src.backup(dst)
finally:
    dst.close();src.close()
PY
for f in "${ARQUIVOS[@]}"; do
  if [[ -f "$DEST/$f" ]]; then cp -p "$DEST/$f" "$BACKUP/$f";fi
done
# preserve tudo: banco.py, servidor_web.py, dados.db, PDF, anexos, credenciais e logos.
echo "Backup do código e banco: $BACKUP"
echo 'Copiando somente módulos v9.2...'
for f in "${ARQUIVOS[@]}";do cp -p "$BASE/$f" "$DEST/$f";done
chmod +x "$DEST"/*.command
mkdir -p "$DEST/tuneis" "$DEST/logs" "$DEST/relatorios_pdf/publicados" "$DEST/anexos_os"
echo ''
echo 'AUTOSEG V9.2 INSTALADO.'
echo "Banco preservado: $DEST/dados.db"
echo "Backup: $BACKUP"
echo 'IMPORTANTE: feche a versão anterior e inicie com:'
echo '  bash ~/GestaoServicos/INICIAR_AUTOSEG.command'
echo 'Para túneis de teste gerenciados (OPCIONAL, só com dados fictícios):'
echo '  bash ~/GestaoServicos/INICIAR_TUNEIS_TESTE.command'
echo 'Não publicar dados reais sem revisar a segurança do servidor legado 8765.'
