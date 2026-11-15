"""Single source of truth for runtime paths and portal server settings.

Data never lives inside the repository:

- server production: ``/var/lib/autoseg`` (Linux), ``/Library/Application
  Support/AUTOSEG`` (macOS) or ``%PROGRAMDATA%/AUTOSEG`` (Windows);
- server DEV: ``<user data>/server-dev``;
- local GTK mode: ``<user data>/local``;
- user data: ``~/.local/share/autoseg`` on Linux, ``~/Library/Application
  Support/AUTOSEG`` on macOS or ``%LOCALAPPDATA%/AUTOSEG`` on Windows.

``AUTOSEG_BASE`` overrides the data directory and ``GESTAO_BANCO`` overrides
the SQLite file, preserving deployment compatibility. The Officina Web site defaults to 8866 in DEV and 8766 otherwise,
bound to 127.0.0.1 unless explicitly configured. The module is dependency free so every entry point can
import it without cycles.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def is_dev() -> bool:
    """True when the explicit DEV environment flag is enabled."""
    return os.environ.get('AUTOSEG_DEV') == '1'


def user_data_dir() -> Path:
    """Per-user application data directory.

    - macOS: ``~/Library/Application Support/AUTOSEG``
    - Linux: ``$XDG_DATA_HOME/autoseg`` or ``~/.local/share/autoseg``
    - Windows: ``%LOCALAPPDATA%/AUTOSEG``
    """
    raw = os.environ.get('AUTOSEG_USER_DATA')
    if raw:
        return Path(raw).expanduser()
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'AUTOSEG'
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') / 'AUTOSEG'
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'autoseg'


def server_data_dir() -> Path:
    """Server-owned data directory.

    Production defaults: ``/var/lib/autoseg`` (Linux) or
    ``/Library/Application Support/AUTOSEG`` (macOS). DEV uses a user-local
    ``server-dev`` directory so it works without root.
    """
    raw = os.environ.get('AUTOSEG_SERVER_DATA')
    if raw:
        return Path(raw).expanduser()
    if is_dev():
        return user_data_dir() / 'server-dev'
    if sys.platform == 'darwin':
        return Path('/Library/Application Support/AUTOSEG')
    if os.name == 'nt':
        return Path(os.environ.get('PROGRAMDATA') or 'C:/ProgramData') / 'AUTOSEG'
    return Path('/var/lib/autoseg')


def local_data_dir() -> Path:
    """Per-user local-mode data directory."""
    raw = os.environ.get('AUTOSEG_LOCAL_DATA')
    if raw:
        return Path(raw).expanduser()
    return user_data_dir() / 'local'


def _create_data_dir(path: Path) -> Path:
    """Create a private data directory and explain permission failures."""
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    except PermissionError as exc:
        raise PermissionError(
            f'Não foi possível criar {path}. Use uma pasta gravável pelo usuário '
            'do serviço ou defina AUTOSEG_SERVER_DATA/AUTOSEG_LOCAL_DATA.'
        ) from exc
    return path


def configure_server() -> Path:
    """Set the data environment for the headless/site server.

    Must run before importing ``officina.core.banco``: that module captures the
    database path at import time. Raises ``PermissionError`` with an actionable
    message when the system directory is not writable.
    """
    base = _create_data_dir(
        Path(os.environ.get('AUTOSEG_BASE') or server_data_dir()).expanduser())
    os.environ.setdefault('AUTOSEG_BASE', str(base))
    banco = os.environ.get('GESTAO_BANCO')
    if not banco:
        banco = str(base / ('dados_teste/autoseg_teste.db' if is_dev() else 'dados.db'))
        os.environ['GESTAO_BANCO'] = banco
    banco_path = Path(banco).expanduser()
    _create_data_dir(banco_path.parent)
    return base


def configure_local() -> Path:
    """Set the data environment for the local GTK mode."""
    base = _create_data_dir(
        Path(os.environ.get('AUTOSEG_BASE') or local_data_dir()).expanduser())
    os.environ.setdefault('AUTOSEG_BASE', str(base))
    os.environ.setdefault('GESTAO_BANCO', str(base / 'dados.db'))
    return base


def base_dir() -> Path:
    """Application/data directory.

    ``AUTOSEG_BASE`` wins when set. Otherwise the per-user local directory is
    used so an accidental direct import can never create a database in the
    repository.
    """
    raw = os.environ.get('AUTOSEG_BASE')
    return Path(raw).expanduser() if raw else local_data_dir()


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


def web_access_enabled() -> bool:
    """Whether the GTK app should start the Officina Web site.

    Default is on, preserving current behavior. ``AUTOSEG_WEB_ACCESS=0`` or
    the ``--no-web`` flag makes the desktop app run fully local, without
    opening the site port.
    """
    return os.environ.get('AUTOSEG_WEB_ACCESS', '1') != '0'
