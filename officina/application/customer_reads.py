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


def obter_cliente_scoped(banco, principal, cliente_id):
    """Read one customer with the exact API object and field restrictions.

    The selected columns are an explicit SQL allowlist; restricted customer
    attributes are never loaded into the returned model for employees.
    """
    from officina.application.contracts import Cliente
    from officina.core import prestadores_ext as ext

    _require_principal(principal)
    cliente_id = int(cliente_id)
    # Preserve the service contract: a missing id is ``None``, while an
    # existing but unauthorized customer is a permission error.
    with ext.db(banco) as connection:
        if connection.execute('SELECT 1 FROM clientes WHERE id=?',
                              (cliente_id,)).fetchone() is None:
            return None
    access.require_customer_read(banco, principal, cliente_id)
    if access.can_read_all(principal, 'customer'):
        from officina.application.local_service import LocalService
        record = clientes_core.obter(cliente_id, banco=banco)
        return LocalService._cliente(record) if record is not None else None

    allowed = access.involved_customer_field_scopes(principal)
    columns = ['id', 'nome', 'status', 'versao', 'dados_incompletos'] + [
        field for field in ('documento', 'telefone', 'email', 'cidade', 'endereco')
        if (field if field != 'cidade' else 'endereco') in allowed]
    with ext.db(banco) as connection:
        row = connection.execute(
            'SELECT ' + ','.join(columns) + ''' FROM clientes WHERE id=? AND EXISTS (
                SELECT 1 FROM ordens_servico os WHERE os.cliente_id=clientes.id
                AND (EXISTS (SELECT 1 FROM os_responsaveis r
                            WHERE r.os_id=os.id AND r.prestador_id=?)
                  OR EXISTS (SELECT 1 FROM os_prestadores p
                            WHERE p.os_id=os.id AND p.prestador_id=? AND p.ativo=1)))''',
            (cliente_id, principal.provider_id, principal.provider_id)).fetchone()
    if row is None:
        raise PermissionError('Recurso indisponível.')
    return Cliente(id=int(row['id']), versao=int(row['versao'] or 1),
                   campos={name: row[name] for name in row.keys()
                           if name not in ('id', 'versao', 'dados_incompletos')},
                   incompleto=bool(row['dados_incompletos']))
