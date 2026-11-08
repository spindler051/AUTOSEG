"""Client-side session file for the GTK desktop.

The file stores only a revocable server token and non-secret display data. It
never stores the provider password. On macOS/Linux the file is written with
mode 0600; moving the token to Keychain/libsecret is a future hardening step.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from officina.application.connection import ConnectionMode


@dataclass(frozen=True)
class Sessao:
    mode: str
    prestador_id: int
    nome: str
    email: str
    admin: bool
    server_url: str = ''
    token: str = ''
    expira_em: str = ''

    @property
    def remote(self) -> bool:
        return self.mode == ConnectionMode.REMOTE.value

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, dados: dict) -> 'Sessao | None':
        try:
            mode = str(dados.get('mode') or '')
            if mode not in (ConnectionMode.LOCAL.value,
                            ConnectionMode.REMOTE.value):
                return None
            return cls(
                mode=mode,
                prestador_id=int(dados.get('prestador_id') or 0),
                nome=str(dados.get('nome') or ''),
                email=str(dados.get('email') or ''),
                admin=bool(dados.get('admin')),
                server_url=str(dados.get('server_url') or '').strip(),
                token=str(dados.get('token') or ''),
                expira_em=str(dados.get('expira_em') or ''),
            )
        except (TypeError, ValueError):
            return None


def session_path() -> Path:
    raw = os.environ.get('AUTOSEG_SESSION_FILE')
    if raw:
        return Path(raw).expanduser()
    return Path.home() / '.config' / 'autoseg' / 'session.json'


def salvar_sessao(sessao: Sessao, caminho: Path | None = None) -> Path | None:
    """Persist only a revocable remote token; local logins are not saved."""
    if not sessao.remote or not sessao.token:
        limpar_sessao(caminho)
        return None
    destino = Path(caminho) if caminho else session_path()
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(destino.parent, 0o700)
    except OSError:
        pass
    temporario = destino.with_suffix(destino.suffix + '.tmp')
    temporario.write_text(
        json.dumps(sessao.to_dict(), ensure_ascii=False, indent=2),
        encoding='utf-8')
    try:
        os.chmod(temporario, 0o600)
    except OSError:
        pass
    temporario.replace(destino)
    return destino


def carregar_sessao(caminho: Path | None = None) -> Sessao | None:
    destino = Path(caminho) if caminho else session_path()
    try:
        dados = json.loads(destino.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return None
    return Sessao.from_dict(dados) if isinstance(dados, dict) else None


def limpar_sessao(caminho: Path | None = None) -> None:
    destino = Path(caminho) if caminho else session_path()
    try:
        destino.unlink()
    except OSError:
        pass
