#!/bin/zsh
# Abre a interface GTK4/libadwaita no macOS.
set -e
cd "$(dirname "$0")"

export AUTOSEG_BASE="${AUTOSEG_BASE:-$HOME/gestaoservicos_MAIN}"
mkdir -p "$AUTOSEG_BASE"
export GESTAO_BANCO="${GESTAO_BANCO:-$AUTOSEG_BASE/dados.db}"

if [ ! -x .venv-gtk/bin/python ]; then
    if python3 -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")' >/dev/null 2>&1; then
        python3 -m venv --system-site-packages .venv-gtk
        .venv-gtk/bin/pip install --quiet 'reportlab>=4.2,<5' 'pillow>=10,<13' 'PyYAML>=6,<7'
    fi
fi

if [ -x .venv-gtk/bin/python ]; then
    PYTHON=".venv-gtk/bin/python"
else
    PYTHON="python3"
fi

if ! "$PYTHON" -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")' >/dev/null 2>&1; then
    echo "GTK4/PyGObject não encontrados."
    echo "Instale com: brew install python3 gtk4 libadwaita pygobject3 adwaita-icon-theme"
    echo "Depois execute este arquivo novamente."
    exit 1
fi

if ! "$PYTHON" -c 'import reportlab' >/dev/null 2>&1; then
    echo "Aviso: reportlab ausente; a geração de PDF ficará indisponível."
    echo "Instale com: $PYTHON -m pip install 'reportlab>=4.2,<5'"
fi

exec "$PYTHON" gtk_app.py "$@"
