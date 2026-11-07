"""Connection settings and service factory.

The GTK shell asks this module for an ``AppService``. Local mode stays the
default and preserves today's behavior. Remote mode is intentionally limited
to health until the server exposes the client use cases; it never falls back to
the local SQLite file silently.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

import runtime_config
from application.contracts import ServicoIndisponivelError


class ConnectionMode(str, Enum):
    LOCAL = 'local'
    REMOTE = 'remote'


@dataclass(frozen=True)
class ConnectionSettings:
    mode: ConnectionMode = ConnectionMode.LOCAL
    server_url: str = ''
    web_access: bool = True
    tunnel: bool = False
    last_user: str = ''

    def to_dict(self) -> dict:
        dados = asdict(self)
        dados['mode'] = self.mode.value
        return dados


def settings_path() -> Path:
    raw = os.environ.get('AUTOSEG_CONNECTION_FILE')
    if raw:
        return Path(raw).expanduser()
    return Path.home() / '.config' / 'autoseg' / 'connection.json'


def load_settings(path: Path | None = None) -> ConnectionSettings:
    destino = Path(path) if path else settings_path()
    dados = {}
    try:
        dados = json.loads(destino.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        dados = {}
    modo = str(dados.get('mode') or 'local').strip().lower()
    try:
        mode = ConnectionMode(modo)
    except ValueError:
        mode = ConnectionMode.LOCAL
    env_mode = os.environ.get('AUTOSEG_CONNECTION_MODE', '').strip().lower()
    if env_mode in (ConnectionMode.LOCAL.value, ConnectionMode.REMOTE.value):
        mode = ConnectionMode(env_mode)
    server_url = os.environ.get('AUTOSEG_SERVER_URL', '').strip() or str(
        dados.get('server_url') or '').strip()
    if 'AUTOSEG_WEB_ACCESS' in os.environ:
        web_access = runtime_config.web_access_enabled()
    else:
        web_access = bool(dados.get('web_access', True))
    return ConnectionSettings(
        mode=mode,
        server_url=server_url,
        web_access=web_access,
        tunnel=bool(dados.get('tunnel', False)),
        last_user=str(dados.get('last_user') or ''),
    )


def save_settings(settings: ConnectionSettings, path: Path | None = None) -> Path:
    destino = Path(path) if path else settings_path()
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + '.tmp')
    temporario.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
        encoding='utf-8')
    temporario.replace(destino)
    return destino


def build_service(banco=None, settings: ConnectionSettings | None = None):
    """Return the application service selected by the current settings."""
    config = settings or load_settings()
    if config.mode is ConnectionMode.LOCAL:
        from application.local_service import LocalService
        return LocalService(banco)
    if not config.server_url:
        raise ServicoIndisponivelError(
            'Modo remoto sem URL de servidor configurada.',
            'Conexão não configurada')
    from application.http_service import HttpService
    return HttpService(config.server_url)
