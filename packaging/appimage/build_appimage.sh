#!/usr/bin/env bash
# Rascunho de empacotamento AppImage (PyInstaller + appimagetool).
# Ainda NÃO validado em máquina limpa. Veja README.md antes de distribuir.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
SAIDA="$RAIZ/build/appimage"
APP="$SAIDA/AUTOSEG.AppDir"
VERSAO="$(python3 - <<'EOF'
import json
from pathlib import Path
try:
    print(json.loads(Path("versao.json").read_text(encoding="utf-8"))["versao"])
except Exception:
    print("dev")
EOF
)"

if ! python3 -m PyInstaller --version >/dev/null 2>&1; then
    echo "PyInstaller não encontrado. Crie um ambiente de build:" >&2
    echo "  python3 -m venv .venv-build" >&2
    echo "  .venv-build/bin/pip install pyinstaller" >&2
    exit 1
fi
if ! command -v appimagetool >/dev/null 2>&1; then
    echo "appimagetool não encontrado. Baixe em https://github.com/AppImage/appimagetool/releases" >&2
    exit 1
fi

rm -rf "$SAIDA"
mkdir -p "$APP/usr/bin" "$APP/usr/share/applications" \
         "$APP/usr/share/icons/hicolor/256x256/apps"

ARGUMENTOS=(
    --noconfirm --clean --windowed --name AUTOSEG
    --distpath "$SAIDA/dist"
    --workpath "$SAIDA/work"
    --specpath "$SAIDA"
    --add-data "$RAIZ/flavors/autoseg/branding/logo.png:flavors/autoseg/branding"
    --add-data "$RAIZ/flavors/autoseg/branding/icone.png:flavors/autoseg/branding"
    --add-data "$RAIZ/flavors/autoseg/branding/icone_devel.png:flavors/autoseg/branding"
    --add-data "$RAIZ/flavors/autoseg/config:flavors/autoseg/config"
    --add-data "$RAIZ/flavors/autoseg/templates:flavors/autoseg/templates"
    --add-data "$RAIZ/versao.json:."
    --add-data "$RAIZ/web:web"
    --add-data "$RAIZ/portal.js:."
    --collect-all reportlab
    --collect-all gi
    --paths "$RAIZ"
    "$RAIZ/flavors/autoseg/modules/gtk_app.py"
)
if [ -d "$RAIZ/.vendor/usr/lib/python3/dist-packages" ]; then
    ARGUMENTOS+=(--paths "$RAIZ/.vendor/usr/lib/python3/dist-packages")
fi
python3 -m PyInstaller "${ARGUMENTOS[@]}"

cp -a "$SAIDA/dist/AUTOSEG" "$APP/usr/bin/AUTOSEG"
cp "$RAIZ/packaging/appimage/AUTOSEG.desktop" "$APP/usr/share/applications/autoseg.desktop"
cp "$RAIZ/flavors/autoseg/branding/icone.png" "$APP/usr/share/icons/hicolor/256x256/apps/autoseg.png"

cat > "$APP/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export AUTOSEG_BASE="${AUTOSEG_BASE:-$HOME/.local/share/autoseg}"
mkdir -p "$AUTOSEG_BASE"
exec "$HERE/usr/bin/AUTOSEG/AUTOSEG" "$@"
EOF
chmod +x "$APP/AppRun"

ARCH=x86_64 appimagetool "$APP" "$SAIDA/AUTOSEG-$VERSAO-x86_64.AppImage"
echo "AppImage gerado em: $SAIDA/AUTOSEG-$VERSAO-x86_64.AppImage"
