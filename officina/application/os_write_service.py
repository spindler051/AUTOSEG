"""Transport-neutral service-order command boundary.

``portal_negocios.os_salvar`` is the only SQL writer for headers, materials,
composition, stock, report drafts and domain closing. Neither a GTK widget
nor an HTTP request may implement those writes a second time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from officina.core import portal_negocios as business


@dataclass(frozen=True)
class OSCommand:
    """Canonical write request; accepts the full existing Web form vocabulary.

    Attachment bytes, recipient references and rateio inputs deliberately stay
    in ``fields``: the domain writer validates them, not each transport.
    """

    actor_id: int
    fields: Mapping[str, Any]
    os_id: int | None = None

    @classmethod
    def from_desktop(cls, values, actor_id: int) -> 'OSCommand':
        """Translate OSInput to the Web writer's full, validated input schema."""
        materials = tuple(values.materiais or ())
        data = {
            'cliente_id': str(values.cliente_id),
            'tecnico': values.tecnico,
            'descricao': values.descricao,
            'valor_mao_obra': str(values.valor_mao_obra),
            'valor_materiais_manual': str(values.valor_materiais if not materials else 0),
            'custo_materiais': str(values.custo_materiais),
            'forma_pagamento': values.forma_pagamento,
            'urgencia': values.urgencia,
            'observacoes': values.observacoes,
            'texto_adicional': values.texto_adicional,
            'tempo_horas': str(values.tempo_horas),
            'base_percentuais': values.base_percentuais,
            'dados_incompletos': str(int(values.dados_incompletos)),
            'materiais_presentes': '1',
            'material_item[]': [str(m.get('item') or '') for m in materials],
            'material_qtd[]': ['' if m.get('quantidade') is None else str(m['quantidade'])
                              for m in materials],
            'material_unidade[]': [str(m.get('unidade') or '') for m in materials],
            'material_unit[]': [str(m.get('valor_unitario') or 0) for m in materials],
            'relatorio_tecnico': values.relato,
            'motivo_encerramento': values.motivo,
            'acao_status': values.acao or 'salvar',
            'modo_envio': ('encerrar' if values.acao in
                           ('Pendente', 'Concluída', 'Cancelada') else 'rascunho'),
            'imagens_encerramento[]': list(values.imagens),
            'sem_destinatario': '1' if values.sem_destinatario else '0',
            'sem_nota_fiscal': '1' if values.sem_nota_fiscal else '0',
            'v9_diagnostico': values.v9_diagnostico,
            'v9_execucao': values.v9_execucao,
            'v9_resultado': values.v9_resultado,
            'rateio_manual_tecnico': list(values.rateio_manual_tecnico),
            'rateio_manual_valor': list(values.rateio_manual_valor),
        }
        # The domain conclusion path uses rateio_tecnico[] / rateio_valor[].
        # Alias the C2 form inputs, never write rateios in the transport.
        if values.acao == 'Concluída':
            data['rateio_tecnico[]'] = list(values.rateio_manual_tecnico)
            data['rateio_valor[]'] = list(values.rateio_manual_valor)
        # The negotiated total is an explicit override only when different
        # from the calculated service + material values.
        material_total = sum((float(m.get('valor_unitario') or 0) if
            m.get('quantidade') is None else float(m['quantidade']) *
            float(m.get('valor_unitario') or 0)) for m in materials)
        calculated = float(values.valor_mao_obra) + (material_total if materials
                     else float(values.valor_materiais))
        if abs(float(values.valor_total) - calculated) > 0.005:
            data['valor_total_override'] = str(values.valor_total)
        if values.destinatarios is not None:
            data['destinatarios_presente'] = '1'
            data['destinatario_sel[]'] = list(values.destinatarios)
        if values.nota_fiscal:
            data['nota_fiscal'] = values.nota_fiscal
        if values.confirmar_numero_os:
            data['confirmar_numero_os'] = values.confirmar_numero_os
        if values.composicao_yaml is not None:
            data['composicao_yaml'] = values.composicao_yaml
        elif values.composicao_json:
            # GTK historically submits computed composition JSON, while the
            # portal accepts a declarative source. Translate the source, not
            # a second SQL writer or an unchecked client total.
            from officina.core import composicao
            saved = composicao.de_json(values.composicao_json)
            if isinstance(saved, dict):
                data['cobrar_visita'] = '0' if saved.get('sem_visita') else '1'
            if isinstance(saved, dict) and saved.get('declarativa'):
                data['composicao_yaml'] = _declarative_fields(saved.get('componentes', []))
            elif isinstance(saved, dict) and saved.get('base_percentuais') and not saved.get('simplificada'):
                data['aplicar_composicao'] = '1'
        return cls(actor_id=int(actor_id), fields=data, os_id=values.os_id)

    @classmethod
    def from_web(cls, values: Mapping[str, Any], actor_id: int,
                 os_id: int | None = None) -> 'OSCommand':
        return cls(actor_id=int(actor_id), fields=dict(values), os_id=os_id)


def _declarative_fields(components):
    """Convert saved modular values to the canonical declarative input.

    Do not trust or persist ``composicao_json`` directly from any client:
    ``portal_negocios.os_salvar`` revalidates these fields and recomputes it.
    """
    if not isinstance(components, list) or not components:
        raise ValueError('Composição declarativa inválida.')
    result = []
    for component in components:
        if not isinstance(component, dict):
            raise ValueError('Componente da OS inválido.')
        item = {
            'id': component.get('id'),
            'nome': component.get('nome'),
            'valor': f'{int(component.get("valor_centavos") or 0) / 100:.2f}',
        }
        if component.get('parent_keeps_remainder'):
            item['parent_keeps_remainder'] = True
        if component.get('filhos'):
            item['filhos'] = _declarative_fields(component['filhos'])
        result.append(item)
    return result


def write_data(banco, command: OSCommand, *, connection=None,
               authorize=None, silent=False, staged_attachments=False) -> int:
    """Write domain data using the existing, authoritative transaction.

    If a connection is supplied, its caller must hold BEGIN IMMEDIATE and
    complete or roll back the transaction. The optional authorization callback
    runs in the same transaction as the SQL changes.
    """
    if command.actor_id <= 0:
        raise PermissionError('Identidade obrigatória para alterar OS.')
    return business.os_salvar(
        banco, command.fields, command.actor_id, command.os_id,
        silent=silent, connection=connection, authorize=authorize,
        staged_attachments=staged_attachments)


@dataclass(frozen=True)
class OSSaveResult:
    """Committed OS state and status of the independently delivered effects."""

    os_id: int
    criada: bool
    encerrada: bool
    status_anterior: str
    dados_incompletos: int
    rascunho: bool = False


class RevokedProviderError(PermissionError):
    """Provider access was revoked before the transactional OS write."""


class PostCommitEffectError(RuntimeError):
    """The OS is committed, but a recoverable post-commit effect failed."""

    def __init__(self, result: OSSaveResult, effect: str, reason: Exception):
        self.result = result
        self.effect = effect
        super().__init__(f'OS {result.os_id} salva; {effect} pendente: {reason}')


def _authorize_locked(connection, principal, oid, action, extra_authorize=None):
    """Authenticate the live provider and authorize the object under the lock."""
    from officina.application.object_policy import ObjectPolicy, Resource
    from officina.application.work_item_access import require_work_item_locked
    from officina.core import prestadores_ext as ext

    if not connection.in_transaction:
        raise RuntimeError('OS authorization requires BEGIN IMMEDIATE.')
    if (principal is None or principal.organization_id != 'autoseg'
            or type(principal.provider_id) is not int
            or principal.provider_id <= 0):
        raise PermissionError('Identidade obrigatória para alterar OS.')
    if not principal.active:
        raise RevokedProviderError('Prestador inativo ou vínculo revogado.')
    pid = principal.provider_id
    provider = connection.execute('''SELECT ativo,excluido FROM prestadores
        WHERE id=?''', (pid,)).fetchone()
    if not provider or not provider['ativo'] or provider['excluido']:
        raise RevokedProviderError('Prestador inativo ou vínculo revogado.')
    role = 'admin' if ext.administrador(connection, pid) else 'employee'
    if principal.role != role:
        raise PermissionError('O papel do prestador foi alterado.')
    if extra_authorize is not None:
        extra_authorize(connection)
    if oid is None:
        ObjectPolicy().require(principal, 'create',
                               Resource('work_item', organization_id='autoseg'))
        return
    order = connection.execute('''SELECT status,arquivada FROM ordens_servico
        WHERE id=?''', (int(oid),)).fetchone()
    if not order or order['arquivada'] or order['status'] not in ext.ATIVAS:
        raise PermissionError('OS indisponível para alteração.')
    require_work_item_locked(connection, principal, int(oid), action)


def _revision(connection, oid: int) -> str:
    event = connection.execute('''SELECT COALESCE(MAX(id),0)
        FROM os_eventos WHERE os_id=?''', (oid,)).fetchone()[0]
    row = connection.execute('''SELECT status,atualizado_em FROM ordens_servico
        WHERE id=?''', (oid,)).fetchone()
    if row is None:
        raise ValueError('OS não encontrada.')
    return f'{int(event)}:{row["status"]}:{row["atualizado_em"]}'


def _flush_files(banco, oid: int) -> None:
    """Promote staged attachments only after the OS transaction has committed."""
    from officina.core import prestadores_ext as ext, os_effect_outbox as outbox
    with ext.db(banco) as connection:
        if not outbox.installed(connection):
            return
        rows = connection.execute('''SELECT operation_key FROM os_effect_outbox
            WHERE os_id=? AND effect_type='file' AND state IN ('pending','failed')
            ORDER BY id''', (oid,)).fetchall()
    for row in rows:
        outbox.publish_file(banco, row['operation_key'])


def _recipient_refs(connection, cliente_id: int, data: Mapping[str, Any]):
    """Resolve *references*, never arbitrary e-mail addresses from client data."""
    from officina.core import produtividade_os as prod

    explicit = str(data.get('destinatarios_presente', '')) == '1'
    refs = data.get('destinatario_sel[]')
    if refs is None:
        if explicit:
            refs = []
        else:
            person = connection.execute('SELECT tipo_pessoa FROM clientes WHERE id=?',
                                        (cliente_id,)).fetchone()
            refs = ['cliente'] if person and person['tipo_pessoa'] == 'Física' else [
                'sindico', 'cliente']
    if isinstance(refs, str):
        refs = [refs]
    if not isinstance(refs, list) or any(x not in
        ('cliente', 'sindico', 'administradora') for x in refs):
        raise ValueError('Seleção de destinatários inválida.')
    if explicit and not refs:
        raise ValueError('Selecione ao menos um destinatário ou marque "Não precisa de destinatário".')
    contact = connection.execute('''SELECT email,sindico_email,administradora_email
        FROM clientes WHERE id=?''', (cliente_id,)).fetchone()
    fields = {'cliente': 'email', 'sindico': 'sindico_email',
              'administradora': 'administradora_email'}
    if not contact:
        raise ValueError('Cliente indisponível para seleção de destinatários.')
    if data.get('destinatario_sel[]') is None and not explicit:
        refs = [ref for ref in refs if contact[fields[ref]]]
    elif any(not contact[fields[ref]] for ref in refs):
        raise ValueError('Destinatário selecionado não tem contato válido.')
    addresses = [prod._email_validado(contact[fields[ref]]) for ref in refs]
    if not refs or not addresses or any(not address for address in addresses):
        raise ValueError('Não há endereço válido para envio. Cadastre um contato '
                         'ou marque "Não precisa de destinatário".')
    return refs


def salvar(banco, command: OSCommand, principal, *, authorize=None,
           name: str = '') -> OSSaveResult:
    """One locked data write and the same recoverable post-commit effects.

    This service is used by HTTP, GTK local, and the Desktop API. Callers own
    neither OS SQL nor PDF/email delivery. The outbox intent is transactional;
    publishing/sending happens *after* commit. An effect error never implies
    the OS itself rolled back.
    """
    from officina.application.os_business_support import OsBusinessSupport
    from officina.core import (prestadores_ext as ext, atendimento_os as aten,
                               fluxo_os as fluxo, cadastros_v9 as cad9,
                               produtividade_os as prod,
                               os_effect_outbox as outbox)
    from flavors.autoseg.modules import gmail_service
    import logging

    if (principal is None or principal.provider_id is None or
            int(command.actor_id) != int(principal.provider_id)):
        raise PermissionError('Identidade da OS inválida.')
    d = dict(command.fields)
    if 'emails_adicionais' in d:
        raise ValueError('Campo de e-mail avulso não aceito. Cadastre o contato da OS.')
    oid = command.os_id
    pid = principal.provider_id
    raw_action = 'Cancelada' if str(d.get('cancelar_os', '')).lower() in (
        '1', 'on', 'true', 'sim') else str(d.get('acao_status', '') or 'salvar')
    d['acao_status'] = raw_action
    draft = d.get('modo_envio') in ('rascunho', 'salvar') or raw_action == 'salvar'
    if not draft and raw_action not in ('Pendente', 'Concluída', 'Cancelada'):
        raise ValueError('Selecione a situação da OS: Pendente, Concluída ou Cancelada.')
    if draft:
        # Draft never changes the workflow status, even if the UI has a
        # previously selected closing option.
        raw_action = d['acao_status'] = 'salvar'
    if not draft and d.get('modo_envio', 'encerrar') != 'encerrar':
        raise ValueError('Use Confirmar situação da OS.')
    if raw_action == 'Concluída' and not (str(d.get('v9_execucao', '')).strip()
            or str(d.get('relatorio_tecnico', '')).strip()):
        raise ValueError('Preencha Serviço executado antes de concluir.')
    if raw_action == 'Concluída' and not str(d.get('forma_pagamento', '')).strip():
        raise ValueError('Selecione a forma de pagamento antes de concluir a OS.')
    if not str(d.get('relatorio_tecnico', '')).strip():
        d['relatorio_tecnico'] = '\n'.join(str(d.get(field, '')).strip()
            for field in ('v9_diagnostico', 'v9_execucao', 'v9_resultado')
            if str(d.get(field, '')).strip())

    business = OsBusinessSupport(banco)
    pdf_key = email_key = None
    outbox_available = False
    previous_status = ''
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        action = ('conclude' if raw_action == 'Concluída' else
                  'cancel' if raw_action == 'Cancelada' else 'edit')
        _authorize_locked(c, principal, oid, action, authorize)
        if not draft and raw_action in ('Pendente', 'Concluída'):
            _authorize_locked(c, principal, oid, 'publish')
        if oid is not None:
            row = c.execute('SELECT status FROM ordens_servico WHERE id=?',
                            (oid,)).fetchone()
            previous_status = str(row['status'] or '') if row else ''
        # This flag is set using the current DB identity, never an HTTP field.
        if ext.administrador(c, pid):
            d['_permitir_trocar_cliente'] = '1'
        else:
            d.pop('_permitir_trocar_cliente', None)
        d['cliente_id'] = business._resolver_cliente_os(d, oid, connection=c)
        outbox_available = outbox.installed(c)
        if not draft and oid is None:
            raise ValueError('Salve a OS antes de alterar a situação.')
        if not draft and raw_action == 'Concluída':
            business._exigir_cliente_os(oid, 'concluir a OS',
                                       d['cliente_id'], connection=c)
            # A simultaneous invoice upload is staged before validation.
            invoice = d.get('nota_fiscal')
            if isinstance(invoice, tuple) and invoice[0]:
                outbox.require_installed(c)
                ext.salvar_nota_fiscal(banco, oid, pid, invoice[0], invoice[1],
                    connection=c, staged=outbox_available)
            if str(d.get('sem_nota_fiscal', '')).lower() not in ('1', 'on', 'true', 'sim') and not c.execute('''SELECT 1
                FROM os_notas_fiscais WHERE os_id=? LIMIT 1''', (oid,)).fetchone():
                raise ValueError('Anexe a nota fiscal ou marque "Não precisa de nota fiscal" antes de concluir.')
        if not draft and oid is not None and not (
                raw_action == 'Cancelada' and ext.administrador(c, pid)):
            prod._os_ativa_responsavel(c, oid, pid)
        refs = []
        if not draft and raw_action == 'Concluída' and not str(
                d.get('sem_destinatario', '')).lower() in ('1', 'on', 'true', 'sim'):
            refs = _recipient_refs(c, d['cliente_id'], d)
            outbox.require_installed(c)
        if draft and oid is not None:
            values = {k: v for k, v in d.items()
                      if k not in ('csrf', 'modo_envio', 'nota_fiscal')}
            ext.salvar_rascunho_web(banco, oid, pid, values, connection=c)
        oid = write_data(banco, OSCommand.from_web(d, pid, oid),
                         connection=c, staged_attachments=outbox_available)
        if command.os_id is None:
            ext.assumir(banco, oid, pid, connection=c)
        if draft and d.get('relatorio_tecnico'):
            aten.salvar_rascunho(c, oid, str(d['relatorio_tecnico']),
                                 f'Prestador {name or pid}')
        if draft:
            invoice = d.get('nota_fiscal')
            if isinstance(invoice, tuple) and invoice[0]:
                outbox.require_installed(c)
                ext.salvar_nota_fiscal(banco, oid, pid, invoice[0], invoice[1],
                                      connection=c, staged=outbox_available)
        if not draft and raw_action in ('Pendente', 'Concluída', 'Cancelada'):
            prod.limpar_rota_ao_iniciar(banco, oid, connection=c)
            if raw_action in ('Pendente', 'Concluída'):
                prod.registrar_etapa(banco, oid, pid, raw_action, d, connection=c)
        cad9.salvar_detalhes(banco, oid, str(d.get('v9_diagnostico', '')),
                            str(d.get('v9_execucao', '')),
                            str(d.get('v9_resultado', '')), connection=c)
        if not draft and raw_action in fluxo.PUBLICAVEIS and outbox_available:
            revision = _revision(c, oid)
            pdf_key = outbox.enqueue_pdf(c, oid, revision,
                                         'save-' + raw_action)['operation_key']
            if raw_action == 'Concluída' and refs:
                email_key = outbox.enqueue_email(c, oid, revision,
                    'send-' + raw_action, recipient_refs=refs)['operation_key']
        incomplete = int(d.get('dados_incompletos') or 0)

    result = OSSaveResult(oid, command.os_id is None, raw_action in fluxo.FIM,
                          previous_status, incomplete, rascunho=draft)
    # Every transport uses these exact same post-commit operations.
    try:
        _flush_files(banco, oid)
    except Exception as error:
        logging.getLogger('autoseg.os_writer').exception(
            'OS %s committed but attachment promotion failed', oid)
        raise PostCommitEffectError(result, 'publicação de anexos', error) from error
    if not draft and raw_action in fluxo.PUBLICAVEIS:
        try:
            if pdf_key:
                outbox.publish_pdf(banco, pdf_key)
            else:
                fluxo.publicar_relatorio(banco, oid)
        except Exception as error:
            logging.getLogger('autoseg.os_writer').exception(
                'OS %s committed but PDF publication failed', oid)
            raise PostCommitEffectError(result, 'publicação do PDF', error) from error
    if email_key:
        try:
            outbox.deliver_email(banco, email_key,
                lambda work_id, key: gmail_service.enviar_operacao_outbox(
                    banco, work_id, key))
        except Exception as error:
            logging.getLogger('autoseg.os_writer').exception(
                'OS %s committed but email dispatch failed', oid)
            raise PostCommitEffectError(result, 'envio de e-mail', error) from error
    return result
