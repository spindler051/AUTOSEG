"""Opt-in account storage and legacy import; no login or session integration."""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from officina.core import prestadores_ext as ext
from flavors.autoseg.modules import identity

IDENTIFIER_TYPES = ("email", "cpf", "phone", "nametag")


@dataclass(frozen=True)
class Account:
    id: int
    display_name: str
    password_hash: str
    active: bool
    created_at: str
    updated_at: str
    password_changed_at: str | None = None


@dataclass(frozen=True)
class AccountIdentifier:
    id: int
    account_id: int
    type: str
    value: str
    normalized: str
    verified: bool
    is_primary: bool


@dataclass(frozen=True)
class AccountLink:
    id: int
    account_id: int
    provider_org_id: str
    link_type: str
    role: str
    provider_id: int | None
    client_user_id: int | None
    client_id: int | None
    legacy_provider_id: int | None
    legacy_client_user_id: int | None
    active: bool


@dataclass(frozen=True)
class LoginPolicy:
    allowed_identifier_types: tuple[str, ...]
    password_min_length: int
    require_letter_number: bool


@dataclass(frozen=True)
class MigrationReport:
    dry_run: bool
    providers: int
    clients: int
    accounts_created: int
    accounts_updated: int
    identifiers_created: int
    identifiers_skipped: int
    conflicts: tuple[dict, ...]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS accounts (
      id INTEGER PRIMARY KEY AUTOINCREMENT, display_name TEXT NOT NULL DEFAULT '',
      password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, password_changed_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS account_identifiers (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      type TEXT NOT NULL CHECK(type IN ('email','cpf','phone','nametag')),
      value TEXT NOT NULL, normalized TEXT NOT NULL,
      verified INTEGER NOT NULL DEFAULT 0, is_primary INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL, UNIQUE(type, normalized))""",
    "CREATE INDEX IF NOT EXISTS idx_account_identifiers_account ON account_identifiers(account_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_account_identifiers_primary ON account_identifiers(account_id) WHERE is_primary=1",
    """CREATE TABLE IF NOT EXISTS account_links (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      account_id INTEGER NOT NULL UNIQUE REFERENCES accounts(id) ON DELETE CASCADE,
      provider_org_id TEXT NOT NULL DEFAULT 'autoseg',
      link_type TEXT NOT NULL CHECK(link_type IN ('provider','client')),
      role TEXT NOT NULL CHECK(role IN ('admin','employee','customer')),
      provider_id INTEGER, client_user_id INTEGER, client_id INTEGER,
      legacy_provider_id INTEGER UNIQUE, legacy_client_user_id INTEGER UNIQUE,
      active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
      CHECK ((link_type='provider' AND role IN ('admin','employee')
              AND provider_id IS NOT NULL AND client_user_id IS NULL AND client_id IS NULL)
             OR (link_type='client' AND role='customer'
                 AND provider_id IS NULL AND client_user_id IS NOT NULL)))""",
    """CREATE TABLE IF NOT EXISTS login_policy (
      id INTEGER PRIMARY KEY CHECK(id=1), allowed_identifier_types TEXT NOT NULL,
      password_min_length INTEGER NOT NULL DEFAULT 12,
      require_letter_number INTEGER NOT NULL DEFAULT 1,
      updated_at TEXT NOT NULL)""",
)


def _install(c):
    for statement in _SCHEMA:
        c.execute(statement)
    c.execute("INSERT OR IGNORE INTO login_policy(id, allowed_identifier_types, updated_at) VALUES (1, ?, ?)",
              (json.dumps(["email", "cpf"]), _now()))


def install(banco) -> None:
    with ext.db(banco) as c:
        _install(c)


def normalize_identifier(kind: str, value: str) -> str:
    if kind not in IDENTIFIER_TYPES or not isinstance(value, str):
        raise ValueError("Invalid identifier")
    value = value.strip()
    if kind == "email":
        result = value.casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", result):
            raise ValueError("Invalid email")
        return result
    if kind in ("cpf", "phone"):
        if not re.fullmatch(r"[\d\s.()/+\-]+", value):
            raise ValueError("Invalid document or phone")
        result = re.sub(r"\D", "", value)
        if kind == "cpf" and len(result) != 11:
            raise ValueError("Invalid document or phone")
        if kind == "phone" and not 10 <= len(result) <= 13:
            raise ValueError("Invalid document or phone")
        return result
    result = value.casefold()
    if not re.fullmatch(r"[a-z0-9._-]{3,30}", result):
        raise ValueError("Invalid nametag")
    return result


def _policy(c):
    row = c.execute("SELECT * FROM login_policy WHERE id=1").fetchone()
    if row is None:
        return LoginPolicy(("email", "cpf"), 12, True)
    try:
        allowed = json.loads(row["allowed_identifier_types"])
        if (not isinstance(allowed, list) or not allowed
                or any(t not in IDENTIFIER_TYPES for t in allowed)
                or len(allowed) != len(set(allowed))):
            raise ValueError("Invalid policy")
        return LoginPolicy(tuple(allowed), int(row["password_min_length"]), bool(row["require_letter_number"]))
    except (ValueError, TypeError):
        return LoginPolicy(("email", "cpf"), 12, True)


def login_policy(banco) -> LoginPolicy:
    with ext.db(banco) as c:
        if not _table(c, "login_policy"):
            return LoginPolicy(("email", "cpf"), 12, True)
        return _policy(c)


def save_login_policy(banco, allowed_identifier_types, password_min_length=12,
                      require_letter_number=True) -> LoginPolicy:
    try:
        kinds = tuple(allowed_identifier_types)
    except TypeError as exc:
        raise ValueError("Invalid identifier policy") from exc
    if (not kinds or len(kinds) != len(set(kinds))
            or any(kind not in IDENTIFIER_TYPES for kind in kinds)
            or not isinstance(password_min_length, int) or isinstance(password_min_length, bool)
            or password_min_length < 1):
        raise ValueError("Invalid identifier policy")
    with ext.db(banco) as c:
        _install(c)
        c.execute("UPDATE login_policy SET allowed_identifier_types=?, password_min_length=?, require_letter_number=?, updated_at=? WHERE id=1",
                  (json.dumps(kinds), password_min_length, int(bool(require_letter_number)), _now()))
    return LoginPolicy(kinds, password_min_length, bool(require_letter_number))


def _table(c, name):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _rows(c, name):
    if not _table(c, name):
        return []
    return c.execute(f"SELECT * FROM {name} ORDER BY id").fetchall()


def _col(row, name, default=None):
    return row[name] if name in row.keys() else default


def _legacy(c):
    providers = _rows(c, "prestadores")
    clients = _rows(c, "v9_usuarios")
    admins = set()
    if _table(c, "v9_admin_prestadores"):
        admins = {int(r[0]) for r in c.execute("SELECT prestador_id FROM v9_admin_prestadores")}
    return providers, clients, admins


def _migrate(c, dry_run):
    providers, clients, admins = _legacy(c)
    created = updated = identifier_created = skipped = 0
    conflicts = []
    # Primary identifiers take precedence regardless of the order of legacy rows.
    tasks = []
    for row in providers:
        tasks.append(("provider", row, "admin" if int(row["id"]) in admins else "employee"))
    for row in clients:
        tasks.append(("client", row, "customer"))
    current = {}
    for kind, row, role in tasks:
        column = "legacy_provider_id" if kind == "provider" else "legacy_client_user_id"
        existing = c.execute(f"SELECT account_id FROM account_links WHERE {column}=?", (row["id"],)).fetchone()
        current[(kind, int(row["id"]))] = existing[0] if existing else None
    for kind, row, role in tasks:
        legacy_id = int(row["id"])
        account_id = current[(kind, legacy_id)]
        active = bool(_col(row, "ativo", 1)) and not bool(_col(row, "excluido", 0))
        if account_id is None:
            cursor = c.execute("INSERT INTO accounts(display_name,password_hash,active,created_at,updated_at) VALUES(?,?,?,?,?)",
                               (row["nome"], row["senha_hash"], int(active), _now(), _now()))
            account_id = cursor.lastrowid
            created += 1
            current[(kind, legacy_id)] = account_id
            if kind == "provider":
                c.execute("INSERT INTO account_links(account_id,provider_org_id,link_type,role,provider_id,legacy_provider_id,active,created_at) VALUES(?,'autoseg','provider',?,?,?,?,?)",
                          (account_id, role, legacy_id, legacy_id, int(active), _now()))
            else:
                c.execute("INSERT INTO account_links(account_id,provider_org_id,link_type,role,client_user_id,client_id,legacy_client_user_id,active,created_at) VALUES(?,'autoseg','client','customer',?,?,?, ?,?)",
                          (account_id, legacy_id, _col(row, "cliente_pf_id"), legacy_id, int(active), _now()))
        else:
            previous = c.execute("SELECT password_hash FROM accounts WHERE id=?", (account_id,)).fetchone()
            if previous is None:
                raise ValueError("Orphaned legacy account link")
            c.execute("UPDATE accounts SET display_name=?,password_hash=?,active=?,updated_at=?, password_changed_at=CASE WHEN password_hash<>? THEN ? ELSE password_changed_at END WHERE id=?",
                      (row["nome"], row["senha_hash"], int(active), _now(), row["senha_hash"], _now(), account_id))
            c.execute("UPDATE account_links SET role=?,active=?,client_id=? WHERE account_id=?",
                      (role, int(active), _col(row, "cliente_pf_id") if kind == "client" else None, account_id))
            updated += 1
        # Primary identifiers first across all identities, then secondary identifiers.
    planned = []
    for kind, row, role in tasks:
        primary_kind = "email" if kind == "provider" else "cpf"
        primary_val = _col(row, "email", "") if kind == "provider" else _col(row, "cpf", "")
        planned.append((0, kind, row, primary_kind, primary_val))
        for typ, col in (("cpf", "documento"), ("phone", "telefone")) if kind == "provider" else (("email", "email"), ("phone", "telefone")):
            if _col(row, col):
                planned.append((1, kind, row, typ, _col(row, col)))
    for _, kind, row, typ, val in sorted(planned, key=lambda t: (t[0], 0 if t[1] == "provider" else 1, int(t[2]["id"]))):
        legacy_id = int(row["id"])
        account_id = current[(kind, legacy_id)]
        try:
            norm = normalize_identifier(typ, str(val or ""))
        except ValueError:
            skipped += 1
            conflicts.append({"reason": "invalid", "type": typ, "legacy_kind": kind, "legacy_id": legacy_id})
            continue
        existing = c.execute("SELECT id,account_id FROM account_identifiers WHERE type=? AND normalized=?", (typ, norm)).fetchone()
        if existing and existing["account_id"] != account_id:
            skipped += 1
            conflicts.append({"reason": "duplicate", "type": typ, "legacy_kind": kind, "legacy_id": legacy_id})
            continue
        is_primary = int((kind == "provider" and typ == "email") or (kind == "client" and typ == "cpf"))
        if existing:
            continue
        # Preserve the declared single-primary invariant on re-runs and changed identifiers.
        if is_primary:
            prior = c.execute("SELECT id FROM account_identifiers WHERE account_id=? AND is_primary=1", (account_id,)).fetchone()
            if prior:
                c.execute("UPDATE account_identifiers SET is_primary=0 WHERE id=?", (prior["id"],))
        c.execute("INSERT INTO account_identifiers(account_id,type,value,normalized,verified,is_primary,created_at) VALUES(?,?,?,?,0,?,?)",
                  (account_id, typ, str(val), norm, is_primary, _now()))
        identifier_created += 1
    return MigrationReport(dry_run, len(providers), len(clients), created, updated,
                           identifier_created, skipped, tuple(conflicts))


def migrate_legacy(banco, dry_run: bool = True) -> MigrationReport:
    # Dry-run works against a memory copy so not even CREATE TABLE touches the source.
    if dry_run:
        source = sqlite3.connect(str(banco))
        source.row_factory = sqlite3.Row
        target = sqlite3.connect(":memory:")
        target.row_factory = sqlite3.Row
        try:
            source.backup(target)
            _install(target)
            report = _migrate(target, True)
            target.rollback()
            return report
        finally:
            source.close()
            target.close()
    with ext.db(banco) as c:
        _install(c)
        return _migrate(c, False)


def _account(row):
    return Account(int(row["id"]), str(row["display_name"]), str(row["password_hash"]),
                   bool(row["active"]), str(row["created_at"]), str(row["updated_at"]),
                   row["password_changed_at"])


def load_account(banco, account_id: int) -> Account | None:
    with ext.db(banco) as c:
        if not _table(c, "accounts"):
            return None
        row = c.execute("SELECT * FROM accounts WHERE id=?", (int(account_id),)).fetchone()
        return _account(row) if row else None


def find_account_by_identifier(banco, kind: str, value: str) -> Account | None:
    norm = normalize_identifier(kind, value)
    with ext.db(banco) as c:
        if not _table(c, "accounts") or not _table(c, "account_identifiers"):
            return None
        row = c.execute("SELECT a.* FROM accounts a JOIN account_identifiers i ON i.account_id=a.id WHERE i.type=? AND i.normalized=?", (kind, norm)).fetchone()
        return _account(row) if row else None


def identifiers(banco, account_id: int) -> tuple[AccountIdentifier, ...]:
    with ext.db(banco) as c:
        if not _table(c, "account_identifiers"):
            return ()
        rows = c.execute("SELECT * FROM account_identifiers WHERE account_id=? ORDER BY id", (int(account_id),))
        return tuple(AccountIdentifier(int(r["id"]), int(r["account_id"]), r["type"], r["value"], r["normalized"], bool(r["verified"]), bool(r["is_primary"])) for r in rows)


def account_link(banco, account_id: int) -> AccountLink | None:
    with ext.db(banco) as c:
        if not _table(c, "account_links"):
            return None
        r = c.execute("SELECT * FROM account_links WHERE account_id=?", (int(account_id),)).fetchone()
        return (AccountLink(int(r["id"]), int(r["account_id"]), r["provider_org_id"], r["link_type"], r["role"],
                            r["provider_id"], r["client_user_id"], r["client_id"], r["legacy_provider_id"],
                            r["legacy_client_user_id"], bool(r["active"]))) if r else None


def identity_for_account(banco, account_id: int) -> identity.Identity | None:
    link = account_link(banco, account_id)
    if not link:
        return None
    return identity.load_identity(banco, link.link_type,
                                  link.provider_id if link.link_type == "provider" else link.client_user_id)


def membership_for_account(banco, account_id: int) -> identity.Membership | None:
    link = account_link(banco, account_id)
    ident = identity_for_account(banco, account_id)
    if not link or not ident:
        return None
    # Keep the linked role and activation distinct from the identity record.
    return identity.Membership(identity_kind=ident.kind, identity_id=ident.id,
                               role=link.role, provider_org_id=link.provider_org_id,
                               provider_id=link.provider_id, client_id=link.client_id,
                               active=link.active)
