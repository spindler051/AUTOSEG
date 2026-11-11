"""Authenticated customer features migrated from the retired HTTP server.

Only domain services and scoped reads live here. Never render HTML or use
cookies. Each call requires the converted client session used by Officina Web.
"""
from __future__ import annotations

from flavors.autoseg.modules import cliente_fluxo_v94 as pf, client_service
from officina.core import cadastros_v9 as cad, catalogo_servicos as catalogo
from officina.core import prestadores_ext as ext, fluxo_os as fluxo
from officina.application import work_item_access as access
from pathlib import Path


def uid(session):
    return client_service._client_id(session)


def profile(banco, session):
    return pf.obter_perfil(banco, uid(session))


def update_profile(banco, session, data):
    return pf.atualizar_perfil(banco, uid(session), data)


def change_password(banco, session, data):
    """Change both credential records for the one converted account atomically."""
    from flavors.autoseg.modules import accounts, web_session
    user_id = uid(session)
    if session.account_id is None or session.source != 'account':
        raise PermissionError('Conta indisponível.')
    current = str(data.get('senha_atual') or '')
    new_password = pf.validar_senha_forte(data.get('nova_senha'))
    if new_password != str(data.get('confirmar_senha') or ''):
        raise ValueError('A confirmação da nova senha não corresponde.')
    if not current:
        raise ValueError('Informe a senha atual.')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        account = c.execute(
            'SELECT password_hash FROM accounts WHERE id=? AND active=1',
            (session.account_id,)).fetchone()
        person = c.execute(
            'SELECT senha_hash FROM v9_usuarios WHERE id=? AND ativo=1',
            (user_id,)).fetchone()
        link = c.execute(
            "SELECT 1 FROM account_links WHERE account_id=? AND client_user_id=? "
            "AND link_type='client' AND active=1",
            (session.account_id, user_id)).fetchone()
        if not account or not person or not link:
            raise PermissionError('Conta indisponível.')
        if not ext.verificar_senha(current, account['password_hash']):
            raise ValueError('Senha atual incorreta.')
        if ext.verificar_senha(new_password, account['password_hash']):
            raise ValueError('A nova senha deve ser diferente da senha atual.')
        hashed = ext.senha_hash(new_password)
        c.execute('UPDATE v9_usuarios SET senha_hash=? WHERE id=?',
                  (hashed, user_id))
        c.execute('UPDATE accounts SET password_hash=?,updated_at=?,password_changed_at=? '
                  'WHERE id=?', (hashed, accounts._now(), accounts._now(), session.account_id))
        c.execute('DELETE FROM web_sessions WHERE account_id=?',
                  (session.account_id,)) if _has_table(c, 'web_sessions') else None
    web_session.revoke_account(banco, session.account_id)
    return hashed


def _has_table(connection, table):
    return connection.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?',
                              ('table', table)).fetchone() is not None


def search_organizations(banco, session, query='', page=1):
    uid(session)
    query = str(query or '').strip()[:120]
    page = min(max(int(page), 1), 100000)
    offset = (page - 1) * 20
    digits = cad.digitos(query)
    by_cnpj = bool(query and len(digits) == 14 and all(
        x.isdigit() or x in './- ' for x in query))
    with ext.db(banco) as c:
        if by_cnpj:
            condition, args = 'cnpj=?', (digits,)
        elif query:
            escaped = query.replace('!', '!!').replace('%', '!%').replace('_', '!_')
            condition, args = "nome LIKE ? ESCAPE '!'", ('%' + escaped + '%',)
        else:
            condition, args = '1=1', ()
        where = f'{condition} AND mesclado_em IS NULL'
        rows = c.execute('SELECT id,nome,tipo,cidade,bairro FROM v9_organizacoes '
                         f'WHERE {where} ORDER BY nome LIMIT 20 OFFSET ?',
                         (*args, offset)).fetchall()
        total = c.execute(f'SELECT COUNT(*) FROM v9_organizacoes WHERE {where}', args).fetchone()[0]
    return tuple(dict(r) for r in rows), int(total)


def organization(banco, session, org_id):
    uid(session)
    with ext.db(banco) as c:
        row = c.execute('SELECT id,nome,tipo,cnpj,cidade,bairro FROM v9_organizacoes '
                        'WHERE id=? AND mesclado_em IS NULL', (int(org_id),)).fetchone()
    if not row:
        raise PermissionError('Organização indisponível.')
    return dict(row)


def request_link(banco, session, data):
    return pf.solicitar_administracao(banco, uid(session), int(data.get('org_id', 0)),
                                     str(data.get('cnpj', '')), str(data.get('funcao', '')))


def create_organization_request(banco, session, data):
    # Existing cadastros_v9 service validates and commits organization + OS.
    return cad.criar_organizacao_e_os(banco, uid(session), data)


def create_call(banco, session, data):
    return pf.registrar_chamado_org(banco, uid(session), data)


def organization_history(banco, session, org_id):
    user_id = uid(session)
    # This service validates the explicit responsible appointment, not a
    # free-text role supplied through the UI.
    return cad.listar_os_organizacao(banco, int(org_id), user_id)


def linked_organizations(banco, session):
    user_id = uid(session)
    with ext.db(banco) as c:
        rows = c.execute('''SELECT o.id,o.nome,o.tipo,v.papel,v.situacao
            FROM v9_vinculos v JOIN v9_organizacoes o ON o.id=v.organizacao_id
            WHERE v.usuario_id=? AND o.mesclado_em IS NULL ORDER BY o.nome''',
            (user_id,)).fetchall()
    return tuple(dict(r) for r in rows)


def approved_organizations(banco, session):
    user_id = uid(session)
    with ext.db(banco) as c:
        rows = c.execute('''SELECT o.id,o.nome,o.tipo,r.papel FROM v9_responsaveis r
            JOIN v9_organizacoes o ON o.id=r.organizacao_id
            WHERE r.usuario_id=? AND o.mesclado_em IS NULL ORDER BY o.nome''',
            (user_id,)).fetchall()
    return tuple(dict(r) for r in rows)


def quote_services(banco, session):
    uid(session)
    return tuple((item, catalogo.reais(catalogo.valores_orcamento(banco, item['id'])['total']))
                 for item in catalogo.listar(banco, ativos=True))


def quote_pdf(banco, session, data):
    person = profile(banco, session)
    pdf = catalogo.pdf_orcamento(banco, int(data.get('servico_id', '0')),
                                data.get('quantidade', '1'),
                                person.get('nome') or 'Cliente', person.get('cpf') or '')
    return pdf, 'application/pdf', 'AUTOSEG_orcamento_estimativo.pdf'


def report_for_work(banco, session, work_id):
    # Server finds the immutable published document ID, never accepts a path
    # or a file name from a request.
    access.require_work_item(banco, session.principal, int(work_id), 'view')
    record = fluxo.ultimo_documento(banco, int(work_id))
    if not record:
        raise PermissionError('Documento indisponível.')
    return client_service.open_document(banco, session, int(work_id), -int(record['id']))


def invoice_by_id(banco, session, invoice_id):
    uid(session)
    with ext.db(banco) as c:
        row = c.execute('SELECT os_id FROM os_notas_fiscais WHERE id=?',
                        (int(invoice_id),)).fetchone()
    if not row:
        raise PermissionError('Documento indisponível.')
    return client_service.open_document(banco, session, int(row['os_id']), int(invoice_id))


def report_for_call(banco, session, call_id):
    call = client_service.get_call(banco, session, int(call_id))
    if call is None or call.work_id is None:
        raise PermissionError('Documento indisponível.')
    record = fluxo.ultimo_documento(banco, int(call.work_id))
    if not record:
        raise PermissionError('Documento indisponível.')
    return client_service.open_call_document(banco, session, int(call_id), -int(record['id']))


def report_for_organization(banco, session, org_id, work_id):
    # Verify actual role/tenant against the current policy before metadata.
    uid(session)
    org_id, work_id = int(org_id), int(work_id)
    if org_id not in session.principal.client_org_ids:
        raise PermissionError('Documento indisponível.')
    resource = access.resource_for_work_item(banco, work_id)
    if resource.client_org_id != org_id:
        raise PermissionError('Documento indisponível.')
    return report_for_work(banco, session, work_id)
