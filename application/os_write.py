"""Transactional OS write used by the desktop dialog.

The SQL and domain calls live here so the GTK shell only validates form fields
and calls the application service. Behaviour is kept identical to the previous
desktop implementation: OS header, materials, stock reconciliation, events,
draft report and optional closing.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import atendimento_os as aten
import estoque_materiais as estoque
import fluxo_os as fluxo
import prestadores_ext as ext
from banco import proximo_numero_os

from application.contracts import OSInput, OSResultado, ValidacaoError


def salvar_os(banco, dados: OSInput) -> OSResultado:
    anterior = None
    status_anterior = ''
    with ext.db(banco) as conexao:
        cursor = conexao.cursor()
        if dados.os_id is not None:
            anterior = cursor.execute(
                'SELECT * FROM ordens_servico WHERE id=?', (dados.os_id,)).fetchone()
            if anterior is None:
                raise ValidacaoError('A OS já não existe no banco de dados.')
            status_anterior = str(anterior['status'] or '')
            if anterior['origem'] == 'Portal':
                original = cursor.execute(
                    'SELECT cliente_id,descricao_original FROM os_solicitacoes WHERE os_id=?',
                    (dados.os_id,)).fetchone()
                if original:
                    dados = _substituir_origem(dados, original)

        materiais_anteriores = []
        if dados.os_id is not None:
            materiais_anteriores = [dict(linha) for linha in cursor.execute(
                'SELECT item,quantidade,unidade,valor_unitario FROM materiais_os '
                'WHERE os_id=? ORDER BY id', (dados.os_id,)).fetchall()]

        if dados.os_id is None:
            numero_os = proximo_numero_os(cursor)
            cursor.execute(
                '''INSERT INTO ordens_servico
                (numero_os,cliente_id,data_abertura,tecnico,descricao,valor_mao_obra,
                 valor_materiais,custo_materiais,valor_total,forma_pagamento,status,urgencia,observacoes,
                 texto_adicional,dados_incompletos,tempo_horas,composicao_json,base_percentuais,criado_em)
                VALUES(?,?,?,?,?,?,?,?,?,?,'Aberta',?,?,?,?,?,?,?,?)''',
                (numero_os, dados.cliente_id, datetime.now().strftime('%d/%m/%Y %H:%M'),
                 dados.tecnico, dados.descricao, dados.valor_mao_obra,
                 dados.valor_materiais, dados.custo_materiais, dados.valor_total,
                 dados.forma_pagamento, dados.urgencia, dados.observacoes,
                 dados.texto_adicional, dados.dados_incompletos, dados.tempo_horas,
                 dados.composicao_json, dados.base_percentuais,
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            os_id = cursor.lastrowid
            aten.registrar_solicitacao(
                cursor, os_id, dados.cliente_id, dados.descricao,
                dados.observacoes, 'App')
        else:
            cursor.execute(
                '''UPDATE ordens_servico SET cliente_id=?,tecnico=?,descricao=?,
                valor_mao_obra=?,valor_materiais=?,custo_materiais=?,valor_total=?,forma_pagamento=?,
                urgencia=?,observacoes=?,texto_adicional=?,dados_incompletos=?,tempo_horas=?,
                composicao_json=?,base_percentuais=?,atualizado_em=? WHERE id=?''',
                (dados.cliente_id, dados.tecnico, dados.descricao,
                 dados.valor_mao_obra, dados.valor_materiais, dados.custo_materiais,
                 dados.valor_total, dados.forma_pagamento, dados.urgencia,
                 dados.observacoes, dados.texto_adicional, dados.dados_incompletos,
                 dados.tempo_horas, dados.composicao_json, dados.base_percentuais,
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S'), dados.os_id))
            os_id = dados.os_id

        _salvar_materiais(cursor, os_id, materiais_anteriores, dados.materiais)
        estoque.reconciliar_os_conexao(cursor, os_id, 'Desktop')

        if anterior is not None:
            _registrar_edicao(cursor, os_id, anterior, dados)
        else:
            ext.evento(cursor, os_id, 'OS criada',
                       'Ordem de serviço cadastrada pelo administrador.')

        if dados.os_id is not None:
            aten.salvar_rascunho(cursor, os_id, dados.relato, 'Administrador desktop')
        if dados.relato and dados.acao:
            ext.evento(cursor, os_id, 'Relatório técnico', dados.relato)
        if dados.acao == 'Pendente':
            alterou = cursor.execute(
                "UPDATE ordens_servico SET status='Pendente' WHERE id=? AND status IN ('Aberta','Iniciada','Pendente')",
                (os_id,)).rowcount
            if alterou != 1:
                raise ValidacaoError('Esta OS não pode ser colocada como pendente.')
            ext.evento(cursor, os_id, 'Pendência',
                       'OS mantida pendente pelo administrador. Consulte o relatório técnico.')

        encerrada = dados.acao in fluxo.FIM
        if encerrada:
            for nome, conteudo in dados.imagens:
                ext.registrar_imagem_transacao(
                    cursor, os_id, None, Path(nome).name, conteudo)
            fluxo.aplicar_encerramento(
                cursor, os_id, dados.acao, dados.relato, dados.motivo,
                ator='Administrador desktop')

    return OSResultado(
        os_id=os_id,
        criada=dados.os_id is None,
        encerrada=encerrada,
        status_anterior=status_anterior,
        dados_incompletos=dados.dados_incompletos,
    )


def _substituir_origem(dados: OSInput, original) -> OSInput:
    return OSInput(
        **{**dados.__dict__,
           'cliente_id': int(original['cliente_id']),
           'descricao': str(original['descricao_original'] or '')}
    )


def _salvar_materiais(cursor, os_id, anteriores, atuais) -> None:
    antes = [(m['item'], None if m['quantidade'] is None else float(m['quantidade']),
              str(m['unidade'] or ''), float(m['valor_unitario'] or 0))
             for m in anteriores]
    depois = [(m.get('item', ''),
               None if m.get('quantidade') is None else float(m['quantidade']),
               str(m.get('unidade') or ''),
               float(m.get('valor_unitario') or 0)) for m in atuais]
    if antes == depois:
        return
    cursor.execute('DELETE FROM materiais_os WHERE os_id=?', (os_id,))
    for material in atuais:
        quantidade = material.get('quantidade')
        quantidade = None if quantidade is None else float(quantidade)
        valor = float(material.get('valor_unitario') or 0)
        unidade = str(material.get('unidade') or '').strip()[:40]
        cursor.execute(
            'INSERT INTO materiais_os(os_id,item,quantidade,unidade,'
            'valor_unitario,valor_total) VALUES(?,?,?,?,?,?)',
            (os_id, material.get('item', ''), quantidade, unidade,
             valor, (quantidade or 0) * valor))


def _registrar_edicao(cursor, os_id, anterior, dados: OSInput) -> None:
    antes = {
        'cliente_id': anterior['cliente_id'],
        'tecnico': anterior['tecnico'] or '',
        'descricao': anterior['descricao'] or '',
        'valor_mao_obra': float(anterior['valor_mao_obra'] or 0),
        'valor_materiais': float(anterior['valor_materiais'] or 0),
        'custo_materiais': float(anterior['custo_materiais'] or 0)
        if 'custo_materiais' in anterior.keys() else 0.0,
        'valor_total': float(anterior['valor_total'] or 0),
        'forma_pagamento': anterior['forma_pagamento'] or '',
        'observacoes': anterior['observacoes'] or '',
        'texto_adicional': anterior['texto_adicional'] or ''
        if 'texto_adicional' in anterior.keys() else '',
        'tempo_horas': float(anterior['tempo_horas'] or 0)
        if 'tempo_horas' in anterior.keys() else 0.0,
    }
    depois = {
        'cliente_id': dados.cliente_id,
        'tecnico': dados.tecnico,
        'descricao': dados.descricao,
        'valor_mao_obra': dados.valor_mao_obra,
        'valor_materiais': dados.valor_materiais,
        'custo_materiais': dados.custo_materiais,
        'valor_total': dados.valor_total,
        'forma_pagamento': dados.forma_pagamento,
        'observacoes': dados.observacoes,
        'texto_adicional': dados.texto_adicional,
        'tempo_horas': dados.tempo_horas,
    }
    alteracoes = [f'{chave}: {antes[chave]!s} → {depois[chave]!s}'
                  for chave in antes if antes[chave] != depois[chave]]
    if alteracoes:
        ext.evento(cursor, os_id, 'Edição administrativa', '; '.join(alteracoes))
