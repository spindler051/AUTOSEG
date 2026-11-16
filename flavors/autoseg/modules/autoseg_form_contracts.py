"""Presentation-neutral provider form descriptions for Officina Web and GTK.

These descriptors contain no UI implementation or authorization decision. The
writing service always reloads policy, identity, object links and current data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Field:
    id: str
    label: str
    help: str = ''
    type: str = 'text'
    required: bool = False
    default: Any = ''
    validation: str = ''
    hint: str = ''
    visibility: str = ''
    options: tuple[str, ...] = ()
    surfaces: tuple[str, ...] = ('web', 'gtk')
    surface_reason: str = ''
    gtk_attribute: str = ''
    web_name: str = ''

    @property
    def input_name(self) -> str:
        return self.web_name or self.id

    @property
    def widget_attribute(self) -> str:
        return self.gtk_attribute or self.id


@dataclass(frozen=True)
class Form:
    id: str
    section: str
    fields: tuple[Field, ...]

    def field(self, name: str) -> Field:
        return next(field for field in self.fields if field.id == name)

    def on(self, surface: str) -> tuple[Field, ...]:
        return tuple(field for field in self.fields if surface in field.surfaces)


def _customer(id: str, label: str, *, visibility='nome', **kwargs) -> Field:
    return Field(id, label, visibility=visibility, **kwargs)


CUSTOMER = Form('customer', 'customers', (
    _customer('tipo_pessoa', 'Tipo de pessoa', visibility='admin', type='select',
              required=True, default='Jurídica', validation='customer.person_type',
              options=('Jurídica', 'Física')),
    _customer('documento', 'CPF / CNPJ', visibility='documento',
              validation='customer.document', hint='CPF ou CNPJ válido para o tipo de pessoa.'),
    _customer('nome', 'Nome / Razão Social', required=True, validation='customer.name',
              hint='Nome ou razão social é obrigatório.'),
    _customer('nome_fantasia', 'Nome fantasia', visibility='admin'),
    _customer('status', 'Situação', visibility='edit', type='select',
              required=True, default='Ativo', validation='customer.status',
              options=('Ativo', 'Inativo', 'Prospect')),
    _customer('cep', 'CEP', visibility='admin', validation='customer.postal_code'),
    _customer('endereco', 'Rua / Logradouro', visibility='endereco'),
    _customer('numero', 'Número', visibility='admin', gtk_attribute='numero_end'),
    _customer('complemento', 'Complemento', visibility='admin'),
    _customer('bairro', 'Bairro', visibility='admin'),
    _customer('cidade', 'Cidade', visibility='endereco'),
    _customer('uf', 'UF', visibility='admin'),
    _customer('telefone', 'Telefone', visibility='telefone'),
    _customer('email', 'E-mail', visibility='email', validation='customer.email'),
    _customer('sindico_nome', 'Nome do síndico / responsável', visibility='admin'),
    _customer('sindico_telefone', 'Telefone do síndico', visibility='admin'),
    _customer('sindico_email', 'E-mail do síndico', visibility='admin'),
    _customer('administradora', 'Imobiliária / administradora', visibility='admin'),
    _customer('administradora_telefone', 'Telefone da administradora', visibility='admin'),
    _customer('administradora_email', 'E-mail da imobiliária / administradora', visibility='admin'),
    _customer('observacoes', 'Observações', visibility='admin', type='textarea'),
))


def customer_fields(banco, principal, *, customer_id=None) -> tuple[Field, ...]:
    """Server-only projection. Never trust submitted visibility or role flags."""
    from officina.application import work_item_access as access
    from officina.application.live_provider import resolve as live_provider
    principal = live_provider(banco, principal)
    if customer_id is None:
        access.require_customer_create(principal)
        return CUSTOMER.fields
    access.require_customer_read(banco, principal, int(customer_id))
    access.require_customer_write(banco, principal, int(customer_id))
    if principal.role == 'admin' and access.can_read_all(principal, 'customer'):
        return CUSTOMER.fields
    scoped = access.involved_customer_field_scopes(principal)
    return tuple(field for field in CUSTOMER.fields
                 if field.visibility == 'edit' or field.visibility in scoped)



WORK = Form('work', 'work', (
    Field('cliente_id', 'Cliente', required=True, validation='work.customer_id'),
    Field('tecnico', 'Atendido por (cliente no local)'),
    Field('forma_pagamento', 'Forma de pagamento', type='select',
          options=('PIX', 'Transferência', 'Dinheiro', 'Cartão', 'Boleto', 'Outro'),
          validation='work.payment_method'),
    Field('urgencia', 'Urgência', type='select', default='Normal',
          options=('Baixa', 'Normal', 'Alta')),
    Field('descricao', 'Descrição do serviço', type='textarea', required=True,
          validation='work.description'),
    Field('valor_mao_obra', 'Valor do serviço — mão de obra (R$)', type='money',
          validation='work.labour', required=True, gtk_attribute='mao_obra'),
    Field('valor_total', 'Valor final da OS (R$)', type='money',
          validation='work.total', gtk_attribute='total', web_name='valor_total_override'),
    Field('valor_materiais', 'Materiais sem itens detalhados (R$)', type='money',
          gtk_attribute='materiais_valor', web_name='valor_materiais_manual'),
    Field('custo_materiais', 'Custo real dos materiais (R$)', type='money',
          validation='work.material_cost'),
    Field('material_item[]', 'Material', type='text',
          validation='work.material_item', gtk_attribute='materiais'),
    Field('material_qtd[]', 'Quantidade', type='number',
          validation='work.material_quantity', gtk_attribute='materiais'),
    Field('material_unidade[]', 'Unidade', type='select',
          gtk_attribute='materiais'),
    Field('material_unit[]', 'Valor unitário / total (R$)', type='money',
          validation='work.material_unit_price', gtk_attribute='materiais'),
    Field('observacoes', 'Observações gerais', type='textarea'),
    Field('texto_adicional', 'Texto adicional', type='textarea'),
    Field('tempo_horas', 'Tempo de atendimento (horas)', type='number'),
    Field('base_percentuais', 'Composição dos valores', type='select',
          validation='work.composition'),
    Field('composicao_yaml', 'Composição declarativa', type='textarea',
          validation='work.composition'),
    Field('status', 'Situação', type='select', gtk_attribute='status',
          web_name='acao_status'),
    Field('relatorio_tecnico', 'Relatório técnico', type='textarea',
          validation='work.close_report', gtk_attribute='relatorio'),
    Field('motivo_encerramento', 'Motivo do cancelamento', type='textarea',
          validation='work.cancel_reason', gtk_attribute='motivo'),
    Field('enviar_email', 'Enviar relatório por e-mail ao concluir', type='checkbox',
          gtk_attribute='enviar_email', web_name='sem_destinatario'),
    Field('destinatario_sel[]', 'Destinatários do relatório', type='checkbox',
          gtk_attribute='enviar_email'),
    Field('v9_diagnostico', 'Diagnóstico', type='textarea',
          gtk_attribute='relatorio'),
    Field('v9_execucao', 'Serviço executado', type='textarea',
          gtk_attribute='relatorio'),
    Field('v9_resultado', 'Resultado e testes', type='textarea',
          gtk_attribute='relatorio'),
    Field('anexo_legenda[]', 'Legenda da foto', gtk_attribute='anexos_label'),
    Field('anexo_incluir[]', 'Incluir foto no PDF', type='checkbox',
          gtk_attribute='anexos_label'),
    Field('fotos', 'Fotos do relatório', type='text', gtk_attribute='anexos_label'),
))

FORMS = (CUSTOMER, WORK)


def work_fields(banco, principal, *, os_id=None) -> tuple[Field, ...]:
    """Resolve OS field access without trusting a client-provided role or ID."""
    from officina.application.work_item_access import require_create, require_work_item
    if principal is None:
        raise PermissionError('Identidade obrigatória.')
    if os_id is None:
        require_create(banco, principal)
        return tuple(field for field in WORK.fields
                     if field.id not in ('status','relatorio_tecnico','motivo_encerramento',
                                        'enviar_email','destinatario_sel[]'))
    require_work_item(banco, principal, int(os_id), 'edit')
    return WORK.fields
