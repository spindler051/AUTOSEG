"""Read-only readiness checks for the opt-in unified login rollout."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

COOKIE_NAME = "autosseg_unified"
_TRUE_VALUES = frozenset(("1", "true", "on", "yes"))
_DEFAULT_TYPES = ("email", "cpf")
_SUPPORTED_TYPES = frozenset(("email", "cpf", "phone", "nametag"))
_REQUIRED_TABLES = frozenset((
    "accounts", "account_identifiers", "account_links", "login_policy",
))


def unified_login_enabled(banco=None) -> bool:
    """Return whether unified login was explicitly enabled in the environment."""
    return str(os.environ.get("AUTOSEG_UNIFIED_LOGIN", "")).strip().lower() in _TRUE_VALUES


def _read_only_connection(banco):
    # URI read-only mode avoids creating a missing database and writing journals.
    if banco is None:
        raise ValueError("database path required")
    db_path = Path(os.fspath(banco)).expanduser().resolve(strict=True)
    return sqlite3.connect(f"file:{quote(str(db_path), safe='/')}?mode=ro", uri=True)


def activation_report(banco) -> dict:
    """Inspect the installed account schema without migrating or writing data."""
    blockers: list[str] = []
    report = {
        "flag": unified_login_enabled(banco),
        "cookie_name": COOKIE_NAME,
        "accounts_installed": False,
        "accounts": 0,
        "active_accounts": 0,
        "providers": 0,
        "clients": 0,
        "active_providers": 0,
        "active_clients": 0,
        "policy_types": (),
        "conflicts": None,
        "ready": False,
        "blockers": (),
    }
    try:
        with _read_only_connection(banco) as connection:
            connection.row_factory = sqlite3.Row
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "accounts" not in tables:
                blockers.append("accounts_not_installed")
            elif not _REQUIRED_TABLES.issubset(tables):
                blockers.append("accounts_schema_incomplete")
            else:
                # Require the exact fields needed by this report rather than
                # silently treating a partially upgraded schema as ready.
                required_columns = {
                    "accounts": {
                        "id", "display_name", "password_hash", "active",
                        "created_at", "updated_at", "password_changed_at",
                    },
                    "account_identifiers": {
                        "id", "account_id", "type", "value", "normalized",
                        "verified", "is_primary", "created_at",
                    },
                    "account_links": {
                        "id", "account_id", "provider_org_id", "link_type",
                        "role", "provider_id", "client_user_id", "client_id",
                        "legacy_provider_id", "legacy_client_user_id", "active",
                        "created_at",
                    },
                    "login_policy": {
                        "id", "allowed_identifier_types",
                        "password_min_length", "require_letter_number",
                        "updated_at",
                    },
                }
                if any(not columns.issubset({
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                }) for table, columns in required_columns.items()):
                    blockers.append("accounts_schema_incomplete")
                else:
                    report["accounts_installed"] = True
                    report["accounts"] = connection.execute(
                        "SELECT count(*) FROM accounts"
                    ).fetchone()[0]
                    report["active_accounts"] = connection.execute(
                        "SELECT count(*) FROM accounts WHERE active=1"
                    ).fetchone()[0]
                    counts = dict(connection.execute(
                        "SELECT link_type, count(*) FROM account_links "
                        "WHERE provider_org_id='autoseg' GROUP BY link_type"
                    ).fetchall())
                    active_counts = dict(connection.execute(
                        "SELECT link_type, count(*) FROM account_links "
                        "WHERE provider_org_id='autoseg' AND active=1 "
                        "GROUP BY link_type"
                    ).fetchall())
                    report["providers"] = counts.get("provider", 0)
                    report["clients"] = counts.get("client", 0)
                    report["active_providers"] = active_counts.get("provider", 0)
                    report["active_clients"] = active_counts.get("client", 0)
                    if report["accounts"] == 0:
                        blockers.append("accounts_empty")
                    elif report["active_accounts"] == 0:
                        blockers.append("accounts_inactive")
                    if report["providers"] == 0:
                        blockers.append("providers_not_migrated")
                    elif report["active_providers"] == 0:
                        blockers.append("active_providers_not_migrated")
                    if report["clients"] == 0:
                        blockers.append("clients_not_migrated")
                    elif report["active_clients"] == 0:
                        blockers.append("active_clients_not_migrated")
                    # Detect dangling links even when SQLite foreign-key
                    # enforcement may have been disabled by older callers.
                    broken = connection.execute(
                        "SELECT 1 FROM account_links AS l LEFT JOIN accounts AS a "
                        "ON a.id=l.account_id WHERE a.id IS NULL LIMIT 1"
                    ).fetchone()
                    if broken:
                        blockers.append("orphan_account_links")
                    policy = connection.execute(
                        "SELECT allowed_identifier_types FROM login_policy WHERE id=1"
                    ).fetchone()
                    if policy is None:
                        blockers.append("login_policy_missing")
                    else:
                        try:
                            types = json.loads(policy[0])
                            if (not isinstance(types, list) or not types
                                    or any(not isinstance(t, str) for t in types)
                                    or len(types) != len(set(types))
                                    or not set(types).issubset(_SUPPORTED_TYPES)):
                                raise ValueError("invalid identifier policy")
                            report["policy_types"] = tuple(types)
                        except (ValueError, TypeError):
                            blockers.append("login_policy_invalid")
    except (OSError, ValueError, sqlite3.Error):
        if not blockers:
            blockers.append("database_unavailable")
    report["blockers"] = tuple(blockers)
    report["ready"] = not blockers and report["accounts_installed"]
    return report
