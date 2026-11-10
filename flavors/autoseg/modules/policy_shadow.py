"""Shadow object-policy adapter for AUTOSEG work items.

This module is intentionally read-only and non-blocking. It maps the current
AUTOSEG tables to ``Principal``/``Resource`` objects, asks ``ObjectPolicy`` for
a decision, compares it with the behavior that actually happened, and appends a
privacy-safe JSONL line when ``AUTOSEG_POLICY_SHADOW`` is enabled.

Enforcement is a separate migration step. Nothing here may raise, block a
request or change a response. See
``docs/planning/PROMPT_POLICY_SHADOW.md`` and
``docs/planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md``.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from officina.application.object_policy import ObjectPolicy, Principal, Resource
from officina.core import prestadores_ext as ext
from officina.core import runtime_config
from flavors.autoseg.modules import identity

LOG_LOCK = threading.Lock()
_EXTRA_KEYS = frozenset({
    "route", "method", "status", "os_id", "finalizer_id", "legacy_participants",
})


def shadow_enabled() -> bool:
    return str(os.environ.get("AUTOSEG_POLICY_SHADOW", "")).strip().lower() in (
        "1", "true", "on", "yes",
    )


def _table_exists(conexao, nome: str) -> bool:
    try:
        return bool(conexao.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (nome,),
        ).fetchone())
    except Exception:
        return False


def principal_provider(banco, provider_id: int) -> Principal:
    """Delegate legacy provider mapping to the identity contract."""
    try:
        ident = identity.load_identity(banco, "provider", provider_id)
        if ident:
            vinculo = next((m for m in identity.memberships(banco, ident)
                            if m.provider_id == int(provider_id)
                            and m.role in ("admin", "employee")), None)
            if vinculo:
                return identity.to_principal(ident, vinculo)
    except Exception:
        pass
    return Principal(account_id=int(provider_id), role="employee",
                     provider_id=int(provider_id), active=False)


def principal_client(banco, user_id: int) -> Principal:
    """Delegate legacy client mapping to the identity contract."""
    try:
        ident = identity.load_identity(banco, "client", user_id)
        if ident:
            vinculo = next((m for m in identity.memberships(banco, ident)
                            if m.client_id == ident.client_id
                            and m.role == "customer"), None)
            if vinculo:
                return identity.to_principal(ident, vinculo)
    except Exception:
        pass
    return Principal(account_id=int(user_id), role="customer", active=False)


def resource_work_item(banco, os_id: int) -> Resource:
    """Build the work-item resource, including owner, participants and status."""
    try:
        with ext.db(banco) as c:
            row = c.execute(
                "SELECT * FROM ordens_servico WHERE id=?",
                (int(os_id),),
            ).fetchone()
            if not row:
                return Resource(kind="work_item", id=int(os_id),
                                attributes={"missing": True})
            responsavel = c.execute(
                "SELECT prestador_id FROM os_responsaveis WHERE os_id=?",
                (int(os_id),),
            ).fetchone()
            participantes = c.execute(
                "SELECT prestador_id,ativo FROM os_prestadores WHERE os_id=?",
                (int(os_id),),
            ).fetchall()
            ativos = frozenset(
                int(x["prestador_id"]) for x in participantes
                if int(x["ativo"] or 0) == 1
            )
            legado = tuple(int(x["prestador_id"]) for x in participantes)
            finalizer = None
            if _table_exists(c, "os_encerramentos"):
                enc = c.execute(
                    "SELECT prestador_id FROM os_encerramentos WHERE os_id=?",
                    (int(os_id),),
                ).fetchone()
                if enc and enc["prestador_id"] is not None:
                    finalizer = int(enc["prestador_id"])
            return Resource(
                kind="work_item",
                id=int(row["id"]),
                organization_id=None,
                owner_id=(int(responsavel["prestador_id"])
                          if responsavel and responsavel["prestador_id"] is not None
                          else None),
                client_id=(int(row["cliente_id"])
                           if row["cliente_id"] is not None else None),
                participant_ids=ativos,
                attributes={
                    "status": row["status"],
                    "arquivada": (bool(row["arquivada"] or 0)
                                  if "arquivada" in row.keys() else False),
                    "finalizer_id": finalizer,
                    "legacy_participant_ids": legado,
                },
            )
    except Exception:
        return Resource(kind="work_item", id=int(os_id),
                        attributes={"missing": True})


def _safe_extra(extra: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(extra, dict):
        return {}
    saida: dict[str, Any] = {}
    for chave in _EXTRA_KEYS:
        if chave not in extra:
            continue
        valor = extra[chave]
        if isinstance(valor, (str, int, float, bool)) or valor is None:
            saida[chave] = valor if not isinstance(valor, str) else valor[:200]
    return saida


def _principal_label(principal: Principal) -> str:
    if principal.provider_id is not None:
        return f"provider:{principal.provider_id}"
    if principal.client_id is not None:
        return f"client:{principal.client_id}"
    return f"account:{principal.account_id}"


def _write_record(record: dict[str, Any]) -> None:
    pasta = runtime_config.base_dir() / "logs"
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        os.chmod(pasta, 0o700)
        arquivo = pasta / "policy_shadow.jsonl"
        with LOG_LOCK:
            with arquivo.open("a", encoding="utf-8") as saida:
                saida.write(json.dumps(record, ensure_ascii=False) + "\n")
        try:
            os.chmod(arquivo, 0o600)
        except OSError:
            pass
    except OSError:
        # Shadow measurement must never break a request.
        return


def evaluate(principal: Principal, action: str, resource: Resource,
             actual_allowed: bool, source: str,
             extra: dict[str, Any] | None = None):
    """Compare the policy decision with the actual behavior and log it."""
    if not shadow_enabled():
        return None
    motivo = "política indisponível"
    try:
        decision = ObjectPolicy().can(principal, action, resource)
    except Exception as exc:
        decision = None
        motivo = f"erro na política: {type(exc).__name__}"
    if decision is None:
        policy_allowed = False
        reason = motivo
        permission = None
        relationship = "unknown"
        tenant_unknown = True
    else:
        policy_allowed = bool(decision.allowed)
        reason = decision.reason
        permission = decision.permission
        relationship = decision.relationship
        tenant_unknown = bool(decision.tenant_unknown)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": str(source or "")[:80],
        "action": str(action or "")[:40],
        "resource": f"{resource.kind}:{resource.id}",
        "principal": _principal_label(principal),
        "role": principal.role,
        "relationship": relationship,
        "policy": policy_allowed,
        "actual": bool(actual_allowed),
        "divergence": policy_allowed != bool(actual_allowed),
        "permission": permission,
        "reason": str(reason or "")[:240],
        "tenant_unknown": tenant_unknown,
    }
    record.update(_safe_extra(extra))
    _write_record(record)
    return decision


def evaluate_os(banco, provider_id: int, os_id: int, action: str,
                actual_allowed: bool, source: str,
                extra: dict[str, Any] | None = None):
    """Convenience helper for provider-facing work-item routes."""
    if not shadow_enabled():
        return None
    return evaluate(
        principal_provider(banco, provider_id),
        action,
        resource_work_item(banco, os_id),
        actual_allowed,
        source,
        extra,
    )


def evaluate_os_client(banco, user_id: int, os_id: int, action: str,
                       actual_allowed: bool, source: str,
                       extra: dict[str, Any] | None = None):
    """Convenience helper for client-facing work-item routes."""
    if not shadow_enabled():
        return None
    return evaluate(
        principal_client(banco, user_id),
        action,
        resource_work_item(banco, os_id),
        actual_allowed,
        source,
        extra,
    )
