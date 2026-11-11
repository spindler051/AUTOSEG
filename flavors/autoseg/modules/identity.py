"""Read-only identity adapters for the legacy AUTOSEG user tables.

Identity identifies a legacy record; memberships supply context and roles.
This module does not authenticate users or grant access to any resources.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from officina.application.object_policy import Principal
from officina.core import prestadores_ext as ext


@dataclass(frozen=True)
class Identity:
    kind: str
    id: int
    display_name: str
    email: str = ""
    cpf: str = ""
    active: bool = True
    provider_id: int | None = None
    client_id: int | None = None


@dataclass(frozen=True)
class Membership:
    identity_kind: str
    identity_id: int
    role: str
    provider_org_id: str | None = None
    provider_id: int | None = None
    client_id: int | None = None
    active: bool = True
    client_org_ids: frozenset[int] = frozenset()


def _exists(connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(connection, table: str) -> set[str]:
    if not _exists(connection, table):
        return set()
    # The table name is an internal constant; PRAGMA cannot bind identifiers.
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}


def _identity_from_row(kind: str, row) -> Identity:
    keys = row.keys()
    active = bool(row["ativo"]) if "ativo" in keys else True
    if "excluido" in keys:
        active = active and not bool(row["excluido"])
    legacy_id = int(row["id"])
    if kind == "provider":
        return Identity(
            kind="provider", id=legacy_id,
            display_name=str(row["nome"] or ""),
            email=str(row["email"] or ""),
            active=active, provider_id=legacy_id,
        )
    return Identity(
        kind="client", id=legacy_id,
        display_name=str(row["nome"] or ""),
        email=str(row["email"] or ""),
        cpf=re.sub(r"\D", "", str(row["cpf"] or "")),
        active=active,
        client_id=(int(row["cliente_pf_id"])
                   if "cliente_pf_id" in keys and row["cliente_pf_id"] is not None
                   else None),
    )


def _search_rows(connection, table: str, condition: str, param: str):
    if not _exists(connection, table):
        return ()
    # Table/condition are internal constants; the identifier is bound.
    return connection.execute(
        f"SELECT * FROM {table} WHERE {condition} ORDER BY id", (param,)
    ).fetchall()


def resolve_identifier(banco, identifier: str) -> tuple[Identity, ...]:
    """Find every provider/client matching an email or normalized document."""
    if not isinstance(identifier, str):
        return ()
    identifier = identifier.strip()
    if not identifier:
        return ()
    is_email = "@" in identifier
    if is_email:
        if not re.fullmatch(r"[^\s@]+@[^\s@]+", identifier):
            return ()
        value = identifier.casefold()
    else:
        # Accept CPF/CNPJ punctuation only; never accept arbitrary text.
        if not re.fullmatch(r"[\d.\-/\s]+", identifier):
            return ()
        value = re.sub(r"\D", "", identifier)
        if len(value) not in (11, 14):
            return ()

    matches: list[Identity] = []
    try:
        with ext.db(banco) as connection:
            for kind, table in (("provider", "prestadores"),
                                ("client", "v9_usuarios")):
                columns = _columns(connection, table)
                if not columns:
                    continue
                if is_email:
                    if "email" not in columns:
                        continue
                    rows = _search_rows(
                        connection, table,
                        "lower(trim(COALESCE(email, ''))) = ?", value,
                    )
                else:
                    document = "documento" if kind == "provider" else "cpf"
                    if document not in columns:
                        continue
                    normalized = (
                        f"replace(replace(replace(replace("
                        f"COALESCE({document}, ''), '.', ''), '-', ''), '/', ''), ' ', '')"
                    )
                    rows = _search_rows(connection, table, f"{normalized} = ?", value)
                matches.extend(_identity_from_row(kind, row) for row in rows)
    except Exception:
        # Identifier resolution is observational and must never break a caller.
        return ()
    return tuple(matches)


def load_identity(banco, kind: str, identity_id: int) -> Identity | None:
    """Read one legacy identity without reading or returning password hashes."""
    if kind not in ("provider", "client"):
        return None
    try:
        identity_id = int(identity_id)
        table = "prestadores" if kind == "provider" else "v9_usuarios"
        with ext.db(banco) as connection:
            if not _exists(connection, table):
                return None
            row = connection.execute(
                f"SELECT * FROM {table} WHERE id=?", (identity_id,)
            ).fetchone()
            return _identity_from_row(kind, row) if row is not None else None
    except (ValueError, TypeError, OverflowError):
        return None
    except Exception:
        return None


def memberships(banco, identity: Identity) -> tuple[Membership, ...]:
    """Read the legacy role for an identity without writing any data."""
    if not isinstance(identity, Identity):
        return ()
    if identity.kind == "client":
        # Client roles require an explicitly converted account_links row.
        # The legacy user record cannot grant an implicit customer role.
        return ()
    if identity.kind != "provider":
        return ()
    try:
        with ext.db(banco) as connection:
            is_admin = False
            if _exists(connection, "v9_admin_prestadores"):
                is_admin = connection.execute(
                    "SELECT 1 FROM v9_admin_prestadores WHERE prestador_id=?",
                    (identity.id,),
                ).fetchone() is not None
    except Exception:
        # A failed role lookup must not silently grant an administrative role.
        return ()
    return (Membership(
        identity_kind="provider", identity_id=identity.id,
        role="admin" if is_admin else "employee",
        provider_id=identity.provider_id,
        active=identity.active,
    ),)


def to_principal(identity: Identity, membership: Membership) -> Principal:
    """Map one matching identity/membership pair to the policy Principal."""
    if (not isinstance(identity, Identity)
            or not isinstance(membership, Membership)
            or identity.kind != membership.identity_kind
            or identity.id != membership.identity_id):
        raise ValueError("Identity and membership do not match.")
    expected = {"provider": ("admin", "employee"), "client": ("customer", "porteiro", "zelador", "sindico")}
    if membership.role not in expected.get(identity.kind, ()):
        raise ValueError("Membership role is invalid for this identity kind.")
    if identity.kind == "provider":
        if (membership.provider_id != identity.id or membership.client_id is not None
                or membership.client_org_ids):
            raise ValueError("Provider membership does not match the identity.")
    elif membership.provider_id is not None or membership.client_id != identity.client_id:
        raise ValueError("Client membership does not match the identity.")
    return Principal(
        account_id=identity.id,
        role=membership.role,
        organization_id=membership.provider_org_id,
        provider_id=membership.provider_id,
        client_id=membership.client_id,
        active=identity.active and membership.active,
        client_org_ids=membership.client_org_ids,
    )
