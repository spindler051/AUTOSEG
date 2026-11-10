"""Unified authentication service with optional account storage and legacy fallback.

This module does not create sessions, cookies, routes or authorization grants.
"""
from __future__ import annotations

import re
import importlib
from dataclasses import dataclass

from flavors.autoseg.modules import identity
from officina.application.object_policy import Principal
from officina.core import cadastros_v9 as cad9
from officina.core import prestadores_ext as ext

try:
    accounts = importlib.import_module("flavors.autoseg.modules.accounts")
except ModuleNotFoundError as exc:
    # Only the optional module itself may be missing. Internal import failures
    # must not silently switch a potentially broken account store to legacy.
    if exc.name not in ("flavors.autoseg.modules.accounts", "accounts"):
        raise
    accounts = None


@dataclass(frozen=True)
class LoginResult:
    account_id: int | None
    identity: identity.Identity
    membership: identity.Membership
    principal: Principal
    source: str


class LoginError(Exception):
    """Public, non-enumerating authentication error."""

    _MESSAGES = {
        "invalid": "Credenciais inválidas.",
        "ambiguous": "Não foi possível autenticar com este identificador.",
        "inactive": "Acesso indisponível.",
        "unsupported": "Tipo de identificador não permitido.",
    }

    def __init__(self, code: str):
        if code not in self._MESSAGES:
            raise ValueError("Invalid login error code.")
        self.code = code
        super().__init__(self._MESSAGES[code])


def normalize_identifier(kind: str, value: str) -> str:
    """Normalize an identifier, preserving the account-store contract."""
    if accounts is not None:
        return accounts.normalize_identifier(kind, value)
    if not isinstance(value, str):
        raise ValueError("Invalid identifier.")
    value = value.strip()
    if kind == "email":
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Invalid identifier.")
        return value.casefold()
    if kind in ("cpf", "phone"):
        if not re.fullmatch(r"[\d.\-/\s()+]+", value):
            raise ValueError("Invalid identifier.")
        digits = re.sub(r"\D", "", value)
        if kind == "cpf" and len(digits) != 11:
            raise ValueError("Invalid identifier.")
        if kind == "phone" and not 10 <= len(digits) <= 13:
            raise ValueError("Invalid identifier.")
        return digits
    if kind == "nametag":
        normalized = value.casefold()
        if not re.fullmatch(r"[a-z0-9._-]{3,30}", normalized):
            raise ValueError("Invalid identifier.")
        return normalized
    raise ValueError("Invalid identifier kind.")


def _policy(banco):
    if accounts is None:
        return None
    try:
        return accounts.login_policy(banco)
    except (ValueError, TypeError, KeyError):
        return None


def allowed_identifier_types(banco) -> tuple[str, ...]:
    policy = _policy(banco)
    types = getattr(policy, "allowed_identifier_types", ("email", "cpf"))
    valid = ("email", "cpf", "phone", "nametag")
    if (not isinstance(types, (tuple, list)) or not types
            or any(t not in valid for t in types)
            or len(set(types)) != len(types)):
        return ("email", "cpf")
    return tuple(types)


def validate_password_strength(password: str, policy=None) -> tuple[bool, str]:
    """Validate proposed passwords; existing hashes are not revalidated."""
    if policy is None:
        min_length, letter_number = 12, True
    else:
        min_length = getattr(policy, "password_min_length", 12)
        letter_number = getattr(policy, "require_letter_number", True)
    if not isinstance(min_length, int) or not 1 <= min_length <= 1024:
        min_length = 12
    if not isinstance(password, str) or len(password) < min_length:
        return False, "A senha não atende ao tamanho mínimo."
    if letter_number and not (any(c.isalpha() for c in password)
                              and any(c.isdigit() for c in password)):
        return False, "A senha deve conter letras e números."
    return True, ""


def _candidate_types(value: str) -> tuple[str, ...]:
    if "@" in value:
        return ("email",) if _valid("email", value) else ()
    # A punctuated CPF is not a nametag, but may be a valid document.
    if re.fullmatch(r"[\d.\-/\s()+]+", value):
        digits = re.sub(r"\D", "", value)
        choices = []
        if len(digits) == 11 and _valid("cpf", value):
            choices.append("cpf")
        if 10 <= len(digits) <= 13 and _valid("phone", value):
            choices.append("phone")
        # A nametag may legitimately contain only digits; the account lookup
        # will reject it if no account uses that handle.
        if _valid("nametag", value):
            choices.append("nametag")
        return tuple(choices)
    return ("nametag",) if _valid("nametag", value) else ()


def _valid(kind, value):
    try:
        normalize_identifier(kind, value)
        return True
    except (ValueError, TypeError):
        return False


def _account_login(banco, candidates, identifier, password):
    if accounts is None:
        return None
    found = {}
    for kind in candidates:
        account = accounts.find_account_by_identifier(banco, kind, identifier)
        if account is not None:
            found[account.id] = account
    if len(found) > 1:
        raise LoginError("ambiguous")
    if not found:
        return None
    account = next(iter(found.values()))
    if not ext.verificar_senha(password, account.password_hash):
        raise LoginError("invalid")
    if not account.active:
        raise LoginError("inactive")
    ident = accounts.identity_for_account(banco, account.id)
    membership = accounts.membership_for_account(banco, account.id)
    if ident is None or membership is None or not membership.active:
        raise LoginError("inactive")
    try:
        principal = identity.to_principal(ident, membership)
    except ValueError:
        raise LoginError("invalid") from None
    if not principal.active:
        raise LoginError("inactive")
    return LoginResult(account.id, ident, membership, principal, "account")


def _legacy_login(banco, candidates, identifier, password):
    legacy_types = tuple(kind for kind in candidates if kind in ("email", "cpf"))
    if not legacy_types:
        raise LoginError("unsupported")
    matched = {}
    for kind in legacy_types:
        normalized = normalize_identifier(kind, identifier)
        for ident in identity.resolve_identifier(banco, normalized):
            if (kind == "email" or ident.kind == "client"):
                matched[(ident.kind, ident.id)] = ident
    if not matched:
        raise LoginError("invalid")
    active = {key: value for key, value in matched.items() if value.active}
    if len(active) > 1:
        raise LoginError("ambiguous")
    if active:
        ident = next(iter(active.values()))
    elif len(matched) == 1:
        ident = next(iter(matched.values()))
    else:
        # Multiple inactive identities are rejected without revealing which
        # one matched or whose password was checked.
        raise LoginError("inactive")
    # The legacy login helpers apply active filters. Read the stored hash only
    # for a matching inactive identity so it can be rejected without a bypass.
    if ident.active:
        if ident.kind == "provider":
            authenticated = ext.autenticar(banco, ident.email, password)
        else:
            authenticated = cad9.autenticar(banco, ident.cpf, password)
        if authenticated is None or int(authenticated["id"]) != ident.id:
            raise LoginError("invalid")
    else:
        table = "prestadores" if ident.kind == "provider" else "v9_usuarios"
        with ext.db(banco) as connection:
            row = connection.execute(
                f"SELECT senha_hash FROM {table} WHERE id=?", (ident.id,)
            ).fetchone()
        if row is None or not ext.verificar_senha(password, row["senha_hash"]):
            raise LoginError("invalid")
        raise LoginError("inactive")
    memberships = identity.memberships(banco, ident)
    if len(memberships) != 1:
        raise LoginError("invalid")
    membership = memberships[0]
    try:
        principal = identity.to_principal(ident, membership)
    except ValueError:
        raise LoginError("invalid") from None
    if not principal.active:
        raise LoginError("inactive")
    return LoginResult(None, ident, membership, principal, "legacy")


def authenticate(banco, identifier: str, password: str) -> LoginResult:
    """Authenticate without creating sessions or modifying persisted records."""
    if not isinstance(identifier, str) or not identifier.strip():
        raise LoginError("invalid")
    if not isinstance(password, str) or not password:
        raise LoginError("invalid")
    identifier = identifier.strip()
    candidates = _candidate_types(identifier)
    if not candidates:
        raise LoginError("invalid")
    allowed = allowed_identifier_types(banco)
    permitted = tuple(kind for kind in candidates if kind in allowed)
    if not permitted:
        raise LoginError("unsupported")
    result = _account_login(banco, permitted, identifier, password)
    if result is not None:
        return result
    return _legacy_login(banco, permitted, identifier, password)
