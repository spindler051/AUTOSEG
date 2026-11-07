#!/bin/bash
# Atualização aditiva, segura e explícita — não instala numa pasta presumida.
set -Eeuo pipefail
BASE="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-}"
if [[ -z "$DEST" ]]; then
  echo 'Uso: bash ATUALIZAR_AUTOSEG_V9_4.command "$HOME/GestaoServicos2"'
  echo 'Ou informe a pasta de instalação ativa em vez de GestaoServicos2.'
  exit 2
fi
DEST="$(cd "$DEST" 2>/dev/null && pwd)" || { echo 'Diretório destino não encontrado.'; exit 2; }
for f in banco.py dados.db portal_prestador.py portal_v9.py cadastros_v9.py INICIAR_AUTOSEG.command; do
  [[ -f "$DEST/$f" ]] || { echo "ERRO: $DEST/$f ausente. Nenhuma alteração realizada."; exit 1; }
done
if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:8766 -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
    echo 'Feche o portal AUTOSEG da porta 8766 antes de atualizar, para evitar execução de versões misturadas.'
    exit 1
  fi
fi
PY="${DEST}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY="$(command -v python3)"; fi
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$DEST/backups/antes_portal_v9_4_$STAMP"
mkdir -p "$BACKUP"
ALTERADOS=(cadastros_v9.py portal_prestador.py portal_v9.py cliente_fluxo_v94.py portal_cliente_v94.py)
for f in "${ALTERADOS[@]}"; do
  [[ -f "$BASE/$f" ]] || { echo "ERRO: pacote incompleto ($f)."; exit 1; }
  if [[ -f "$DEST/$f" ]]; then cp -p "$DEST/$f" "$BACKUP/$f"; fi
done
"$PY" - "$DEST/dados.db" "$BACKUP/dados.db" <<'PYBACKUP'
import sqlite3,sys
src=sqlite3.connect(sys.argv[1],timeout=30)
dst=sqlite3.connect(sys.argv[2])
try:
    if src.execute('PRAGMA quick_check').fetchone()[0]!='ok':
        raise RuntimeError('Banco de dados não passou em quick_check. Atualização interrompida.')
    src.backup(dst)
finally:
    src.close();dst.close()
PYBACKUP
# Copia exclusivamente os módulos modificados; banco, GUI, imagens, legacy,
# Workaholic e outros módulos permanecem intactos.
for f in "${ALTERADOS[@]}"; do
  cp -p "$BASE/$f" "$DEST/.$f.v94.$$"
  mv -f "$DEST/.$f.v94.$$" "$DEST/$f"
done
mkdir -p "$DEST/docs"
cp -p "$BASE/docs/archive/FLUXO_CLIENTE_V9_4.md" "$DEST/docs/FLUXO_CLIENTE_V9_4.md"
cp -p "$BASE/docs/archive/MIGRACAO_MODULAR.md" "$DEST/docs/MIGRACAO_MODULAR.md"
[[ -f "$BASE/test_fluxo_cliente_v94.py" ]] && cp -p "$BASE/test_fluxo_cliente_v94.py" "$DEST/test_fluxo_cliente_v94.py"
"$PY" -m py_compile "$DEST/cadastros_v9.py" "$DEST/portal_prestador.py" "$DEST/portal_v9.py" "$DEST/cliente_fluxo_v94.py" "$DEST/portal_cliente_v94.py"
echo ''
echo 'AUTOSEG v9.4 — atualização concluída.'
echo "Backup SQLite e arquivos anteriores: $BACKUP"
echo 'Abrir a GUI com o comando habitual:'
printf '  bash "%s/INICIAR_AUTOSEG.command"\n' "$DEST"
