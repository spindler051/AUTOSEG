"""C2: one authorized rateio boundary shared by Web and GTK.

Persistence remains exclusively in produtividade_os.definir_rateio_manual.
This service neither edits OS headers nor introduces a second SQL writer.
"""
from __future__ import annotations

from officina.application.work_item_access import (require_work_item_locked,
                                                   require_read_work_item)
from officina.core import prestadores_ext as ext
from officina.core import produtividade_os as prod


def contexto(banco, os_id, principal):
    """Read current contacts and rateio data for an already authorized OS."""
    from officina.application.live_provider import resolve as live_provider
    principal = live_provider(banco, principal)
    require_read_work_item(banco, principal, int(os_id))
    with ext.db(banco) as connection:
        work = connection.execute(
            'SELECT status,valor_total,arquivada FROM ordens_servico WHERE id=?',
            (int(os_id),)).fetchone()
        if not work:
            raise PermissionError('Recurso indisponível.')
        final = connection.execute(
            'SELECT prestador_id FROM os_encerramentos WHERE os_id=?',
            (int(os_id),)).fetchone()
        closer = (int(final['prestador_id']) if final and final['prestador_id'] is not None
                  else ext.responsavel_atual(connection, int(os_id)))
        is_admin = bool(ext.administrador(connection, principal.provider_id))
        can_edit = (not work['arquivada'] and
                    work['status'] not in ('Cancelada', 'Não realizada') and
                    (is_admin or (closer is not None and
                     int(closer) == int(principal.provider_id))))
        rows = [dict(item) for item in connection.execute('''
            SELECT r.tecnico_id,p.nome,r.valor_centavos
            FROM produtividade_rateios r JOIN prestadores p ON p.id=r.tecnico_id
            WHERE r.os_id=? ORDER BY p.nome''', (int(os_id),))]
        nota = connection.execute('''SELECT nome_original FROM os_notas_fiscais
            WHERE os_id=? ORDER BY id DESC LIMIT 1''', (int(os_id),)).fetchone()
        workers = [dict(item) for item in connection.execute('''
            SELECT id,nome FROM prestadores
            WHERE ativo=1 AND excluido=0 ORDER BY nome''')]
    return {
        'contatos': prod.contatos_email_os(banco, int(os_id)),
        'nota_fiscal': dict(nota) if nota else None,
        'rateios': rows,
        'prestadores_rateio': workers,
        'rateio_editavel': bool(can_edit),
        'rateio_responsavel_id': closer,
    }


def require_work_item_locked_view(connection, principal, os_id):
    """Read policy is checked even if the rateio belongs to a closed OS."""
    return require_work_item_locked(connection, principal, int(os_id), 'view')


def definir(banco, principal, os_id, tecnico_id, valor, *, authorize=None):
    """Use the existing domain transaction and authorizations for one rateio row."""
    if principal is None or principal.provider_id is None:
        raise PermissionError('Identidade obrigatória.')
    from officina.application.live_provider import resolve as live_provider
    principal = live_provider(banco, principal)
    with ext.db(banco) as connection:
        connection.execute('BEGIN IMMEDIATE')
        if authorize is not None:
            authorize(connection)
        else:
            require_work_item_locked_view(connection, principal, os_id)
        # Domain validates administrator/finalizer, active workers, existing
        # payments and the OS total before writing. A failed call rolls back.
        return prod.definir_rateio_manual(
            banco, int(os_id), int(principal.provider_id), int(tecnico_id),
            str(valor), connection=connection)
