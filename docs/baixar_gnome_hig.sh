#!/usr/bin/env bash
# Baixa o espelho offline da GNOME HIG para docs/gnome-hig/.
# O diretório não é versionado (documentação de terceiros, ~4,5 MB).
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v wget >/dev/null 2>&1; then
    echo "wget não encontrado." >&2
    exit 1
fi
mkdir -p docs/gnome-hig
wget -q -r -np -nH --cut-dirs=1 -P docs/gnome-hig -E -k \
    --accept-regex='developer\.gnome\.org/hig' \
    https://developer.gnome.org/hig/

cat > docs/gnome-hig/FONTE.md <<'EOF'
# Fonte das normas GNOME

Espelho estático baixado de <https://developer.gnome.org/hig/>.

- Índice: `index.html`
- Princípios: `principles.html`
- Diretrizes: `guidelines.html`
- Padrões: `patterns.html`
- Referência: `reference/`

O conteúdo pertence ao projeto GNOME e mantém a licença original.
Não é código do AUTOSEG.
EOF
echo "GNOME HIG baixada em docs/gnome-hig/index.html"
