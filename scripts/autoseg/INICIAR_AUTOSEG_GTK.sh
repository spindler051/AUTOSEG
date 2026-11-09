#!/usr/bin/env bash
# Abre a interface GTK4/libadwaita diretamente (Linux).
set -euo pipefail
cd "$(dirname "$0")/../.."
if command -v dbus-run-session >/dev/null 2>&1; then
    if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] || [ "${XDG_SESSION_TYPE:-}" = "tty" ]; then
        exec dbus-run-session -- python3 flavors/autoseg/modules/gtk_app.py "$@"
    fi
fi
exec python3 flavors/autoseg/modules/gtk_app.py "$@"
