#!/usr/bin/env bash
# Executa o AUTOSEG no display físico/virtual do VM usando Cage + DRM.
# O app GTK4 usa Wayland nativo; não há Xvfb nem Xwayland no caminho.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v cage >/dev/null 2>&1; then
    echo "Cage não encontrado. Instale o pacote 'cage'." >&2
    exit 1
fi
if ! command -v setfacl >/dev/null 2>&1; then
    echo "setfacl não encontrado. Instale o pacote 'acl'." >&2
    exit 1
fi

CARD="${WLR_DRM_DEVICES:-/dev/dri/card1}"
if [ ! -e "$CARD" ]; then
    echo "Dispositivo DRM não encontrado: $CARD" >&2
    exit 1
fi

# O Cage abre DRM, o VT ativo e os dispositivos de entrada via libseat.
# Em VM/headless é mais simples liberar ACLs para o usuário atual do que
# exigir uma sessão logind completa.
sudo setfacl -m "u:${USER}:rw" "$CARD" /dev/tty0 /dev/tty1 /run/seatd.sock 2>/dev/null || true
sudo setfacl -m "u:${USER}:rw" /dev/input/event* /dev/input/mice 2>/dev/null || true

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/autoseg-runtime-$(id -u)}"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
export WLR_BACKENDS="drm,libinput"
export WLR_DRM_DEVICES="$CARD"
# virtio-gpu desta VM desenha o cursor de hardware invertido/deslocado;
# o cursor de software usa a cena do compositor.
export WLR_NO_HARDWARE_CURSORS=1
# Não forçar GTK_USE_PORTAL=0: o libadwaita lê tema escuro/accent do
# org.gnome.desktop.interface via xdg-desktop-portal nesta sessão dbus.

exec dbus-run-session -- cage -s -- python3 gtk_app.py "$@"
