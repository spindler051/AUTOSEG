"""Opt-in SQLite unified sessions; memory fallback preserves rollout compatibility."""
from __future__ import annotations

import secrets
import hashlib
import json
import os
import sqlite3
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
    credential: str = field(repr=False)  # SHA-256 credential fingerprint when durable
    source: str
    csrf: str = field(repr=False)
    telemetry_session: str = field(repr=False)
    created_at: float
    expires_at: float

    def __repr__(self) -> str:
        # The complete session, including nested identity PII, is sensitive.
        return "SessionData(<redacted>)"

    @property
    def context(self):
        from officina.application.contracts import SessionContext
        return SessionContext.from_identity(
            self.identity, self.membership, self.principal,
            account_id=self.account_id)


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
            return accounts.credential_hash(banco, account) if account else None
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
        if account is None or not accounts.effective_active(banco, account):
            return False
        current_identity = accounts.identity_for_account(banco, account_id)
        current_membership = accounts.membership_for_account(banco, account_id)
        if current_identity is None or current_membership is None:
            return False
        if (current_identity.kind != identity_record.kind
                or current_identity.id != identity_record.id
                or not current_membership.active):
            return False
        # Reject changed or removed links; never manufacture a new principal.
        return (current_membership.role == membership.role
                and current_membership.provider_org_id == membership.provider_org_id
                and current_membership.provider_id == membership.provider_id
                and current_membership.client_id == membership.client_id
                and current_membership.client_org_ids == membership.client_org_ids)
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
        if data.source == "legacy":
            # A role change must end the session instead of silently keeping or
            # upgrading the legacy role for the remaining lifetime.
            current_memberships = identity.memberships(banco, current)
            if len(current_memberships) != 1:
                return False
            current_membership = current_memberships[0]
            return (current_membership.role == data.membership.role
                    and current_membership.provider_org_id == data.membership.provider_org_id
                    and current_membership.provider_id == data.membership.provider_id
                    and current_membership.client_id == data.membership.client_id
                    and current_membership.client_org_ids == data.membership.client_org_ids)
        return False
    except Exception:
        return False



_TRUE = frozenset({'1', 'true', 'on', 'yes'})


def durable_enabled() -> bool:
    return str(os.environ.get('AUTOSEG_WEB_SESSION_DURABLE', '0')).strip().lower() in _TRUE


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def install(banco) -> None:
    """Idempotent explicit schema creation. No migration of desktop sessions."""
    with ext.db(banco) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS web_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            account_id INTEGER,
            source TEXT NOT NULL CHECK(source IN ('account','legacy')),
            identity_kind TEXT NOT NULL CHECK(identity_kind IN ('provider','client')),
            identity_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            provider_org_id TEXT,
            provider_id INTEGER,
            client_id INTEGER,
            client_org_ids TEXT NOT NULL DEFAULT '[]',
            csrf TEXT NOT NULL,
            telemetry_session TEXT NOT NULL,
            credential_fingerprint TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL
        )""")
        c.execute('CREATE INDEX IF NOT EXISTS idx_web_sessions_account ON web_sessions(account_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_web_sessions_identity ON web_sessions(identity_kind, identity_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_web_sessions_expiry ON web_sessions(expires_at)')


def _validate_create(banco, account_id, identity_record, membership, principal,
                     credential, source, ttl):
    if source not in ('account', 'legacy'):
        raise ValueError('Invalid session source.')
    if not isinstance(credential, str) or not credential:
        raise ValueError('Invalid credential.')
    if (not isinstance(ttl, (int, float)) or isinstance(ttl, bool)
            or not 0 < ttl <= SESSION_TTL):
        raise ValueError('Invalid session lifetime.')
    if source == 'account' and (type(account_id) is not int or account_id <= 0):
        raise ValueError('Invalid account.')
    if source == 'legacy' and account_id is not None:
        raise ValueError('Unexpected account.')
    if (not isinstance(identity_record, identity.Identity)
            or not isinstance(membership, identity.Membership)
            or not isinstance(principal, Principal)):
        raise ValueError('Invalid session identity.')
    expected = identity.to_principal(identity_record, membership)
    if (not expected.active or not principal.active
            or principal.account_id != expected.account_id
            or principal.role != expected.role
            or principal.provider_id != expected.provider_id
            or principal.client_id != expected.client_id
            or principal.organization_id != expected.organization_id
            or principal.client_org_ids != expected.client_org_ids):
        raise ValueError('Invalid session principal.')
    if source == 'account' and not _account_binding(
            banco, account_id, identity_record, membership):
        raise ValueError('Invalid account link.')
    if source == 'legacy':
        actual = identity.load_identity(banco, identity_record.kind, identity_record.id)
        candidates = identity.memberships(banco, actual) if actual else ()
        if (actual is None or not actual.active or len(candidates) != 1
                or candidates[0] != membership):
            raise ValueError('Invalid legacy membership.')
    if current_credential(banco, source, account_id, identity_record) != credential:
        raise ValueError('Credential mismatch.')


def create(banco, account_id, identity_record, membership, principal,
           credential, source, ttl=SESSION_TTL) -> tuple[str, SessionData]:
    """Store only token and credential fingerprints in durable mode."""
    _validate_create(banco, account_id, identity_record, membership, principal,
                     credential, source, ttl)
    now = time.time()
    token = secrets.token_urlsafe(36)
    csrf = secrets.token_urlsafe(32)
    telemetry = secrets.token_urlsafe(24)
    fingerprint = _hash(credential)
    data = SessionData(account_id, identity_record, membership, principal,
                       fingerprint if durable_enabled() else credential, source,
                       csrf, telemetry, now, now + ttl)
    if durable_enabled():
        with ext.db(banco) as c:
            # install is a startup responsibility; missing schema fails closed.
            c.execute("""INSERT INTO web_sessions
                (token_hash,account_id,source,identity_kind,identity_id,role,
                 provider_org_id,provider_id,client_id,client_org_ids,csrf,
                 telemetry_session,credential_fingerprint,created_at,expires_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (_hash(token), account_id, source, identity_record.kind,
                 identity_record.id, membership.role, membership.provider_org_id,
                 membership.provider_id, membership.client_id,
                 json.dumps(sorted(membership.client_org_ids)),csrf,telemetry,
                 fingerprint,now,now+ttl))
    else:
        with _LOCK:
            if len(_SESSIONS) > 2000:
                _prune_locked(now)
            while token in _SESSIONS:
                token = secrets.token_urlsafe(36)
            _SESSIONS[token] = data
    return token, data


def _resolve_sqlite(banco, token: str) -> SessionData | None:
    token_hash = _hash(token)
    try:
        with ext.db(banco) as c:
            row = c.execute('SELECT * FROM web_sessions WHERE token_hash=?',
                            (token_hash,)).fetchone()
        if row is None:
            return None
        now = time.time()
        if row['expires_at'] <= now:
            revoke(banco, token)
            return None
        org_ids = json.loads(row['client_org_ids'])
        if (not isinstance(org_ids, list)
                or any(type(x) is not int or x <= 0 for x in org_ids)
                or len(set(org_ids)) != len(org_ids)):
            revoke(banco, token)
            return None
        kind = row['identity_kind']
        ident = identity.load_identity(banco, kind, row['identity_id'])
        if ident is None or not ident.active:
            revoke(banco, token)
            return None
        source = row['source']
        aid = row['account_id']
        if source == 'account':
            if aid is None:
                revoke(banco, token)
                return None
            membership = accounts.membership_for_account(banco, aid)
        elif source == 'legacy' and aid is None:
            candidates = identity.memberships(banco, ident)
            membership = candidates[0] if len(candidates) == 1 else None
        else:
            revoke(banco, token)
            return None
        if membership is None:
            revoke(banco, token)
            return None
        p = identity.to_principal(ident, membership)
        if (not p.active or membership.role != row['role']
                or membership.provider_org_id != row['provider_org_id']
                or membership.provider_id != row['provider_id']
                or membership.client_id != row['client_id']
                or membership.client_org_ids != frozenset(org_ids)
                or (source == 'account'
                    and not _account_binding(banco,aid,ident,membership))):
            revoke(banco,token)
            return None
        current = current_credential(banco,source,aid,ident)
        if not current or _hash(current) != row['credential_fingerprint']:
            revoke(banco,token)
            return None
        # Re-query after potentially slow validation: a concurrent revoke wins.
        with ext.db(banco) as c:
            still_valid = c.execute(
                'SELECT 1 FROM web_sessions WHERE token_hash=? AND expires_at>?',
                (token_hash,time.time())).fetchone()
        if not still_valid:
            return None
        return SessionData(aid,ident,membership,p,row['credential_fingerprint'],
                           source,row['csrf'],row['telemetry_session'],
                           row['created_at'],row['expires_at'])
    except (ValueError, TypeError, KeyError):
        try:
            revoke(banco, token)
        except sqlite3.Error:
            pass
        return None
    except sqlite3.Error:
        return None


def resolve(banco, token: str | None) -> SessionData | None:
    if not isinstance(token, str) or not token:
        return None
    if durable_enabled():
        return _resolve_sqlite(banco,token)
    with _LOCK:
        data = _SESSIONS.get(token)
        if data is None:
            return None
        if time.time() >= data.expires_at:
            _SESSIONS.pop(token,None)
            return None
    if (current_credential(banco,data.source,data.account_id,data.identity)
            != data.credential or not _active(banco,data)):
        revoke(banco,token)
        return None
    with _LOCK:
        return data if _SESSIONS.get(token) is data and time.time() < data.expires_at else None


def revoke(banco, token: str | None = None) -> None:
    """Two-argument durable API; one-argument compatibility is memory-only."""
    if token is None:
        token = banco
        banco = None
    if not isinstance(token,str) or not token:
        return
    if banco is not None and durable_enabled():
        with ext.db(banco) as c:
            c.execute('DELETE FROM web_sessions WHERE token_hash=?',(_hash(token),))
    else:
        with _LOCK:
            _SESSIONS.pop(token,None)


def revoke_account(banco, account_id: int | None = None) -> None:
    if account_id is None:
        account_id,banco = banco,None
    if banco is not None and durable_enabled():
        with ext.db(banco) as c:
            c.execute('DELETE FROM web_sessions WHERE account_id=?',(account_id,))
    else:
        with _LOCK:
            for token,data in tuple(_SESSIONS.items()):
                if data.account_id == account_id and data.account_id is not None:
                    del _SESSIONS[token]


def revoke_identity(banco, kind: str | int, identity_id: int | None = None) -> None:
    if identity_id is None:
        identity_id,kind,banco = kind,banco,None
    if banco is not None and durable_enabled():
        with ext.db(banco) as c:
            c.execute('DELETE FROM web_sessions WHERE identity_kind=? AND identity_id=?',
                      (kind,identity_id))
    else:
        with _LOCK:
            for token,data in tuple(_SESSIONS.items()):
                if data.identity.kind == kind and data.identity.id == identity_id:
                    del _SESSIONS[token]


def _prune_locked(now: float) -> None:
    for token,data in tuple(_SESSIONS.items()):
        if now >= data.expires_at:
            del _SESSIONS[token]


def prune(banco=None) -> None:
    if banco is not None and durable_enabled():
        with ext.db(banco) as c:
            c.execute('DELETE FROM web_sessions WHERE expires_at<=?',(time.time(),))
    else:
        with _LOCK:
            _prune_locked(time.time())


def clear(banco=None) -> None:
    """Tests only. Never called by application startup."""
    if banco is not None:
        with ext.db(banco) as c:
            c.execute('DELETE FROM web_sessions')
    with _LOCK:
        _SESSIONS.clear()
