#!/bin/zsh
# Abre a interface GTK4/libadwaita no macOS.
# Usa o Python que tiver PyGObject/GTK4 instalado (MacPorts ou Homebrew).
set -e
cd "$(dirname "$0")/../.."

export AUTOSEG_BASE="${AUTOSEG_BASE:-$HOME/gestaoservicos_MAIN}"
mkdir -p "$AUTOSEG_BASE"
export GESTAO_BANCO="${GESTAO_BANCO:-$AUTOSEG_BASE/dados.db}"

# MacPorts e Homebrew instalam ícones/typelibs fora dos caminhos padrão.
export XDG_DATA_DIRS="/opt/local/share:/usr/local/share:${XDG_DATA_DIRS:-/usr/share}"
export GI_TYPELIB_PATH="/opt/local/lib/girepository-1.0:/usr/local/lib/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"

if [ ! -f "$AUTOSEG_BASE/completude.yaml" ] && [ -f completude.yaml ]; then
    cp completude.yaml "$AUTOSEG_BASE/completude.yaml"
fi
if [ ! -f "$AUTOSEG_BASE/composicao.yaml" ] && [ -f composicao_padrao.yaml ]; then
    cp composicao_padrao.yaml "$AUTOSEG_BASE/composicao.yaml"
fi

funciona_gtk() {
    "$1" -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")' >/dev/null 2>&1
}

BASE_PYTHON=""
for CANDIDATO in \
    /opt/local/bin/python3.14 \
    /opt/local/bin/python3.13 \
    /opt/local/bin/python3.12 \
    /usr/local/bin/python3 \
    /opt/homebrew/bin/python3 \
    python3; do
    if command -v "$CANDIDATO" >/dev/null 2>&1 && funciona_gtk "$CANDIDATO"; then
        BASE_PYTHON="$CANDIDATO"
        break
    fi
done

if [ -z "$BASE_PYTHON" ]; then
    echo "GTK4/PyGObject não encontrados."
    echo "MacPorts: sudo port install gtk4 +quartz libadwaita py-gobject3 adwaita-icon-theme"
    echo "Homebrew (Intel/legacy): brew install gtk4 libadwaita pygobject3 adwaita-icon-theme"
    exit 1
fi

# Recria o venv se ele não enxergar o PyGObject do sistema.
if [ -x .venv-gtk/bin/python ] && ! funciona_gtk .venv-gtk/bin/python; then
    rm -rf .venv-gtk
fi
if [ ! -x .venv-gtk/bin/python ]; then
    "$BASE_PYTHON" -m venv --system-site-packages .venv-gtk
    .venv-gtk/bin/pip install --quiet 'reportlab>=4.2,<5' 'pillow>=10,<13' 'PyYAML>=6,<7'
fi
PYTHON=".venv-gtk/bin/python"

if ! "$PYTHON" -c 'import reportlab' >/dev/null 2>&1; then
    echo "Aviso: reportlab ausente; a geração de PDF ficará indisponível." >&2
    echo "Instale com: $PYTHON -m pip install 'reportlab>=4.2,<5'" >&2
fi

exec "$PYTHON" flavors/autoseg/modules/gtk_app.py "$@"
