"""Single source of truth for runtime paths and portal server settings.

This module reads environment variables only; it does not import application
modules. It preserves the historical defaults exactly:

- ``AUTOSEG_BASE``: data/application directory;
- ``GESTAO_BANCO``: SQLite database (``AUTOSEG_BASE/dados.db`` by default);
- client portal: 8865 in DEV, 8765 otherwise;
- provider portal: 8866 in DEV, 8766 otherwise;
- bind host: 127.0.0.1 unless explicitly configured.

Keeping the defaults here avoids divergent port/path logic in the GTK app,
the headless backend and the provider portal. It is intentionally dependency
free so it can be imported by every entry point without cycles.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def is_dev() -> bool:
    """True when the explicit DEV environment flag is enabled."""
    return os.environ.get('AUTOSEG_DEV') == '1'


def base_dir() -> Path:
    """Application/data directory, preserving ``AUTOSEG_BASE`` semantics."""
    raw = os.environ.get('AUTOSEG_BASE')
    return Path(raw).expanduser() if raw else Path(__file__).resolve().parents[2]


def database_path() -> Path:
    """SQLite database path, preserving ``GESTAO_BANCO`` semantics."""
    raw = os.environ.get('GESTAO_BANCO')
    return Path(raw).expanduser() if raw else base_dir() / 'dados.db'


def _env_port(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == '':
        return int(default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(f'{name} deve ser um número inteiro.') from None


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    https: bool = False


def provider_server(port: int | None = None, host: str | None = None) -> ServerConfig:
    """Provider portal settings.

    Precedence matches the previous implementation:
    - explicit ``host`` wins over ``PRESTADOR_BIND``;
    - ``PRESTADOR_PORT`` wins over the ``port`` argument;
    - otherwise the argument, then the DEV/MAIN default.
    """
    default_port = 8866 if is_dev() else 8766
    final_host = host or os.environ.get('PRESTADOR_BIND') or '127.0.0.1'
    if 'PRESTADOR_PORT' in os.environ and str(os.environ.get('PRESTADOR_PORT')).strip() != '':
        final_port = _env_port('PRESTADOR_PORT', default_port)
    elif port is not None:
        final_port = int(port)
    else:
        final_port = default_port
    return ServerConfig(final_host, final_port, provider_https())


def provider_https() -> bool:
    """Whether the provider portal should mark cookies Secure by default."""
    return os.environ.get('PRESTADOR_HTTPS') == '1'


def client_server(port: int | None = None, host: str | None = None) -> ServerConfig:
    """Client portal settings.

    Precedence matches the headless/GTK entry points: explicit ``host`` first,
    then ``CLIENTE_BIND``; ``CLIENTE_PORT`` overrides the argument; otherwise
    the argument or the DEV/MAIN default.
    """
    default_port = 8865 if is_dev() else 8765
    final_host = host or os.environ.get('CLIENTE_BIND') or '127.0.0.1'
    if 'CLIENTE_PORT' in os.environ and str(os.environ.get('CLIENTE_PORT')).strip() != '':
        final_port = _env_port('CLIENTE_PORT', default_port)
    elif port is not None:
        final_port = int(port)
    else:
        final_port = default_port
    return ServerConfig(final_host, final_port, False)


def web_access_enabled() -> bool:
    """Whether the GTK app should start local web portals.

    Default is on, preserving current behavior. ``AUTOSEG_WEB_ACCESS=0`` or
    the ``--no-web`` flag makes the desktop app run fully local, without
    opening ports 8765/8766.
    """
    return os.environ.get('AUTOSEG_WEB_ACCESS', '1') != '0'


def client_port(default: int = 8765) -> int:
    """Port used in links between the provider portal and the client portal.

    ``portal_prestador`` historically used 8765 as its fallback even in DEV,
    so the caller can pass that default explicitly while still honoring
    ``CLIENTE_PORT``.
    """
    return _env_port('CLIENTE_PORT', default)
