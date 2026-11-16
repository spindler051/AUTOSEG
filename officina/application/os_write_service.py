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
        return cls(actor_id=int(actor_id), fields=data, os_id=values.os_id)

    @classmethod
    def from_web(cls, values: Mapping[str, Any], actor_id: int,
                 os_id: int | None = None) -> 'OSCommand':
        return cls(actor_id=int(actor_id), fields=dict(values), os_id=os_id)


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
