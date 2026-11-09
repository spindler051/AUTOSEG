#!/usr/bin/env bash
# Copia um snapshot consistente do banco do macOS para o Linux.
# Leitura segura: usa "sqlite3 .backup", não copia o arquivo em uso.
set -euo pipefail

REMOTE="${AUTOSEG_MAC_SSH:-}"
if [[ -z "$REMOTE" ]]; then
    echo 'Defina AUTOSEG_MAC_SSH=usuario@host-do-mac (sem valor padrao no repositorio).' >&2
    exit 2
fi
REMOTE_BASE="${AUTOSEG_MAC_BASE:-$HOME/gestaoservicos_MAIN}"
REMOTE_DB="${AUTOSEG_MAC_DB:-$REMOTE_BASE/dados.db}"
LOCAL="${1:-$HOME/autoseg/dados_remoto.db}"
TMP="/tmp/autoseg_snapshot_$$.db"

mkdir -p "$(dirname "$LOCAL")"
ssh "$REMOTE" "sqlite3 '$REMOTE_DB' \".backup '$TMP'\""
scp "$REMOTE:$TMP" "$LOCAL.tmp"
ssh "$REMOTE" "rm -f '$TMP'"
mv "$LOCAL.tmp" "$LOCAL"
chmod 600 "$LOCAL"
echo "Snapshot remoto: $LOCAL"
python3 - "$LOCAL" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
for tabela in ("clientes", "ordens_servico"):
    print(tabela, c.execute(f"select count(*) from {tabela}").fetchone()[0])
PY
