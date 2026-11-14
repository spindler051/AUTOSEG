"""Authorized provider OS commands.

Each command runs authorization before business operations. Writers were extracted
from the provider portal, retaining their responses through an explicit UI port.
A writer cannot be invoked by the HTTP router without the command registry.
"""
from __future__ import annotations
import re
from pathlib import Path
from officina.application.work_item_access import (require_work_item, require_create,
    require_work_item_locked)
from officina.application.object_policy import ObjectPolicy, Resource
import json
import mimetypes
import os
import secrets
import time
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode as urllib_parse_urlencode
import logging
from officina.core import (prestadores_ext as ext, portal_negocios as neg,
    fluxo_os as fluxo, atendimento_os as aten, cadastros_v9 as cad9,
    produtividade_os as prod, catalogo_servicos as catalogo,
    os_effect_outbox as outbox)
from flavors.autoseg.modules import object_policy_flags
from flavors.autoseg.modules import (importacao_yaml as yaml_import,
    solicitacoes_pj as pj_publico, policy_shadow)
from officina.integration import clientes as clientes_core
from officina.repositories import ordens as ordens_repo
LOG=logging.getLogger('autosseg.portal')
from threading import RLock
from contextlib import contextmanager, nullcontext

_LOCK_POOL: dict[int, RLock] = {}
_POOL_GUARD = RLock()

@contextmanager
def _serialized(os_id):
    key = int(os_id or 0)
    with _POOL_GUARD:
        lock = _LOCK_POOL.setdefault(key,RLock())
    with lock:
        yield


def _provider_context(banco, session):
    from flavors.autoseg.modules import identity, accounts, web_session
    from officina.core import prestadores_ext as ext
    pid = session.get('pid')
    if not isinstance(pid,int):
        raise PermissionError('Operação indisponível.')
    user = identity.load_identity(banco,'provider',pid)
    if not user or not user.active:
        raise PermissionError('Operação indisponível.')
    memberships = identity.memberships(banco,user)
    if len(memberships)!=1:
        raise PermissionError('Operação indisponível.')
    from dataclasses import replace
    principal = identity.to_principal(user,memberships[0])
    # The current deployment has one provider tenant; legacy memberships lack
    # provider_org_id. Bind to this deployment's concrete tenant explicitly.
    return replace(principal,organization_id="autoseg")


def _transaction_guard(banco, principal, os_id, action):
    """Validate current OS/account state inside the caller's BEGIN IMMEDIATE.

    Existing legacy permission scope remains opt-in; current account activity,
    cached role and archived/state constraints are never trusted from preflight.
    """
    enforce = object_policy_flags.enforcement_enabled(banco)

    def verify(connection):
        if not connection.in_transaction:
            raise RuntimeError('Writer authorization requires a transaction.')
        row = connection.execute('SELECT status,arquivada FROM ordens_servico WHERE id=?',
                                 (os_id,)).fetchone()
        if not row or row['arquivada']:
            raise PermissionError('OS indisponível para alteração.')
        if action in ('start', 'assign', 'assume', 'edit', 'cancel') and row['status'] not in ext.ATIVAS:
            raise PermissionError('OS não está ativa.')
        if principal is not None and principal.provider_id is not None:
            active = connection.execute('SELECT 1 FROM prestadores WHERE id=? AND ativo=1',
                                        (principal.provider_id,)).fetchone()
            if not active:
                raise PermissionError('Prestador inativo ou vínculo revogado.')
            current_role = 'admin' if ext.administrador(connection,principal.provider_id) else 'employee'
            if principal.role != current_role:
                raise PermissionError('Papel alterado desde a autenticação.')
        if enforce:
            return require_work_item_locked(connection, principal, os_id, action)
        return None

    return verify


def _work_revision(c, os_id):
    """A committed OS event uniquely identifies the current domain revision."""
    event = c.execute('SELECT COALESCE(MAX(id),0) FROM os_eventos WHERE os_id=?',
                      (os_id,)).fetchone()[0]
    row = c.execute('SELECT status,atualizado_em FROM ordens_servico WHERE id=?',
                    (os_id,)).fetchone()
    if not row:
        raise ValueError('OS não encontrada.')
    return f'{int(event)}:{row["status"]}:{row["atualizado_em"]}'


def _publish_postcommit(banco, key):
    if key:
        return outbox.publish_pdf(banco, key)
    return None


def _enqueue_pdf_if_installed(c, os_id, action):
    if not outbox.installed(c):
        return None
    return outbox.enqueue_pdf(c, os_id, _work_revision(c, os_id), action)['operation_key']


def _flush_staged_files(banco, os_id):
    # Publication is deliberately after the OS transaction commits.
    with ext.db(banco) as c:
        if not outbox.installed(c):
            return
        rows=c.execute('''SELECT operation_key FROM os_effect_outbox
            WHERE os_id=? AND effect_type='file' AND state IN ('pending','failed')
            ORDER BY id''',(os_id,)).fetchall()
    for row in rows:
        outbox.publish_file(banco,row['operation_key'])


def _authorize(banco, principal, os_id, permission):
    if not object_policy_flags.enforcement_enabled(banco):
        return None
    if permission == 'create':
        return require_create(banco, principal)
    return require_work_item(banco, principal, os_id, permission)


from officina.core import prestadores_ext as ext, cadastros_v9 as cad9, portal_negocios as neg
from officina.integration import clientes as clientes_core
class OsBusinessSupport:
    """Business-side compatibility helpers moved out of HTTP Handler."""
    def __init__(self,banco):
        self.banco=banco
    def _cliente_por_nome(self, nome, *, connection=None):
        banco = self.banco
        return clientes_core.criar_provisorio(nome, banco=banco, connection=connection)


    def _resolver_cliente_os(self, d, oid=None, *, connection=None):
        banco = self.banco
        """Existing selected id, new client typed by name, or current OS client."""
        bruto = str(d.get('cliente_id', '')).strip()
        if bruto:
            try:
                cliente_id = int(bruto)
            except (TypeError, ValueError):
                raise ValueError('Cliente selecionado inválido.') from None
            with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
                ativo = c.execute("SELECT 1 FROM clientes WHERE id=? AND status NOT IN ('Inativo','A definir')", (cliente_id,)).fetchone()
            if ativo:
                return cliente_id
            # "Cliente a definir" is intentionally allowed on an OS.
            with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
                linha = c.execute('SELECT status FROM clientes WHERE id=?',
                                  (cliente_id,)).fetchone()
            if linha and linha['status'] == 'A definir':
                return cliente_id
            raise ValueError('Cliente selecionado não encontrado ou inativo.')
        nome = str(d.get('cliente_busca', '')).strip()
        if len(nome) >= 2:
            return self._cliente_por_nome(nome,connection=connection)
        if oid is not None:
            with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
                atual = c.execute('SELECT cliente_id FROM ordens_servico WHERE id=?',
                                  (oid,)).fetchone()
            if atual and atual['cliente_id']:
                return int(atual['cliente_id'])
        raise ValueError('Selecione um cliente existente ou digite o nome de um novo cliente.')


    def _cliente_a_definir(self, *, connection=None):
        banco = self.banco
        """Cadastro provisório para OS aberta antes de escolher o cliente."""
        with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
            linha=c.execute("SELECT id FROM clientes WHERE status='A definir' "
                            "ORDER BY id LIMIT 1").fetchone()
            if linha:
                return int(linha['id'])
            cur=c.execute("""INSERT INTO clientes
                (tipo_pessoa,documento,nome,bairro,cidade,observacoes,status,criado_em)
                VALUES('Física','','Cliente a definir','','',
                'Criado automaticamente para uma OS aberta sem cliente. Associe o cliente depois.',
                'A definir',?)""",(ext.agora(),))
            return int(cur.lastrowid)


    def _exigir_cliente_os(self, oid, acao, cliente_id=None, *, connection=None):
        banco = self.banco
        with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
            if cliente_id:
                linha=c.execute("SELECT nome,status FROM clientes WHERE id=?",
                                (int(cliente_id),)).fetchone()
            else:
                linha=c.execute("""SELECT c.nome,c.status FROM ordens_servico o
                    JOIN clientes c ON c.id=o.cliente_id WHERE o.id=?""",(oid,)).fetchone()
        if not linha or linha['status'] in ('A definir','Inativo'):
            raise ValueError(f'Escolha o cliente da OS antes de {acao}.')


    def _persist_form_client(self, d, oid, pid, actor, rule, *, connection=None):
        banco = self.banco
        """Persist the client chosen in a workflow form before its action.

        Workflow buttons submit the whole OS form, but only the regular
        save route used to persist the client. Without this, selecting
        a client and clicking "Iniciar OS" still validated the previous
        client stored on the OS. ``rule`` mirrors the authorization of
        each action so a denied action never changes the client.
        """
        if 'cliente_id' not in d and 'cliente_busca' not in d:
            return None
        with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
            linha=c.execute('SELECT status FROM ordens_servico WHERE id=?',(oid,)).fetchone()
            if not linha:
                raise ValueError('OS não encontrada.')
            if linha['status'] not in ext.ATIVAS:
                raise ValueError('Esta OS não está ativa.')
            responsavel=ext.responsavel_atual(c,oid)
        if rule=='route' and responsavel is None:
            raise ValueError('Atribua um técnico antes de marcar Em rota.')
        # ObjectPolicy already checked the exact command before this helper.
        cliente_id=int(self._resolver_cliente_os(d,oid,connection=connection))
        with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
            if connection is None:
                c.execute('BEGIN IMMEDIATE')
            atual=c.execute('SELECT cliente_id FROM ordens_servico WHERE id=?',(oid,)).fetchone()
            anterior=int(atual['cliente_id'] or 0) if atual else 0
            if anterior!=cliente_id:
                c.execute('UPDATE ordens_servico SET cliente_id=?,atualizado_em=? WHERE id=?',
                          (cliente_id,ext.agora(),oid))
                nome=c.execute('SELECT nome FROM clientes WHERE id=?',(cliente_id,)).fetchone()
                rotulo=nome['nome'] if nome else str(cliente_id)
                ext.evento(c,oid,'Cliente definido',
                           f'{anterior} -> {cliente_id} ({rotulo})',pid,actor)
                neg.audit(c,pid,'Cliente da OS alterado',oid,
                          f'{anterior} -> {cliente_id} ({rotulo})')
            if connection is None:
                c.commit()
        return cliente_id


def _write_import_yaml_existing(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid=int(partes[1]);arq=d.get('yaml')
    if not isinstance(arq,tuple):raise ValueError('Selecione um arquivo YAML.')
    with ext.db(banco) as c:
        os_atual=c.execute('SELECT numero_os,status FROM ordens_servico WHERE id=?',(oid,)).fetchone()
    if not os_atual or os_atual['status'] not in ext.ATIVAS:
        raise ValueError('Somente OS ativas podem importar relatório.')
    try:pre=yaml_import.relatorio(arq[0],arq[1])
    except ValueError as erro:return ui.os_form(s,oid,erro=str(erro))
    if not pre:
        return ui.os_form(s,oid,erro='O YAML está em branco. Preencha a seção "os" antes de importar.')
    pre['_substituir']=str(d.get('substituir',''))=='1'
    return ui.os_form(s,oid,preenchimento=pre)


def _write_create_quick(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    card = portal.card
    botao = portal.botao
    esc = portal.esc
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    cliente_texto=str(d.get('cliente_id','')).strip()
    cliente_nome=str(d.get('cliente_nome','')).strip()[:250]
    descricao=str(d.get('descricao','')).strip()
    if len(descricao)<5:
        return ui.os_rapida_form(s,erro='Descreva a solicitação com pelo menos 5 caracteres.',
                                dados_form=d)
    urgencia=str(d.get('urgencia','Normal')).strip() or 'Normal'
    if urgencia not in ('Baixa','Normal','Alta'):
        return ui.os_rapida_form(s,erro='Escolha a urgência.',dados_form=d)
    if cliente_texto:
        try:
            cliente_id=int(cliente_texto)
        except (ValueError,TypeError):
            return ui.os_rapida_form(s,erro='Cliente inválido. Digite o nome novamente.',
                                    dados_form=d)
        if not clientes_core.obter_resumo_ativo(cliente_id,banco=banco):
            return ui.os_rapida_form(s,erro='Cliente não encontrado ou inativo.',
                                    dados_form=d)
    else:
        cliente_id=None

    class DuplicateNotice(Exception):
        def __init__(self, selected_id, existing):
            self.selected_id=selected_id
            self.existing=existing

    try:
        with ext.db(banco) as c:
            c.execute('BEGIN IMMEDIATE')
            if cliente_id:
                cliente_id=business._resolver_cliente_os({'cliente_id':str(cliente_id)},
                                                         connection=c)
            elif cliente_nome:
                cliente_id=business._cliente_por_nome(cliente_nome,connection=c)
            else:
                cliente_id=business._cliente_a_definir(connection=c)
            duplicada=ui._os_duplicada_recente(cliente_id)
            if duplicada and str(d.get('confirmar_duplicidade',''))!='1':
                raise DuplicateNotice(cliente_id,duplicada)
            dados={'cliente_id':str(cliente_id),'descricao':descricao,'tecnico':'',
                   'forma_pagamento':'','forma_pagamento_opcional':'1',
                   'urgencia':urgencia,'valor_mao_obra':'0',
                   'valor_materiais_manual':'0','materiais_presentes':'1',
                   'acao_status':'salvar'}
            oid=neg.os_salvar(banco,dados,pid,connection=c)
            ext.assumir(banco,oid,pid,connection=c)
            if duplicada and str(d.get('confirmar_duplicidade',''))=='1':
                ext.evento(c,oid,'Criação confirmada após aviso de duplicidade',
                           f'OS recente do mesmo cliente: {duplicada["numero_os"]} '
                           f'({duplicada["criado_em"]}).',pid,f'Prestador {s["nome"]}')
            numero=(c.execute('SELECT numero_os FROM ordens_servico WHERE id=?',
                              (oid,)).fetchone() or {'numero_os': oid})['numero_os']
            cliente=(c.execute('SELECT status,dados_incompletos FROM clientes WHERE id=?',
                               (cliente_id,)).fetchone() or
                     {'status':'','dados_incompletos':0})
    except DuplicateNotice as warning:
        return ui.os_rapida_form(s,dados_form=d,cliente_id=warning.selected_id,
                                duplicada=warning.existing)
    aviso_cliente=''
    if cliente['status']=='A definir':
        aviso_cliente=('<p class="notice">A OS está com <b>Cliente a definir</b>. '
                       'Abra a OS e escolha o cliente quando souber.</p>')
    elif cliente['dados_incompletos']:
        aviso_cliente=('<p class="notice">O cliente foi criado com <b>dados incompletos</b>. '
                       'Complete CPF/CNPJ, e-mail e endereço quando puder.</p>')
    extra_cliente=(''
        if not cliente['dados_incompletos'] else
        botao('Completar cadastro do cliente',f'/clientes/{cliente_id}','secondary'))
    return ui.pagina('OS aberta com sucesso',
        card('OS aberta com sucesso',
            f'<p class="good">A OS <b>{esc(numero)}</b> foi criada como <b>Aberta</b>.</p>'
            +aviso_cliente+
            '<p class="muted">Você não precisa preencher o atendimento agora. '
            'Abra a OS quando for executar o serviço ou anexar fotos.</p>'
            +botao('Abrir OS',f'{url_os(banco, oid)}')
            +extra_cliente
            +botao('Abrir outra OS','/os/rapida','secondary')
            +botao('Voltar às OS','/os','secondary')),s)


def _write_import_yaml_new(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    arquivo=d.get('yaml')
    if not isinstance(arquivo,tuple) or not arquivo[0]:
        raise ValueError('Selecione um arquivo YAML.')
    try:
        preenchimento=yaml_import.relatorio(arquivo[0],arquivo[1])
    except ValueError as erro:
        return ui.os_form(s,None,erro=str(erro))
    if not preenchimento:
        return ui.os_form(s,None,erro='O YAML está em branco. Preencha a seção "os" antes de importar.')
    cliente_id=str(d.get('cliente_id','')).strip()
    if cliente_id:
        try:
            preenchimento['cliente_id']=int(cliente_id)
        except ValueError:
            pass
    return ui.os_form(s,None,preenchimento=preenchimento)


def _write_create_full(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    d = dict(d)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        d['cliente_id'] = business._resolver_cliente_os(d,connection=c)
        oid=neg.os_salvar(banco,d,pid,connection=c)
        ext.assumir(banco,oid,pid,connection=c)
    return ui.redir(f'{url_os(banco, oid)}')


def _write_move_attachment(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules.portal_prestador import url_os
    aid=int(path.strip('/').split('/')[3])
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        _transaction_guard(banco,principal,os_id,'attach')(c)
        movido=ext.mover_anexo(banco,os_id,aid,str(data.get('direcao','')),
                               session['pid'],ator=session['nome'],connection=c)
    if quer_json:
        return ui.send_bytes(json.dumps({'ok':True,'movido':bool(movido)}).encode(),
                             'application/json; charset=utf-8')
    return ui.redir(url_os(banco,os_id))


def _write_remove_attachment(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules.portal_prestador import url_os
    aid=int(path.strip('/').split('/')[3])
    key=None
    removed_path=None
    committed=False
    try:
        with ext.db(banco) as c:
            c.execute('BEGIN IMMEDIATE')
            _transaction_guard(banco,principal,os_id,'attach')(c)
            foto=c.execute('SELECT caminho,sha256 FROM os_anexos WHERE id=? AND os_id=?',
                           (aid,os_id)).fetchone()
            if not foto: raise ValueError('Foto não encontrada.')
            removed_path=Path(foto['caminho']).resolve()
            if outbox.installed(c):
                revision=f'{aid}:{foto["sha256"]}'
                intent=outbox.enqueue_file(c,os_id,revision,'attachment-remove',
                                           aid,foto['sha256'])
                key=intent['operation_key']
                outbox.quarantine_file(ext.ANEXOS,foto['caminho'],key,
                                        source_id=aid,source_sha256=foto['sha256'])
            ext.remover_anexo(banco,os_id,aid,session['pid'],
                              ator=f'Prestador {session["nome"]}',connection=c)
        committed=True
    finally:
        if key and not committed:
            outbox.restore_quarantine(ext.ANEXOS,key)
    if key: outbox.publish_file(banco,key)
    elif removed_path.parent==Path(ext.ANEXOS).resolve(): removed_path.unlink(missing_ok=True)
    return ui.redir(url_os(banco,os_id))


def _write_rotate_attachment(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules.portal_prestador import url_os
    aid=int(path.strip('/').split('/')[3])
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        _transaction_guard(banco,principal,os_id,'attach')(c)
        ext.girar_imagem(banco,os_id,aid,session['pid'],ator=session['nome'],connection=c)
    _flush_staged_files(banco,os_id)
    if quer_json:
        return ui.send_bytes(json.dumps({'ok':True,'anexo_id':aid}).encode(),
                             'application/json; charset=utf-8')
    return ui.redir(url_os(banco,os_id))


def _write_publish_attachment(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules.portal_prestador import url_os
    aid=int(path.strip('/').split('/')[3])
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        _transaction_guard(banco,principal,os_id,'attach')(c)
        if not c.execute('SELECT 1 FROM os_anexos WHERE id=? AND os_id=?',
                         (aid,os_id)).fetchone():
            raise ValueError('Anexo não pertence à OS.')
        cad9.aprovar_anexo(banco,aid,str(data.get('visivel','0'))=='1',
                           str(data.get('legenda','')),session['nome'],connection=c,pid=session['pid'])
    return ui.redir(url_os(banco,os_id))


def _write_photos(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid=int(partes[1])
    with ext.db(banco) as c:
        os_atual=c.execute('SELECT status,arquivada FROM ordens_servico WHERE id=?',
                           (oid,)).fetchone()
        admin=bool(c.execute('SELECT 1 FROM v9_admin_prestadores WHERE prestador_id=?',(pid,)).fetchone())
        if ext.responsavel_atual(c,oid)!=pid and not admin:
            raise PermissionError('Somente o responsável ou administrador edita fotos e legendas.')
    if not os_atual or os_atual['status'] not in ext.ATIVAS:
        raise ValueError('Somente OS ativas podem receber fotos.')
    if 'arquivada' in os_atual.keys() and os_atual['arquivada']:
        raise PermissionError('OS arquivada: edição bloqueada.')
    def _lista(valor):
        if valor is None:return []
        return valor if isinstance(valor,list) else [valor]
    imagens=_lista(d.get('imagens_encerramento[]'))
    legendas=_lista(d.get('foto_legenda[]'))
    chaves=_lista(d.get('foto_chave[]'))
    visiveis=_lista(d.get('foto_visivel[]'))
    anexo_ids=_lista(d.get('anexo_id[]'))
    anexo_legendas=_lista(d.get('anexo_legenda[]'))
    anexo_visiveis=_lista(d.get('anexo_visivel[]'))
    anexo_incluidos={str(x).strip() for x in _lista(d.get('anexo_incluir[]')) if str(x).strip()}
    modo_checkbox=str(d.get('anexo_incluir_modo',''))=='1'
    imagens=[x for x in imagens if isinstance(x,tuple) and x[1]]
    if not imagens and not anexo_ids and not d.get('comprimir_fotos_pdf_presente'):
        raise ValueError('Selecione uma foto ou altere uma legenda.')
    if len(imagens)>10:
        raise ValueError('Envie no máximo 10 fotos por vez.')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        guard = _transaction_guard(banco, principal, oid, 'attach')
        guard(c)
        current = c.execute('SELECT status,arquivada FROM ordens_servico WHERE id=?',
                            (oid,)).fetchone()
        if not current or current['status'] not in ext.ATIVAS or current['arquivada']:
            raise PermissionError('OS indisponível para anexos.')
        if str(d.get('comprimir_fotos_pdf_presente',''))=='1':
            comprimir_pdf=1 if str(d.get('comprimir_fotos_pdf','')) in ('1','on','true','sim') else 0
            c.execute('UPDATE ordens_servico SET comprimir_fotos_pdf=? WHERE id=?',
                      (comprimir_pdf,oid))
        for i,(nome,conteudo) in enumerate(imagens):
            ext.registrar_imagem_transacao(
                c,oid,pid,nome,conteudo,
                permitir_colaboracao=admin,
                chave=chaves[i] if i<len(chaves) else None,
                legenda=legendas[i] if i<len(legendas) else '',
                visivel=str(visiveis[i])!='0' if i<len(visiveis) else 1,
                staged=outbox.installed(c))
        for i,anexo_id in enumerate(anexo_ids):
            try:
                anexo_id=int(anexo_id)
            except (TypeError,ValueError):
                continue
            if modo_checkbox:
                visivel=1 if str(anexo_id) in anexo_incluidos else 0
            else:
                visivel=(str(anexo_visiveis[i])!='0'
                         if i<len(anexo_visiveis) else 1)
            ext.definir_legenda_anexo_c(
                c,oid,anexo_id,
                anexo_legendas[i] if i<len(anexo_legendas) else '',
                visivel)
    _flush_staged_files(banco,oid)
    if quer_json:
        return ui.send_bytes(json.dumps({
            'ok': True,
            'fotos': len(imagens),
            'legendas': len(anexo_ids),
        }).encode(), 'application/json; charset=utf-8')
    return ui.redir(f'{url_os(banco, oid)}')


def _write_autosave_draft(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    if 'emails_adicionais' in data:
        message='Campo de e-mail avulso não aceito. Cadastre o contato da OS.'
        return ui.send_bytes(json.dumps({'ok':False,'error':message}).encode(),
            'application/json; charset=utf-8',status=400)
    pid = session['pid']
    oid = os_id
    values = {key: value for key, value in data.items()
              if key not in ('csrf', 'modo_envio', 'nota_fiscal')}
    try:
        with ext.db(banco) as c:
            c.execute('BEGIN IMMEDIATE')
            guard=_transaction_guard(banco,principal,oid,'edit')
            if guard:
                guard(c)
            prod.salvar_rascunho(banco,oid,pid,data,connection=c)
            ext.salvar_rascunho_web(banco,oid,pid,values,connection=c)
            # A background autosave can contain only technical draft fields.
            # Do not invoke full-form validation without its required description.
            if str(data.get('descricao','')).strip():
                save=dict(data,acao_status='salvar')
                save['cliente_id']=OsBusinessSupport(banco)._resolver_cliente_os(
                    save,oid,connection=c)
                neg.os_salvar(banco,save,pid,oid,silent=True,connection=c,
                             staged_attachments=outbox.installed(c))
            cad9.salvar_detalhes(banco,oid,str(data.get('v9_diagnostico','')),
                str(data.get('v9_execucao','')),str(data.get('v9_resultado','')),
                connection=c)
            if str(data.get('relatorio_tecnico','')).strip():
                aten.salvar_rascunho(c,oid,str(data['relatorio_tecnico']),
                                     f'Prestador {session["nome"]}')
            version=c.execute('SELECT atualizado_em FROM ordens_servico WHERE id=?',
                              (oid,)).fetchone()
            versao_os=version['atualizado_em'] if version else None
        _flush_staged_files(banco,oid)
        if quer_json:
            return ui.send_bytes(json.dumps({'ok':True,'versao_os':versao_os}).encode(),
                                 'application/json; charset=utf-8')
        return ui.redir(portal.url_os(banco,oid))
    except (ValueError,PermissionError) as exc:
        if quer_json:
            return ui.send_bytes(json.dumps({'ok':False,'error':str(exc)}).encode(),
                'application/json; charset=utf-8',status=(403 if isinstance(exc,PermissionError) else 400))
        raise


def _write_save_draft(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    if 'emails_adicionais' in data:
        message='Campo de e-mail avulso não aceito. Cadastre o contato da OS.'
        return ui.send_bytes(json.dumps({'ok':False,'error':message}).encode(),
            'application/json; charset=utf-8',status=400)
    pid=session['pid']
    oid=os_id
    values={key: value for key, value in data.items()
            if key not in ('csrf','modo_envio','nota_fiscal')}
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        guard=_transaction_guard(banco,principal,oid,'edit')
        if guard:
            guard(c)
        prod.salvar_rascunho(banco,oid,pid,data,connection=c)
        ext.salvar_rascunho_web(banco,oid,pid,values,connection=c)
        save=dict(data,acao_status='salvar')
        save['cliente_id']=OsBusinessSupport(banco)._resolver_cliente_os(
            save,oid,connection=c)
        neg.os_salvar(banco,save,pid,oid,connection=c,
                         staged_attachments=outbox.installed(c))
        cad9.salvar_detalhes(banco,oid,str(data.get('v9_diagnostico','')),
            str(data.get('v9_execucao','')),str(data.get('v9_resultado','')),
            connection=c)
        if str(data.get('relatorio_tecnico','')).strip():
            aten.salvar_rascunho(c,oid,str(data['relatorio_tecnico']),
                f'Prestador {session["nome"]}')
        arquivo=data.get('nota_fiscal')
        if isinstance(arquivo,tuple) and arquivo[0]:
            ext.salvar_nota_fiscal(banco,oid,pid,arquivo[0],arquivo[1],
               connection=c,staged=outbox.installed(c))
    _flush_staged_files(banco,oid)
    return ui.pagina('Rascunho salvo',portal.card('Rascunho',
        '<p class="good">Rascunho salvo com sucesso. Ele será recuperado ao reabrir esta OS.</p>'
        +portal.botao('Voltar à OS',f'{portal.url_os(banco, oid)}')),session)


def _write_rateio(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid=int(partes[1])
    try:
        tecnico=int(str(d.get('rateio_manual_tecnico','')).strip())
    except (TypeError,ValueError):
        erro='Selecione o técnico secundário.'
        if quer_json:
            return ui.send_bytes(json.dumps(
                {'ok':False,'error':erro}).encode(),
                'application/json; charset=utf-8',status=400)
        raise ValueError(erro)
    try:
        with ext.db(banco) as c:
            c.execute('BEGIN IMMEDIATE')
            guard=_transaction_guard(banco,principal,oid,'edit')
            if guard:
                guard(c)
            prod.definir_rateio_manual(banco,oid,pid,tecnico,
                                       str(d.get('rateio_manual_valor','0')),connection=c)
    except Exception as exc:
        if quer_json:
            status=403 if isinstance(exc,PermissionError) else 400
            return ui.send_bytes(json.dumps(
                {'ok':False,'error':str(exc)}).encode(),
                'application/json; charset=utf-8',status=status)
        raise
    if quer_json:
        with ext.db(banco) as c:
            o=c.execute('SELECT valor_total FROM ordens_servico WHERE id=?',
                        (oid,)).fetchone()
            rows=c.execute('''SELECT r.tecnico_id,p.nome,r.valor_centavos,
                COALESCE(rep.pago_centavos,0) pago_centavos,
                COALESCE(rep.enviado_centavos,0) enviado_centavos
                FROM produtividade_rateios r
                JOIN prestadores p ON p.id=r.tecnico_id
                LEFT JOIN produtividade_repasses rep
                  ON rep.os_id=r.os_id AND rep.tecnico_id=r.tecnico_id
                WHERE r.os_id=? ORDER BY p.nome''',(oid,)).fetchall()
        rateios=[]
        for x in rows:
            valor_x=int(x['valor_centavos'] or 0)
            pago_x=int(x['pago_centavos'] or 0)
            enviado_x=int(x['enviado_centavos'] or 0)
            situacao=('Repasse confirmado' if pago_x>=valor_x
                      else 'Repasse enviado' if enviado_x>0
                      else 'Aguardando repasse')
            rateios.append({'tecnico_id':int(x['tecnico_id']),
                            'nome':x['nome'],
                            'valor_centavos':valor_x,
                            'situacao':situacao})
        total_centavos=int(round(float(
            (o['valor_total'] if o else 0) or 0)*100))
        rateado_centavos=sum(x['valor_centavos'] for x in rateios)
        return ui.send_bytes(json.dumps({
            'ok':True,'rateios':rateios,
            'total_centavos':total_centavos,
            'rateado_centavos':rateado_centavos,
            'restante_centavos':max(0,total_centavos-rateado_centavos)
        }).encode(),'application/json; charset=utf-8')
    return ui.redir(f'{url_os(banco, oid)}')


def _write_remove_invoice(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules.portal_prestador import url_os
    nid=int(path.strip('/').split('/')[3])
    key=None
    removed_path=None
    committed=False
    try:
        with ext.db(banco) as c:
            c.execute('BEGIN IMMEDIATE')
            _transaction_guard(banco,principal,os_id,'attach')(c)
            invoice=c.execute('SELECT caminho,sha256 FROM os_notas_fiscais WHERE id=? AND os_id=?',
                              (nid,os_id)).fetchone()
            if not invoice: raise ValueError('Nota fiscal não encontrada.')
            removed_path=Path(invoice['caminho']).resolve()
            if outbox.installed(c):
                revision=f'{nid}:{invoice["sha256"]}'
                intent=outbox.enqueue_file(c,os_id,revision,'invoice-remove',
                                           nid,invoice['sha256'])
                key=intent['operation_key']
                outbox.quarantine_file(ext.NOTAS,invoice['caminho'],key,
                                        source_id=nid,source_sha256=invoice['sha256'])
            ext.remover_nota_fiscal(banco,os_id,nid,session['pid'],
                                   ator=session['nome'],connection=c)
        committed=True
    finally:
        if key and not committed:
            outbox.restore_quarantine(ext.NOTAS,key)
    if key: outbox.publish_file(banco,key)
    elif removed_path.parent==Path(ext.NOTAS).resolve(): removed_path.unlink(missing_ok=True)
    if quer_json:
        return ui.send_bytes(json.dumps({'ok':True}).encode(),
                             'application/json; charset=utf-8')
    return ui.redir(url_os(banco,os_id))


def _write_attach_invoice(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    pid=session['pid']
    oid=os_id
    arquivo=data.get('nota_fiscal')
    if not isinstance(arquivo,tuple) or not arquivo[0]:
        raise ValueError('Selecione um arquivo PDF de nota fiscal.')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        guard=_transaction_guard(banco,principal,oid,'attach')
        if guard:
            guard(c)
        if ext.responsavel_atual(c,oid)!=pid and not ext.administrador(c,pid):
            raise PermissionError('Somente o responsável ou administrador pode anexar nota fiscal.')
        values={k: data[k] for k in data if k not in ('csrf','modo_envio','nota_fiscal')}
        if values:
            ext.salvar_rascunho_web(banco,oid,pid,values,connection=c)
            cad9.salvar_detalhes(banco,oid,str(data.get('v9_diagnostico','')),
                str(data.get('v9_execucao','')),str(data.get('v9_resultado','')),
                connection=c)
            if str(data.get('relatorio_tecnico','')).strip():
                aten.salvar_rascunho(c,oid,str(data['relatorio_tecnico']),
                    f'Prestador {session["nome"]}')
        nid=ext.salvar_nota_fiscal(banco,oid,pid,arquivo[0],arquivo[1],
                                  connection=c,staged=outbox.installed(c))
    _flush_staged_files(banco,oid)
    if quer_json:
        return ui.send_bytes(json.dumps({'ok':True,'nota_id':nid}).encode(),
                             'application/json; charset=utf-8')
    return ui.redir(portal.url_os(banco,oid))


def _write_action_abrir(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid = os_id
    acao = partes[2]
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        o=c.execute('SELECT status,arquivada,cliente_id FROM ordens_servico WHERE id=?',
                    (oid,)).fetchone()
        if not o or o['status'] not in ext.ATIVAS:
            raise ValueError('Esta OS não está ativa.')
        if 'arquivada' in o.keys() and o['arquivada']:
            raise ValueError('OS arquivada: edição bloqueada.')
        action = 'reopen' if o['status'] == 'Pendente' else 'edit'
        guard = _transaction_guard(banco, principal, oid, action)
        guard(c)
        if o['status'] == 'Pendente' and not object_policy_flags.enforcement_enabled(banco):
            require_work_item_locked(c, principal, oid, 'reopen')
        # Client selection is part of this transaction, not an earlier write.
        # A new provisional customer is a separate domain operation and is not
        # implicitly created as part of a privileged reopen.
        cliente_id = int(o['cliente_id'] or 0)
        raw_id = str(d.get('cliente_id', '')).strip()
        raw_name = str(d.get('cliente_busca', '')).strip()
        if raw_id:
            try:
                cliente_id = int(raw_id)
            except (ValueError, TypeError):
                raise ValueError('Cliente selecionado inválido.') from None
        elif raw_name and len(raw_name) >= 2:
            # The provisional client and reopen share the same transaction.
            # Authorization has already been checked before this write.
            cliente_id = business._cliente_por_nome(raw_name, connection=c)
        customer = c.execute('SELECT nome,status FROM clientes WHERE id=?',
                             (cliente_id,)).fetchone()
        if not customer or customer['status'] in ('A definir','Inativo'):
            raise ValueError('Escolha o cliente da OS antes de reabrir a OS.')
        if cliente_id != int(o['cliente_id'] or 0):
            c.execute('UPDATE ordens_servico SET cliente_id=?,atualizado_em=? WHERE id=?',
                      (cliente_id, ext.agora(), oid))
            ext.evento(c, oid, 'Cliente definido',
                       f'{o["cliente_id"]} -> {cliente_id} ({customer["nome"]})',
                       pid, f'Prestador {s["nome"]}')
            neg.audit(c, pid, 'Cliente da OS alterado', oid,
                      f'{o["cliente_id"]} -> {cliente_id} ({customer["nome"]})')
        c.execute("UPDATE ordens_servico SET status='Aberta',data_conclusao=NULL,atualizado_em=? WHERE id=?",
                  (ext.agora(),oid))
        c.execute('''UPDATE os_atendimentos SET iniciado_em=NULL,iniciado_por=NULL,
                     ator_inicio='',atualizado_em=? WHERE os_id=?''',
                  (ext.agora(),oid))
        c.execute('DELETE FROM produtividade_deslocamentos WHERE os_id=?',(oid,))
        ext.evento(c,oid,'OS reaberta','Situação alterada para Aberta.',pid,'Prestador')
    return ui.redir(f'{url_os(banco, oid)}')


def _write_action_arquivar(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid = os_id
    acao = partes[2]
    ext.arquivar_os(banco,oid,pid,ator=s['nome'],
                    motivo=str(d.get('motivo_arquivamento','')),
                    authorize=_transaction_guard(banco,principal,oid,'archive'))
    return ui.redir('/os')
    return ui.redir(f"{url_os(banco, os_id)}")


def _write_action_rota(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid = os_id
    acao = partes[2]
    prod.marcar_em_rota(banco,oid,pid,str(d.get('ativo','0'))=='1',
                        admin=bool(s.get('admin')),
                        authorize=_transaction_guard(banco,principal,oid,'start'))
    return ui.redir(f'{url_os(banco, oid)}')


def _write_action_cancelar(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    card = portal.card
    botao = portal.botao
    esc = portal.esc
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid = os_id
    acao = partes[2]
    motivo=str(d.get('motivo_encerramento','')).strip()[:2000]
    if not motivo:
        raise ValueError('Informe o motivo do cancelamento.')
    publish_key=None
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        o=c.execute('SELECT numero_os,status,arquivada FROM ordens_servico WHERE id=?',
                    (oid,)).fetchone()
        if not o or o['status'] not in ext.ATIVAS:
            raise ValueError('Esta OS não está ativa.')
        if 'arquivada' in o.keys() and o['arquivada']:
            raise ValueError('OS arquivada: edição bloqueada.')
        _transaction_guard(banco,principal,oid,'cancel')(c)
        atual=ext.responsavel_atual(c,oid)
        admin=bool(c.execute('SELECT 1 FROM v9_admin_prestadores WHERE prestador_id=?',
                             (pid,)).fetchone())
        if atual not in (None,pid) and not admin:
            raise PermissionError('Somente o responsável ou administrador pode cancelar.')
        if str(d.get('confirmar_numero_os','')).strip()!=str(o['numero_os']).strip():
            raise ValueError('O número da OS digitado não confere.')
        fluxo.aplicar_encerramento(
            c,oid,'Cancelada','',motivo,prestador_id=pid,
            ator=f'Prestador {s["nome"]}')
        neg.audit(c,pid,'OS cancelada',oid,f'Motivo: {motivo}')
        publish_key=_enqueue_pdf_if_installed(c,oid,'cancel')
    try:
        if publish_key:
            _publish_postcommit(banco,publish_key)
        else:
            fluxo.publicar_relatorio(banco,oid)
    except (ValueError,OSError) as falha:
        LOG.exception('OS %s cancelada, mas falhou a publicação do PDF',oid)
        return ui.pagina('OS cancelada — PDF pendente',card('Cancelamento salvo',
            '<p>Os dados da OS foram preservados. Falhou apenas a publicação do PDF.</p>'
            f'<p class="bad">{esc(str(falha)[:400])}</p>'
            +botao('Abrir OS e republicar PDF',f'{url_os(banco, oid)}')),s,503)
    return ui.redir(f'{url_os(banco, oid)}')


def _write_action_salvar(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    card, botao, esc, url_os = portal.card, portal.botao, portal.esc, portal.url_os
    business = OsBusinessSupport(banco)
    pid = session['pid']
    oid = os_id
    d = dict(data)
    if 'emails_adicionais' in d:
        raise ValueError('Campo de e-mail avulso não aceito. Cadastre o contato da OS.')
    draft = d.get('modo_envio') in ('rascunho', 'salvar')
    if draft:
        with ext.db(banco) as c:
            c.execute('BEGIN IMMEDIATE')
            guard = _transaction_guard(banco, principal, oid, 'edit')
            if guard:
                guard(c)
            # No partial draft is kept if the OS data is rejected.
            values = {key: value for key, value in d.items()
                      if key not in ('csrf', 'modo_envio', 'nota_fiscal')}
            ext.salvar_rascunho_web(banco, oid, pid, values, connection=c)
            save = dict(d, acao_status='salvar')
            save['cliente_id'] = business._resolver_cliente_os(save, oid, connection=c)
            neg.os_salvar(banco, save, pid, oid, connection=c,
                         staged_attachments=outbox.installed(c))
            cad9.salvar_detalhes(banco, oid, str(d.get('v9_diagnostico','')),
                str(d.get('v9_execucao','')), str(d.get('v9_resultado','')),
                connection=c)
            if d.get('relatorio_tecnico'):
                aten.salvar_rascunho(c,oid,str(d.get('relatorio_tecnico','')),
                                    f'Prestador {session["nome"]}')
            # Uploaded invoice bytes require a durable stage before the commit;
            # reject this combination instead of silently committing only data.
            arquivo = d.get('nota_fiscal')
            if isinstance(arquivo,tuple) and arquivo[0]:
                ext.salvar_nota_fiscal(banco,oid,pid,arquivo[0],arquivo[1],
                   connection=c,staged=outbox.installed(c))
        _flush_staged_files(banco,oid)
        return ui.pagina('Rascunho salvo',card('Rascunho',
            '<p class="good">Rascunho salvo com sucesso.</p>'
            +botao('Voltar à OS',f'{url_os(banco, oid)}')),session)

    cancelar_os = str(d.get('cancelar_os','')).lower() in ('1','on','true','sim')
    acao_status = 'Cancelada' if cancelar_os else str(d.get('acao_status',''))
    d['acao_status'] = acao_status
    if cad9.prestador_admin(banco, pid):
        d['_permitir_trocar_cliente'] = '1'
    if acao_status in ('Pendente','Concluída','Cancelada') and not d.get('modo_envio'):
        d['modo_envio'] = 'encerrar'
    if d.get('modo_envio')!='encerrar':
        raise ValueError('Use Confirmar situação da OS.')
    if acao_status not in ('Pendente','Concluída','Cancelada'):
        raise ValueError('Selecione a situação da OS: Pendente, Concluída ou Cancelada.')
    if acao_status=='Concluída' and not (str(d.get('v9_execucao','')).strip()
            or str(d.get('relatorio_tecnico','')).strip()):
        raise ValueError('Preencha Serviço executado antes de concluir.')
    if acao_status=='Concluída' and not str(d.get('forma_pagamento','')).strip():
        raise ValueError('Selecione a forma de pagamento antes de concluir a OS.')
    if not str(d.get('relatorio_tecnico','')).strip():
        d['relatorio_tecnico']='\n'.join(str(d.get(x,'')).strip()
            for x in ('v9_diagnostico','v9_execucao','v9_resultado')
            if str(d.get(x,'')).strip())
    sem_destinatario = str(d.get('sem_destinatario','')).lower() in ('1','on','true','sim')
    pdf_key = email_key = None
    references = []
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        action = _permission('salvar',d)
        guard = _transaction_guard(banco,principal,oid,action)
        if guard:
            guard(c)
        if acao_status in ('Pendente','Concluída'):
            pub_guard = _transaction_guard(banco,principal,oid,'publish')
            if pub_guard:
                pub_guard(c)
        d['cliente_id'] = business._resolver_cliente_os(d,oid,connection=c)
        if acao_status=='Concluída':
            business._exigir_cliente_os(oid,'concluir a OS',d['cliente_id'],connection=c)
            if not d.get('sem_nota_fiscal') and not c.execute(
                    'SELECT 1 FROM os_notas_fiscais WHERE os_id=? LIMIT 1', (oid,)).fetchone():
                raise ValueError('Anexe a nota fiscal ou marque "Não precisa de nota fiscal" antes de concluir.')
        if not (acao_status=='Cancelada' and ext.administrador(c,pid)):
            prod._os_ativa_responsavel(c,oid,pid)
        use_outbox=outbox.installed(c)
        requires_email=False
        if acao_status=='Concluída' and not sem_destinatario:
            explicit = str(d.get('destinatarios_presente','')) == '1'
            references=d.get('destinatario_sel[]')
            if references is None:
                if explicit:
                    references=[]
                else:
                    person=c.execute('SELECT tipo_pessoa FROM clientes WHERE id=?',
                                     (d['cliente_id'],)).fetchone()
                    references=['cliente'] if person and person['tipo_pessoa']=='Física' else ['sindico','cliente']
            if isinstance(references,str): references=[references]
            if not isinstance(references,list) or any(x not in
                ('cliente','sindico','administradora') for x in references):
                raise ValueError('Seleção de destinatários inválida.')
            if explicit and not references:
                raise ValueError('Selecione ao menos um destinatário ou marque "Não precisa de destinatário".')
            contact=c.execute('''SELECT email,sindico_email,administradora_email
                FROM clientes WHERE id=?''',(d['cliente_id'],)).fetchone()
            fields={'cliente':'email','sindico':'sindico_email',
                    'administradora':'administradora_email'}
            if not contact:
                raise ValueError('Cliente indisponível para seleção de destinatários.')
            if d.get('destinatario_sel[]') is None and not explicit:
                references=[ref for ref in references if contact[fields[ref]]]
            elif any(not contact[fields[ref]] for ref in references):
                raise ValueError('Destinatário selecionado não tem contato válido.')
            addresses=[prod._email_validado(contact[fields[ref]]) for ref in references]
            if not references or not addresses or any(not address for address in addresses):
                raise ValueError('Não há endereço válido para envio. Cadastre um contato ou marque "Não precisa de destinatário".')
            requires_email = True
            # Reject before OS persistence; earlier transactional edits roll back.
            if requires_email:
                outbox.require_installed(c)
        neg.os_salvar(banco,d,pid,oid,connection=c,
                         staged_attachments=use_outbox)
        prod.limpar_rota_ao_iniciar(banco,oid,connection=c)
        if acao_status in ('Pendente','Concluída'):
            prod.registrar_etapa(banco,oid,pid,acao_status,d,connection=c)
        cad9.salvar_detalhes(banco,oid,str(d.get('v9_diagnostico','')),
            str(d.get('v9_execucao','')),str(d.get('v9_resultado','')),
            connection=c)
        if acao_status in fluxo.PUBLICAVEIS and use_outbox:
            revision=_work_revision(c,oid)
            pdf_key=outbox.enqueue_pdf(c,oid,revision,'save-'+acao_status)['operation_key']
            if acao_status=='Concluída' and requires_email:
                email_key=outbox.enqueue_email(c,oid,revision,'send-'+acao_status,
                    recipient_refs=references)['operation_key']

    _flush_staged_files(banco,oid)
    if acao_status in fluxo.PUBLICAVEIS:
        try:
            if pdf_key:
                _publish_postcommit(banco,pdf_key)
            else:
                fluxo.publicar_relatorio(banco,oid)
        except Exception as exc:
            LOG.exception('Encerrada OS %s, mas falhou a publicação do PDF',oid)
            return ui.pagina('OS encerrada — PDF pendente',card('Encerramento salvo',
                '<p>Os dados da OS foram preservados. Falhou apenas a publicação do PDF.</p>'
                +f'<p class="bad">{esc(str(exc)[:400])}</p>'
                +botao('Abrir OS e republicar PDF',f'{url_os(banco, oid)}')),session,503)
        if email_key:
            try:
                from flavors.autoseg.modules import gmail_service
                outbox.deliver_email(banco,email_key,
                    lambda oid,key: gmail_service.enviar_operacao_outbox(banco,oid,key))
            except Exception as exc:
                LOG.exception('OS %s: e-mail não entregue pela outbox',oid)
                return ui.pagina('OS salva — e-mail não entregue',card('Envio de e-mail',
                    '<p>A OS foi salva, mas o envio não foi confirmado. '
                    'Confira o estado da outbox antes de solicitar reenvio.</p>'
                    +f'<p class="bad">{esc(str(exc)[:400])}</p>'
                    +botao('Voltar à OS',f'{url_os(banco, oid)}')),session,503)
    return ui.redir(f'{url_os(banco, oid)}')


def _write_action_publicar(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid = os_id
    acao = partes[2]
    publish_key=None
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        guard = _transaction_guard(banco,principal,oid,'publish')
        guard(c)
        status=c.execute('SELECT status,arquivada FROM ordens_servico WHERE id=?',
                         (oid,)).fetchone()
        if not status or status['arquivada'] or status['status'] not in fluxo.PUBLICAVEIS:
            raise PermissionError('OS indisponível para publicação.')
        publish_key=_enqueue_pdf_if_installed(c,oid,'publish')
    if publish_key:
        _publish_postcommit(banco,publish_key)
    else:
        fluxo.publicar_relatorio(banco,oid)
    return ui.redir(f"{url_os(banco, os_id)}")


def _write_action_atribuir(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid = os_id
    acao = partes[2]
    try:
        destino=int(str(d.get('prestador_destino','')).strip())
    except (TypeError,ValueError):
        raise ValueError('Selecione o prestador de destino.') from None
    ext.atribuir(banco,oid,destino,ator=f'Prestador {s["nome"]}',
                 authorize=_transaction_guard(banco,principal,oid,'assign'))
    if quer_json:
        return ui.send_bytes(json.dumps({'ok':True}).encode(),
                               'application/json; charset=utf-8')
    return ui.redir(f"{url_os(banco, os_id)}")


def _write_action_assumir(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid = os_id
    acao = partes[2]
    ext.assumir(banco,oid,pid,authorize=_transaction_guard(banco,principal,oid,'assume'))
    return ui.redir(f"{url_os(banco, os_id)}")


def _write_action_em_rota(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid = os_id
    acao = partes[2]
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        guard=_transaction_guard(banco,principal,oid,'start')
        if guard is not None:
            guard(c)
        cliente_id=business._persist_form_client(
            d,oid,pid,f'Prestador {s["nome"]}','route',connection=c)
        business._exigir_cliente_os(oid,'colocar em rota',cliente_id,connection=c)
        ext.marcar_em_rota(banco,oid,pid,ator=f'Prestador {s["nome"]}',
                           admin=bool(s.get('admin')),connection=c)
    return ui.redir(f"{url_os(banco, os_id)}")


def _write_action_cancelar_rota(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid = os_id
    acao = partes[2]
    ext.cancelar_em_rota(banco,oid,pid,ator=f'Prestador {s["nome"]}',
                         admin=bool(s.get('admin')),
                         authorize=_transaction_guard(banco,principal,oid,'start'))
    return ui.redir(f"{url_os(banco, os_id)}")


def _write_action_iniciar(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid = os_id
    acao = partes[2]
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        guard=_transaction_guard(banco,principal,oid,'start')
        if guard is not None:
            guard(c)
        cliente_id=business._persist_form_client(
            d,oid,pid,f'Prestador {s["nome"]}','start',connection=c)
        business._exigir_cliente_os(oid,'iniciar o atendimento',cliente_id,connection=c)
        aten.iniciar_assumindo(banco,oid,pid,admin=bool(s.get('admin')),
                               connection=c)
        prod.limpar_rota_ao_iniciar(banco,oid,connection=c)
    return ui.redir(f"{url_os(banco, os_id)}")


def _write_action_reenviar_email(banco, principal, os_id, data, *, ui, session, path, quer_json):
    from flavors.autoseg.modules import portal_prestador as portal
    url_os = portal.url_os
    business = OsBusinessSupport(banco)
    s = session
    pid = s["pid"]
    d = data
    partes = path.strip('/').split('/')
    oid = os_id
    acao = partes[2]
    if 'emails_adicionais' in d:
        raise ValueError('Campo de e-mail avulso não aceito. Cadastre o contato da OS.')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        outbox.require_installed(c)
        request=str(d.get('reenviar_operacao','')).strip()
        ack=str(d.get('confirmar_duplicata','')).lower() in ('1','on','true','sim')
        if not ack or not re.fullmatch(r'[A-Za-z0-9_-]{12,80}',request):
            raise ValueError('Reenvio pode duplicar uma entrega. Confirme e informe a operação.')
        selected=d.get('destinatario_sel[]')
        if isinstance(selected,str): selected=[selected]
        if selected is None: selected=[]
        if not selected or not isinstance(selected,list) or any(x not in ('cliente','sindico','administradora')
                                               for x in selected):
            raise ValueError('Destinatários inválidos.')
        _transaction_guard(banco,principal,oid,'send')(c)
        if ext.responsavel_atual(c,oid)!=pid and not ext.administrador(c,pid):
            raise PermissionError('Sem permissão para reenviar e-mail.')
        recipient=c.execute('''SELECT cl.email,cl.sindico_email,cl.administradora_email
            FROM ordens_servico o JOIN clientes cl ON o.cliente_id=cl.id WHERE o.id=?''',
            (oid,)).fetchone()
        sources={'cliente':'email','sindico':'sindico_email',
                 'administradora':'administradora_email'}
        if not recipient or any(not recipient[sources[ref]] for ref in selected):
            raise ValueError('Atualize o contato antes de selecioná-lo para reenvio.')
        document=c.execute('''SELECT 1 FROM os_documentos
                     WHERE os_id=? AND tipo='relatorio_pdf' ORDER BY versao DESC LIMIT 1''',
                     (oid,)).fetchone()
        if not document:
            raise ValueError('Publique o relatório antes do reenvio.')
        existing=c.execute('''SELECT operation_key,state FROM os_effect_outbox
             WHERE os_id=? AND effect_type='email' AND state IN ('pending','processing')
             ORDER BY id DESC LIMIT 1''',(oid,)).fetchone()
        revision=_work_revision(c,oid)+':'+request
        key=outbox.manual_email_retry(c,oid,revision,'send-manual',
            duplicate_acknowledged=True,recipient_refs=selected)['operation_key']
        if existing and existing['operation_key']!=key:
            raise ValueError('Já há um envio pendente para esta OS.')
        pending=c.execute('SELECT state FROM os_effect_outbox WHERE operation_key=?',
                          (key,)).fetchone()
    from flavors.autoseg.modules import gmail_service
    if outbox.get(banco,key)['state']=='pending':
        outbox.deliver_email(banco,key,
            lambda oid,op: gmail_service.enviar_operacao_outbox(banco,oid,op))
    return ui.redir(f'{url_os(banco, oid)}')


# Permission for an action depends on its *effective* mutation, never the URL
# alone. In particular /os/<id>/salvar cannot close/cancel with edit rights.
PERMISSIONS = {
    'abrir':'edit', 'arquivar':'archive', 'rota':'start',
    'cancelar':'cancel', 'salvar':'edit', 'publicar':'publish',
    'atribuir':'assign', 'assumir':'assume', 'em-rota':'start',
    'cancelar-rota':'start','iniciar':'start', 'reenviar-email':'send',
}
BRANCH_PERMISSIONS = {
    'import_yaml_existing':'edit', 'create_quick':'create', 'import_yaml_new':'create', 'create_full':'create',
    'move_attachment':'attach', 'remove_attachment':'attach','rotate_attachment':'attach','publish_attachment':'attach',
    'photos':'attach','autosave_draft':'edit','save_draft':'edit',
    'rateio':'edit','remove_invoice':'attach','attach_invoice':'attach',
}


def _command(path, data):
    parts=path.strip('/').split('/')
    if len(parts)>=2 and parts[0]=='os' and parts[1] in ('rapida','nova','yaml'):
        if path=='/os/rapida/salvar':return 'create_quick',None
        if path=='/os/yaml':return 'import_yaml_new',None
        if path=='/os/nova/salvar':return 'create_full',None
        raise PermissionError('Operação indisponível.')
    if len(parts)<3 or parts[0]!='os' or not parts[1].isdigit():
        raise PermissionError('Operação indisponível.')
    os_id=int(parts[1]); tail=parts[2:]
    if tail==['yaml']:return 'import_yaml_existing',os_id
    if len(tail)==1 and tail[0] in PERMISSIONS:
        return tail[0],os_id
    if len(tail)==3 and tail[0]=='anexo' and tail[1].isdigit():
        return {'mover':'move_attachment','remover':'remove_attachment','girar':'rotate_attachment',
                'publico':'publish_attachment'}.get(tail[2]),os_id
    if tail==['fotos']:return 'photos',os_id
    if tail==['rascunho','auto']:return 'autosave_draft',os_id
    if tail==['rascunho','salvar']:return 'save_draft',os_id
    if tail==['rateio']:return 'rateio',os_id
    if tail==['nota-fiscal']:return 'attach_invoice',os_id
    if len(tail)==3 and tail[0]=='nota-fiscal' and tail[1].isdigit() and tail[2]=='remover':
        return 'remove_invoice',os_id
    raise PermissionError('Operação indisponível.')


def _permission(action, data):
    permission = PERMISSIONS.get(action) or BRANCH_PERMISSIONS.get(action)
    if permission is None:
        raise PermissionError('Operação indisponível.')
    if action=='salvar':
        # Status transitions are a distinct privilege from ordinary editing.
        status=str(data.get('acao_status','')).strip()
        if str(data.get('cancelar_os','')).lower() in ('1','on','true','sim'):
            return 'cancel'
        if status=='Concluída':return 'conclude'
        if status=='Cancelada':return 'cancel'
    return permission


WRITERS = {
    'import_yaml_existing': _write_import_yaml_existing,
    'create_quick': _write_create_quick,
    'import_yaml_new': _write_import_yaml_new,
    'create_full': _write_create_full,
    'move_attachment': _write_move_attachment,
    'remove_attachment': _write_remove_attachment,
    'rotate_attachment': _write_rotate_attachment,
    'publish_attachment': _write_publish_attachment,
    'photos': _write_photos,
    'autosave_draft': _write_autosave_draft,
    'save_draft': _write_save_draft,
    'rateio': _write_rateio,
    'remove_invoice': _write_remove_invoice,
    'attach_invoice': _write_attach_invoice,
    'abrir': _write_action_abrir,
    'arquivar': _write_action_arquivar,
    'rota': _write_action_rota,
    'cancelar': _write_action_cancelar,
    'salvar': _write_action_salvar,
    'publicar': _write_action_publicar,
    'atribuir': _write_action_atribuir,
    'assumir': _write_action_assumir,
    'em-rota': _write_action_em_rota,
    'cancelar-rota': _write_action_cancelar_rota,
    'iniciar': _write_action_iniciar,
    'reenviar-email': _write_action_reenviar_email,
}

def execute_http(ui,banco,principal,path,data,session,quer_json=False):
    """Resolve command, authorize, *then* invoke the extracted writer."""
    action,os_id=_command(path,data)
    if action is None:
        raise PermissionError('Operação indisponível.')
    with _serialized(os_id):
        # Authorization and writer dispatch are indivisible relative to other
        # HTTP commands in this process. The service owns the actual writer.
        _authorize(banco, principal, os_id, _permission(action,data))
        if action == 'abrir' and os_id is not None:
            if principal is None:
                principal = _provider_context(banco, session)
            with ext.db(banco) as check:
                row = check.execute('SELECT status FROM ordens_servico WHERE id=?',
                                    (os_id,)).fetchone()
                if row and row['status'] == 'Pendente':
                    require_work_item(banco, principal, os_id, 'reopen')
        if action=='reenviar-email':
            _authorize(banco,principal,os_id,'publish')
        if action=='salvar' and str(data.get('acao_status','')) in ('Concluída','Pendente'):
            _authorize(banco,principal,os_id,'publish')
        writer=WRITERS[action]
        return writer(banco,principal,os_id,data,ui=ui,session=session,path=path,
                      quer_json=quer_json)


def authorize_get(banco, principal, path, *, allow_reduced=False):
    """Enforce read authorization independently of the write policy flag."""
    from officina.application.work_item_access import (
        resource_for_work_item, require_document, require_read_work_item,
        shared_queue_item,
    )
    parts=path.strip('/').split('/')
    if len(parts)<2 or parts[0]!='os' or not parts[1].isdigit():
        raise PermissionError('Recurso indisponível.')
    oid=int(parts[1])
    tail=parts[2:]
    if not tail:
        try:
            return require_read_work_item(banco,principal,oid)
        except PermissionError:
            if not allow_reduced:
                raise
            shared_queue_item(banco, principal, oid)
            return None
    if tail==['relatorio.yaml']:
        return require_read_work_item(banco,principal,oid)
    if tail==['rascunho']:
        decision=require_read_work_item(banco,principal,oid)
        if object_policy_flags.enforcement_enabled(banco):
            return require_work_item(banco,principal,oid,'edit')
        return decision
    if tail in (['pdf'],['pdf-preview'],['email'],['nota']):
        if tail==['pdf']:
            require_read_work_item(banco,principal,oid)
            resource=resource_for_work_item(banco,oid)
            doc=Resource('document',oid,resource.organization_id,resource.owner_id,
                         resource.client_id,resource.participant_ids,
                         resource.attributes,resource.client_org_id)
            return ObjectPolicy().require(principal,'download',doc)
        decision=require_read_work_item(banco,principal,oid)
        if object_policy_flags.enforcement_enabled(banco):
            action = 'publish' if tail==['pdf-preview'] else 'send'
            return require_work_item(banco,principal,oid,action)
        return decision
    if len(tail)>=2 and tail[0]=='nota-fiscal' and tail[1].isdigit():
        require_read_work_item(banco,principal,oid)
        return require_document(banco,principal,oid,int(tail[1]),'download')
    raise PermissionError('Recurso indisponível.')



def document_get(banco,principal,os_id,*,ui,session,kind):
    """Document writer, authorization and business logic on the service side."""
    authorize_get(banco,principal,f'/os/{os_id}/{kind}')
    from flavors.autoseg.modules import portal_prestador as portal
    ext=portal.ext
    neg=portal.neg
    prod=portal.prod
    fluxo=portal.fluxo
    policy_shadow=portal.policy_shadow
    LOCK_DOCS=portal.LOCK_DOCS
    LOG=portal.LOG
    Path=portal.Path
    botao=portal.botao
    card=portal.card
    esc=portal.esc
    url_os=portal.url_os
    self=ui
    s=session
    oid=os_id
    with ext.db(banco) as c:
        o=c.execute('SELECT numero_os,status FROM ordens_servico WHERE id=?',(oid,)).fetchone()
        if not o: return self.erro('OS inexistente.',404,s)
    policy_shadow.evaluate_os(
        banco,s['pid'],oid,
        'download' if kind in ('pdf','pdf-preview') else (
            'export' if kind in ('email','nota') else 'read'),
        True,f'documentos:{kind}')
    if kind=='pdf-preview':
        # Preview is deliberately unpublished: no os_documentos row,
        # no e-mail, no status change. Any authenticated provider who
        # can open the OS may download the current draft.
        with LOCK_DOCS:
            arq=ext.gerar_pdf(banco,oid)
            with ext.db(banco) as c:
                neg.audit(c,s['pid'],'Preview de PDF gerado',oid,'pdf-preview')
            nome=f'{Path(arq).stem}_preview.pdf'
            return self.send_bytes(Path(arq).read_bytes(),
                                   'application/pdf',filename=nome)
    prod.controlar_pdf(banco,oid,s['pid'])
    with LOCK_DOCS:
        if kind in ('pdf','email'):
            if o['status'] not in fluxo.FIM:
                return self.erro('PDF disponível somente após o encerramento da OS.',409,s)
            publicado=fluxo.ultimo_documento(banco,oid)
            if not publicado:
                return self.erro('PDF ainda não publicado. Abra esta OS e use Republicar PDF.',409,s)
            pdf=fluxo.validar_pdf_publicado(publicado)
        if kind=='pdf':
            arq=pdf;mime='application/pdf'
        elif kind=='email':
            arq=ext.criar_email_rascunho(banco,oid,pdf,prestador_id=s['pid']);mime='message/rfc822'
        elif kind=='nota':
            arq=ext.criar_rascunho_fiscal(banco,oid);mime='application/json; charset=utf-8'
        else:return self.erro('Arquivo inválido.',404,s)
        with ext.db(banco) as c:
            neg.audit(c,s['pid'],'Documento gerado',oid,kind)
        return self.send_bytes(Path(arq).read_bytes(),mime,filename=Path(arq).name)


def read_anexo(banco,principal,aid,*,ui,session):
    from flavors.autoseg.modules import portal_prestador as portal
    from officina.core import prestadores_ext as ext
    import mimetypes
    from pathlib import Path
    from flavors.autoseg.modules import policy_shadow
    prod=portal.prod
    self=ui
    s=session
    with ext.db(banco) as c:
        row=c.execute("SELECT os_id FROM os_anexos WHERE id=?",(aid,)).fetchone()
    if row is None:
        raise PermissionError('Recurso indisponível.')
    if principal is None:
        raise PermissionError('Recurso indisponível.')
    from officina.application.work_item_access import (
        require_read_work_item, resource_for_work_item)
    require_read_work_item(banco,principal,int(row['os_id']))
    resource=resource_for_work_item(banco,int(row['os_id']))
    document=Resource('document',aid,resource.organization_id,resource.owner_id,
                      resource.client_id,resource.participant_ids,
                      resource.attributes,resource.client_org_id)
    ObjectPolicy().require(principal,'download',document)
    with ext.db(banco) as c:
        x=c.execute('SELECT os_id,nome_original,caminho FROM os_anexos WHERE id=?',(aid,)).fetchone()
    if not x:return self.erro('Anexo não encontrado.',404,s)
    policy_shadow.evaluate_os(
        banco,s['pid'],x['os_id'],'download',True,'anexo')
    arq=Path(x['caminho']).resolve()
    if not arq.is_relative_to(ext.ANEXOS.resolve()):
        return self.erro('Anexo fora do diretório autorizado.',403,s)
    if not arq.is_file():return self.erro('Arquivo de imagem não encontrado.',404,s)
    mime=mimetypes.guess_type(arq.name)[0] or 'application/octet-stream'
    return self.send_bytes(arq.read_bytes(),mime,filename=x['nome_original'])


def read_anexo_thumb(banco,principal,aid,*,ui,session):
    from flavors.autoseg.modules import portal_prestador as portal
    from officina.core import prestadores_ext as ext
    import mimetypes
    from pathlib import Path
    from flavors.autoseg.modules import policy_shadow
    prod=portal.prod
    self=ui
    s=session
    with ext.db(banco) as c:
        row=c.execute("SELECT os_id FROM os_anexos WHERE id=?",(aid,)).fetchone()
    if row is None:
        raise PermissionError('Recurso indisponível.')
    if principal is None:
        raise PermissionError('Recurso indisponível.')
    from officina.application.work_item_access import (
        require_read_work_item, resource_for_work_item)
    require_read_work_item(banco,principal,int(row['os_id']))
    resource=resource_for_work_item(banco,int(row['os_id']))
    document=Resource('document',aid,resource.organization_id,resource.owner_id,
                      resource.client_id,resource.participant_ids,
                      resource.attributes,resource.client_org_id)
    ObjectPolicy().require(principal,'download',document)
    with ext.db(banco) as c:
        x=c.execute('SELECT os_id,caminho FROM os_anexos WHERE id=?',(aid,)).fetchone()
    if not x:return self.erro('Anexo não encontrado.',404,s)
    policy_shadow.evaluate_os(
        banco,s['pid'],x['os_id'],'view',True,'anexo_thumb')
    arq=Path(x['caminho']).resolve()
    if not arq.is_relative_to(ext.ANEXOS.resolve()):
        return self.erro('Anexo fora do diretório autorizado.',403,s)
    return self.send_bytes(ext.thumb_imagem(arq),'image/jpeg',
                           cache='private, max-age=31536000, immutable')
