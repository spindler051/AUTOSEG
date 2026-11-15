"""Authenticated, surface-neutral customer read projections.

GTK-local and Desktop API invoke the same SQL and ObjectPolicy checks. The
caller supplies a principal derived from the authenticated session; this module
never trusts a GTK/Web discriminator or a caller-controlled admin boolean.
"""
from __future__ import annotations

from officina.application import work_item_access as access
from officina.application.contracts import ClienteResumo
from officina.integration import clientes as clientes_core


def _require_principal(principal):
    if (principal is None or not principal.active
            or principal.organization_id != 'autoseg'
            or type(principal.provider_id) is not int
            or principal.provider_id <= 0):
        raise PermissionError('Recurso indisponível.')


def listar_clientes_scoped(banco, principal, termo='') -> list[ClienteResumo]:
    """List only customer rows and columns visible to the given actor.

    The admin branch matches the historical full projection; the employee
    branch uses the *same* SQL-side relationship and field projection that the
    Desktop API used before this module was extracted.
    """
    _require_principal(principal)
    if access.can_read_all(principal, 'customer'):
        from officina.application.local_service import LocalService
        return [LocalService._resumo(record)
                for record in clientes_core.listar(termo, banco=banco)]
    allowed = access.involved_customer_field_scopes(principal)
    _, rows = clientes_core.listar_paginado(
        termo, limite=1000, banco=banco,
        provider_id=principal.provider_id, allowed_fields=allowed)
    return [ClienteResumo(id=int(row['id']), nome=str(row['nome'] or ''),
              documento=str(row['documento'] or ''), cidade=str(row['cidade'] or ''),
              telefone=str(row['telefone'] or ''), status=str(row['status'] or ''),
              incompleto=bool(row['dados_incompletos'])) for row in rows]
