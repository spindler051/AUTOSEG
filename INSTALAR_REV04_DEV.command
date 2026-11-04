#!/bin/zsh
set -eu
DEV="$HOME/GestaoServicos_DEV"
PACOTE="$(cd "$(dirname "$0")" && pwd)"

echo '=========================================='
echo 'AUTOSEG REV04 — INSTALADOR EXCLUSIVO DEV'
echo '=========================================='
if [[ ! -d "$DEV/.git" ]]; then
  echo 'ERRO: .git ausente em GestaoServicos_DEV. Não prosseguir.'
  exit 1
fi
BRANCH="$(git -C "$DEV" branch --show-current)"
if [[ "$BRANCH" != 'develop' ]]; then
  echo "ERRO: branch atual é $BRANCH, precisa ser develop. Não prosseguir."
  exit 1
fi
if [[ ! -x "$DEV/.venv/bin/python" ]]; then
  echo 'ERRO: .venv ausente. Recrie o ambiente e instale requirements.txt antes de prosseguir.'
  exit 1
fi
if [[ ! -f "$PACOTE/estoque_materiais.py" || ! -f "$PACOTE/gtk_app.py" || ! -f "$PACOTE/VERIFICAR_AUTOSEG_DEV.command" ]]; then
  echo 'ERRO: pacote incompleto. Não prosseguir.'
  exit 1
fi
if [[ ! -f "$DEV/INICIAR_AUTOSEG_DEV.command" ]]; then
  echo 'ERRO: inicializador DEV ausente. Não prosseguir.'
  exit 1
fi
printf '\nArquivos alterados antes da aplicação:\n'
git -C "$DEV" status --short
printf '\nO AUTOSEG DEV e os dois portais devem estar FECHADOS.\n'
printf 'Digite INSTALAR para criar backup e aplicar apenas ao DEV: '
read -r RESPOSTA
if [[ "$RESPOSTA" != 'INSTALAR' ]]; then
  echo 'Operação cancelada. Nenhum arquivo alterado.'
  exit 1
fi
DATA="$(date '+%Y%m%d_%H%M%S')"
BACKUP="$HOME/GestaoServicos_DEV_BACKUP_ANTES_REV04_$DATA"
echo "Backup do projeto em: $BACKUP"
/usr/bin/ditto "$DEV" "$BACKUP"
DB="$DEV/dados_teste/autoseg_teste.db"
if [[ -f "$DB" ]]; then
  echo 'Criando backup SQLite consistente do banco fictício...'
  "$DEV/.venv/bin/python" - "$DB" "$BACKUP/autoseg_teste_backup_sqlite.db" <<'PY'
import sqlite3,sys
src=sqlite3.connect(sys.argv[1],timeout=30)
dst=sqlite3.connect(sys.argv[2],timeout=30)
try:
    src.backup(dst)
    row=dst.execute('PRAGMA integrity_check').fetchone()
    if not row or row[0]!='ok':raise RuntimeError('Integridade do backup SQLite falhou')
finally:
    dst.close();src.close()
print('Backup de SQLite: integridade OK')
PY
fi
printf '\nAplicando código, modelos e testes (não contém banco/.git/.venv)...\n'
/bin/cp -R "$PACOTE/." "$DEV/"
cd "$DEV" || exit 1
"$DEV/.venv/bin/python" -m pip install -r requirements.txt || {
  echo "Falha nas dependências. O backup está em $BACKUP"; exit 1;
}
./VERIFICAR_AUTOSEG_DEV.command || {
  echo "ERRO: teste falhou. NÃO ABRA O AUTOSEG. Backup disponível: $BACKUP"
  exit 1
}
echo '=========================================='
echo 'AUTOSEG REV04 aplicado no DEV. Testes OK.'
echo "Backup: $BACKUP"
echo 'Não atualizar main / produção antes dos testes manuais.'
echo '=========================================='
