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
    role: str = ''
    context_label: str = ''
    permissions: frozenset[str] = frozenset()
    navigation_ids: frozenset[str] = frozenset()

    def can(self, permission: str) -> bool:
        return ('*' in self.permissions or permission in self.permissions
                or any(p.endswith('.*') and permission.startswith(p[:-1])
                       for p in self.permissions))

    @property
    def remote(self) -> bool:
        return self.mode == ConnectionMode.REMOTE.value

    def to_dict(self) -> dict:
        data = asdict(self)
        data['permissions'] = sorted(self.permissions)
        data['navigation_ids'] = sorted(self.navigation_ids)
        return data

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
                role=str(dados.get('role') or ('admin' if dados.get('admin') else 'employee')),
                context_label=str(dados.get('context_label') or 'Portal do prestador'),
                permissions=frozenset(str(p) for p in (dados.get('permissions') or ())),
                navigation_ids=frozenset(str(n) for n in (dados.get('navigation_ids') or ())),
            )
        except (TypeError, ValueError):
            return None


def navigation_for_session(sections=None, sessao: Sessao | None = None, *, web_enabled=False):
    """Project supplied canonical sections; generic core never imports a flavor."""
    if sessao is None:
        return list(sections or ())
    # The AUTOSEG adapter owns the canonical ITEMS registry and passes the
    # ordered provider sections. Missing registry fails closed by showing none.
    allowed = []
    for item in sections or ():
        if 'gtk' not in item.surfaces or not item.gtk_page:
            continue
        permission = item.permission
        if permission == '*' and not sessao.can('provider.manage.all'):
            continue
        if permission and permission != '*' and not sessao.can(permission):
            continue
        if sessao.remote and sessao.navigation_ids and item.id not in sessao.navigation_ids:
            continue
        if not web_enabled and item.gtk_page == 'portal':
            continue
        allowed.append(item)
    # The GNOME mapping only changes presentation; permission and ordering
    # come solely from the caller's already-resolved registry entries.
    icons = {'home':'go-home-symbolic', 'users':'system-users-symbolic',
             'clipboard':'document-edit-symbolic', 'history':'document-open-recent-symbolic',
             'wallet':'accessories-calculator-symbolic', 'receipt':'x-office-document-symbolic',
             'mail':'mail-send-symbolic', 'wrench':'view-list-symbolic',
             'layout':'emblem-important-symbolic', 'building':'view-grid-symbolic',
             'network':'network-wired-symbolic'}
    return [(item.gtk_page, item.label, icons.get(item.icon,'package-x-generic-symbolic'))
            for item in allowed]


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
