"""Object-level permission resolution skeleton.

The declarative role/field policy lives in ``officina.application.policy``.
This module adds the missing object relationship layer: who owns the resource,
who participates, which organization it belongs to, and which explicit
grants/denies the account has.

It is deliberately not wired into the web server or desktop app yet. The
migration will call ``can``/``require`` from the service boundary and remove
``if admin`` checks from business code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from officina.application.policy import Policy, load_policy

ACTIONS = frozenset({
    "view", "read", "create", "edit", "delete", "assign", "conclude",
    "cancel", "approve", "export", "manage", "publish", "respond",
})
SCOPES = ("own", "involved", "all")


class PermissionDenied(PermissionError):
    """Raised when an object policy decision is negative."""

    def __init__(self, decision: "Decision"):
        super().__init__(decision.reason)
        self.decision = decision


@dataclass(frozen=True)
class Principal:
    account_id: int
    role: str
    organization_id: str | None = None
    provider_id: int | None = None
    client_id: int | None = None
    grants: frozenset[str] = frozenset()
    denies: frozenset[str] = frozenset()
    active: bool = True


@dataclass(frozen=True)
class Resource:
    kind: str
    id: int | str | None = None
    organization_id: str | None = None
    owner_id: int | None = None
    client_id: int | None = None
    participant_ids: frozenset[int] = frozenset()
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    permission: str | None = None
    relationship: str = "other"


def _matches(patterns: Iterable[str], candidates: Iterable[str]) -> str | None:
    for candidate in candidates:
        for pattern in patterns:
            if pattern == "*" or pattern == candidate:
                return candidate
            if pattern.endswith(".*") and candidate.startswith(pattern[:-1]):
                return candidate
    return None


class ObjectPolicy:
    """Resolve effective permissions for one account and one resource."""

    def __init__(self, policy: Policy | None = None):
        self.policy = policy or load_policy()

    @staticmethod
    def relationship(principal: Principal, resource: Resource) -> str:
        if not principal.active:
            return "inactive"
        if (principal.organization_id and resource.organization_id
                and principal.organization_id != resource.organization_id):
            return "other"
        if principal.role == "admin":
            return "all"
        if resource.owner_id is not None and resource.owner_id == principal.account_id:
            return "own"
        if resource.owner_id is not None and resource.owner_id == principal.provider_id:
            return "own"
        if resource.client_id is not None and resource.client_id == principal.client_id:
            return "own"
        if principal.provider_id is not None and principal.provider_id in resource.participant_ids:
            return "involved"
        if principal.account_id in resource.participant_ids:
            return "involved"
        return "other"

    def can(self, principal: Principal, action: str, resource: Resource) -> Decision:
        action = str(action or "").strip()
        if action not in ACTIONS:
            raise ValueError(f"Ação inválida: {action}")
        if not principal.active:
            return Decision(False, "Conta inativa.", relationship="inactive")
        if (principal.organization_id and resource.organization_id
                and principal.organization_id != resource.organization_id):
            return Decision(False, "Recurso de outra organização.", relationship="other")
        relationship = self.relationship(principal, resource)
        base = f"{resource.kind}.{action}"
        candidates = [base, f"{base}.all"]
        if relationship in SCOPES:
            candidates.append(f"{base}.{relationship}")
        if action == "create":
            candidates.append(f"{base}.request")
            if relationship in SCOPES:
                candidates.append(f"{base}.{relationship}.request")
        if principal.role == "admin":
            return Decision(True, "Administrador da organização.", base, relationship)
        denied = _matches(principal.denies, candidates)
        if denied:
            return Decision(False, "Permissão negada explicitamente.", denied, relationship)
        granted = _matches(principal.grants, candidates)
        if granted:
            return Decision(True, "Permissão concedida ao usuário.", granted, relationship)
        if relationship == "other":
            return Decision(False, "Sem vínculo com o recurso.", relationship=relationship)
        for candidate in candidates:
            if self.policy.allows(principal.role, candidate):
                return Decision(True, "Permissão do papel.", candidate, relationship)
        return Decision(False, "Sem permissão para a ação.", candidates[-1], relationship)

    def require(self, principal: Principal, action: str, resource: Resource) -> Decision:
        decision = self.can(principal, action, resource)
        if not decision.allowed:
            raise PermissionDenied(decision)
        return decision

    def can_view_field(self, principal: Principal, resource: Resource,
                       field_name: str) -> Decision:
        relationship = self.relationship(principal, resource)
        if not principal.active:
            return Decision(False, "Conta inativa.", relationship="inactive")
        if (principal.organization_id and resource.organization_id
                and principal.organization_id != resource.organization_id):
            return Decision(False, "Recurso de outra organização.", relationship="other")
        if not self.policy.can_view_field(principal.role, field_name, relationship):
            return Decision(False, "Campo restrito.", field_name, relationship)
        return self.can(principal, "view", resource)
