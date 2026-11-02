#!/usr/bin/env bash
# Túnel SSH para os portais do macOS. Deixe o backend rodando no Mac.
# Uso: ./scripts/tunel_mac.sh
set -euo pipefail
REMOTE="${AUTOSEG_MAC_SSH:-idkosx@100.71.106.7}"

exec ssh -N \
    -L 8765:127.0.0.1:8765 \
    -L 8766:127.0.0.1:8766 \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    "$REMOTE"
