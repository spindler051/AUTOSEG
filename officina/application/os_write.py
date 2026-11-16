"""Legacy desktop OSInput compatibility adapter; no service-order SQL.

The canonical data writer is ``portal_negocios.os_salvar``, reached only via
``os_write_service``. This module preserves the public OSInput/OSResultado
boundary while the Web and native desktop share business rules.
"""
from __future__ import annotations

from dataclasses import replace

from officina.application.contracts import OSInput, OSResultado
from officina.application.object_policy import ObjectPolicy, Resource
from officina.application.work_item_access import require_work_item_locked
from officina.application.os_write_service import OSCommand, write_data
from officina.core import prestadores_ext as ext, fluxo_os as fluxo


def _authorize_locked(connection, principal, os_id, action, extra_authorize):
    """Repeat identity and object authorization under BEGIN IMMEDIATE."""
    if not connection.in_transaction:
        raise RuntimeError('OS authorization requires a locked transaction.')
    if (principal is None or not principal.active or
            principal.organization_id != 'autoseg' or
            type(principal.provider_id) is not int):
        raise PermissionError('Identidade obrigatória para alterar OS.')
    pid = principal.provider_id
    row = connection.execute('''SELECT ativo,excluido FROM prestadores
                                  WHERE id=?''', (pid,)).fetchone()
    if not row or not row['ativo'] or row['excluido']:
        raise PermissionError('Prestador inativo ou vínculo revogado.')
    actual = 'admin' if ext.administrador(connection, pid) else 'employee'
    if principal.role != actual:
        raise PermissionError('O papel do prestador foi alterado.')
    if extra_authorize is not None:
        extra_authorize(connection)
    if os_id is None:
        ObjectPolicy().require(principal, 'create',
                               Resource('work_item', organization_id='autoseg'))
    else:
        order = connection.execute('''SELECT status,arquivada FROM ordens_servico
                                      WHERE id=?''', (int(os_id),)).fetchone()
        if not order or order['arquivada'] or order['status'] not in ext.ATIVAS:
            raise PermissionError('OS indisponível para alteração.')
        require_work_item_locked(connection, principal, int(os_id), action)


def salvar_os(banco, dados: OSInput, *, authorize=None, principal=None) -> OSResultado:
    """Translate desktop inputs and delegate every SQL write to the Web core."""
    if principal is None or type(principal.provider_id) is not int:
        raise PermissionError('Identidade obrigatória para alterar OS.')
    action = ('conclude' if dados.acao == 'Concluída'
              else 'cancel' if dados.acao == 'Cancelada' else 'edit')
    command = OSCommand.from_desktop(dados, principal.provider_id)
    with ext.db(banco) as connection:
        connection.execute('BEGIN IMMEDIATE')
        _authorize_locked(connection, principal, dados.os_id, action, authorize)
        old = connection.execute('SELECT status FROM ordens_servico WHERE id=?',
                                 (dados.os_id,)).fetchone() if dados.os_id else None
        oid = write_data(banco, command, connection=connection)
        if dados.os_id is None:
            ext.assumir(banco, oid, principal.provider_id, connection=connection)
    return OSResultado(oid, dados.os_id is None, dados.acao in fluxo.FIM,
                       str(old['status'] or '') if old else '',
                       dados.dados_incompletos)
