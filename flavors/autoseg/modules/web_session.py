"""In-memory unified web sessions; no HTTP, cookies, or persistence."""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

from flavors.autoseg.modules import accounts, identity, login_flags
from officina.application.object_policy import Principal
from officina.core import prestadores_ext as ext

COOKIE_NAME = login_flags.COOKIE_NAME
SESSION_TTL = 28800


@dataclass(frozen=True, repr=False)
class SessionData:
    account_id: int | None
    identity: identity.Identity = field(repr=False)
    membership: identity.Membership = field(repr=False)
    principal: Principal = field(repr=False)
    credential: str = field(repr=False)
    source: str
    csrf: str = field(repr=False)
    telemetry_session: str = field(repr=False)
    created_at: float
    expires_at: float

    def __repr__(self) -> str:
        # The complete session, including nested identity PII, is sensitive.
        return "SessionData(<redacted>)"


_LOCK = threading.Lock()
_SESSIONS: dict[str, SessionData] = {}


def current_credential(banco, source: str, account_id: int | None,
                       identity_record: identity.Identity) -> str | None:
    """Read the current hash without exposing it through logs or errors."""
    try:
        if source == "account":
            if account_id is None:
                return None
            account = accounts.load_account(banco, account_id)
            return account.password_hash if account and account.active else None
        if source != "legacy" or identity_record.kind not in ("provider", "client"):
            return None
        table = "prestadores" if identity_record.kind == "provider" else "v9_usuarios"
        with ext.db(banco) as connection:
            row = connection.execute(
                f"SELECT senha_hash, ativo FROM {table} WHERE id=?",
                (identity_record.id,),
            ).fetchone()
            if row is None or not bool(row["ativo"]):
                return None
            if identity_record.kind == "provider":
                columns = {r[1] for r in connection.execute("PRAGMA table_info(prestadores)")}
                if "excluido" in columns:
                    state = connection.execute(
                        "SELECT excluido FROM prestadores WHERE id=?", (identity_record.id,)
                    ).fetchone()
                    if state is None or bool(state[0]):
                        return None
            return row["senha_hash"]
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return None
    except Exception:
        # A read failure must invalidate the session, never grant access.
        return None


def _account_binding(banco, account_id, identity_record: identity.Identity,
                     membership: identity.Membership) -> bool:
    """Check that one active account link still maps to this identity and role."""
    try:
        account = accounts.load_account(banco, account_id)
        link = accounts.account_link(banco, account_id)
        if account is None or not account.active or link is None or not link.active:
            return False
        if (link.provider_org_id != membership.provider_org_id
                or link.role != membership.role):
            return False
        if identity_record.kind == "provider":
            return (link.link_type == "provider"
                    and link.provider_id == identity_record.id)
        if identity_record.kind == "client":
            return (link.link_type == "client"
                    and link.client_user_id == identity_record.id)
        return False
    except Exception:
        return False


def _active(banco, data: SessionData) -> bool:
    """Check activation and link validity without silently upgrading roles."""
    if not data.identity.active or not data.membership.active or not data.principal.active:
        return False
    try:
        current = identity.load_identity(banco, data.identity.kind, data.identity.id)
        if current is None or not current.active:
            return False
        if data.source == "account":
            if data.account_id is None:
                return False
            # Reject changed or removed links; never manufacture a new principal.
            return _account_binding(banco, data.account_id, data.identity,
                                    data.membership)
        return data.source == "legacy"
    except Exception:
        return False


def create(banco, account_id, identity_record, membership, principal,
           credential, source, ttl=SESSION_TTL) -> tuple[str, SessionData]:
    """Store one opaque session, bound to the current credential hash."""
    if source not in ("account", "legacy"):
        raise ValueError("Invalid session source.")
    if not isinstance(credential, str) or not credential:
        raise ValueError("Invalid credential.")
    if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or not 0 < ttl <= SESSION_TTL:
        raise ValueError("Invalid session lifetime.")
    if source == "account" and account_id is None:
        raise ValueError("Missing account.")
    if source == "account" and (not isinstance(account_id, int)
                                or isinstance(account_id, bool)):
        raise ValueError("Invalid account.")
    if source == "legacy" and account_id is not None:
        raise ValueError("Unexpected account.")
    if (not isinstance(identity_record, identity.Identity)
            or not isinstance(membership, identity.Membership)
            or not isinstance(principal, Principal)):
        raise ValueError("Invalid session identity.")
    expected = identity.to_principal(identity_record, membership)
    if (not expected.active or not principal.active
            or principal.account_id != expected.account_id
            or principal.role != expected.role
            or principal.provider_id != expected.provider_id
            or principal.client_id != expected.client_id
            or principal.organization_id != expected.organization_id):
        raise ValueError("Invalid session principal.")
    if source == "account" and not _account_binding(
            banco, account_id, identity_record, membership):
        raise ValueError("Invalid account link.")
    if current_credential(banco, source, account_id, identity_record) != credential:
        raise ValueError("Credential mismatch.")
    now = time.time()
    data = SessionData(account_id, identity_record, membership, principal,
                       credential, source, secrets.token_urlsafe(32),
                       secrets.token_urlsafe(24), now, now + ttl)
    with _LOCK:
        if len(_SESSIONS) > 2000:
            _prune_locked(now)
        token = secrets.token_urlsafe(36)
        while token in _SESSIONS:
            token = secrets.token_urlsafe(36)
        _SESSIONS[token] = data
    return token, data


def resolve(banco, token: str | None) -> SessionData | None:
    """Validate expiration, activation, and credential before returning data."""
    if not isinstance(token, str) or not token:
        return None
    with _LOCK:
        data = _SESSIONS.get(token)
        if data is None:
            return None
        if time.time() >= data.expires_at:
            _SESSIONS.pop(token, None)
            return None
    if (current_credential(banco, data.source, data.account_id, data.identity)
            != data.credential or not _active(banco, data)):
        revoke(token)
        return None
    with _LOCK:
        # A concurrent revoke must win over a slow database read.
        return data if _SESSIONS.get(token) is data and time.time() < data.expires_at else None


def revoke(token: str | None) -> None:
    if not isinstance(token, str):
        return
    with _LOCK:
        _SESSIONS.pop(token, None)


def revoke_account(account_id: int) -> None:
    with _LOCK:
        for token, data in tuple(_SESSIONS.items()):
            if data.account_id is not None and data.account_id == account_id:
                del _SESSIONS[token]


def revoke_identity(kind: str, identity_id: int) -> None:
    with _LOCK:
        for token, data in tuple(_SESSIONS.items()):
            if data.identity.kind == kind and data.identity.id == identity_id:
                del _SESSIONS[token]


def _prune_locked(now: float) -> None:
    for token, data in tuple(_SESSIONS.items()):
        if now >= data.expires_at:
            del _SESSIONS[token]


def prune() -> None:
    with _LOCK:
        _prune_locked(time.time())


def clear() -> None:
    """Clear the process-local session map for tests."""
    with _LOCK:
        _SESSIONS.clear()
