"""Read-only desktop context queries kept out of the GTK dialogs.

These payloads are intentionally table-shaped because the legacy dialogs still
consume rows by name. The next migration can replace them with typed DTOs when
the dialog itself is rebuilt.
"""
from __future__ import annotations

import sqlite3

import prestadores_ext as ext


def contexto_os(banco, os_id=None) -> dict:
    resultado = {
        'clientes': [],
        'dados': None,
        'materiais': [],
        'original_portal': None,
        'andamento': None,
        'encerramento': None,
    }
    with ext.db(banco) as conexao:
        resultado['clientes'] = [dict(linha) for linha in conexao.execute(
            "SELECT id,nome FROM clientes WHERE status!='Inativo' ORDER BY nome")]
        if os_id is None:
            return resultado
        registro = conexao.execute(
            'SELECT * FROM ordens_servico WHERE id=?', (os_id,)).fetchone()
        if registro is None:
            raise ValueError('OS não encontrada.')
        resultado['dados'] = dict(registro)
        resultado['materiais'] = [dict(linha) for linha in conexao.execute(
            'SELECT item,quantidade,unidade,valor_unitario,valor_total FROM materiais_os '
            'WHERE os_id=? ORDER BY id', (os_id,))]
        if resultado['dados'].get('origem') == 'Portal':
            original = conexao.execute(
                'SELECT descricao_original FROM os_solicitacoes WHERE os_id=?',
                (os_id,)).fetchone()
            resultado['original_portal'] = (
                original['descricao_original'] if original else None)
        andamento = conexao.execute(
            'SELECT iniciado_em,rascunho FROM os_atendimentos WHERE os_id=?',
            (os_id,)).fetchone()
        resultado['andamento'] = dict(andamento) if andamento else None
        encerramento = conexao.execute(
            'SELECT motivo,relatorio FROM os_encerramentos WHERE os_id=?',
            (os_id,)).fetchone()
        resultado['encerramento'] = dict(encerramento) if encerramento else None
    return resultado


def contar_anexos_os(banco, os_id) -> int:
    try:
        with ext.db(banco) as conexao:
            return int(conexao.execute(
                'SELECT COUNT(*) FROM os_anexos WHERE os_id=?',
                (os_id,)).fetchone()[0])
    except sqlite3.Error:
        return 0


def contexto_atribuicao(banco, os_id) -> dict:
    with ext.db(banco) as conexao:
        ordem = conexao.execute(
            'SELECT numero_os,status FROM ordens_servico WHERE id=?',
            (os_id,)).fetchone()
        prestadores = [dict(linha) for linha in conexao.execute(
            'SELECT id,nome,email FROM prestadores '
            'WHERE ativo=1 AND excluido=0 ORDER BY nome')]
        atual_id = ext.responsavel_atual(conexao, os_id)
    return {
        'ordem': dict(ordem) if ordem else None,
        'prestadores': prestadores,
        'atual_id': atual_id,
    }


def documento_prestador(banco, prestador_id) -> str:
    with ext.db(banco) as conexao:
        linha = conexao.execute(
            'SELECT documento FROM prestadores WHERE id=?',
            (prestador_id,)).fetchone()
    return str(linha['documento'] or '') if linha else ''


def contexto_responsavel(banco) -> dict:
    with ext.db(banco) as conexao:
        organizacoes = [dict(linha) for linha in conexao.execute(
            """SELECT o.id,o.nome,o.tipo,o.cnpj,r.usuario_id,u.nome responsavel
               FROM v9_organizacoes o
               LEFT JOIN v9_responsaveis r ON r.organizacao_id=o.id
               LEFT JOIN v9_usuarios u ON u.id=r.usuario_id
               WHERE o.mesclado_em IS NULL ORDER BY o.nome""").fetchall()]
        pessoas = [dict(linha) for linha in conexao.execute(
            'SELECT id,nome,cpf FROM v9_usuarios WHERE ativo=1 ORDER BY nome')]
    return {'organizacoes': organizacoes, 'pessoas': pessoas}


def contexto_os_rapida(banco) -> dict:
    with ext.db(banco) as conexao:
        clientes = [dict(linha) for linha in conexao.execute(
            "SELECT id,nome,tipo_pessoa FROM clientes "
            "WHERE status!='Inativo' ORDER BY nome")]
        prestadores = [dict(linha) for linha in conexao.execute(
            'SELECT id,nome FROM prestadores WHERE ativo=1 ORDER BY nome')]
    return {'clientes': clientes, 'prestadores': prestadores}


def contexto_movimento_empresa(banco) -> dict:
    with ext.db(banco) as conexao:
        prestadores = [dict(linha) for linha in conexao.execute(
            'SELECT id,nome FROM prestadores '
            'WHERE ativo=1 AND excluido=0 ORDER BY nome')]
        oses = [dict(linha) for linha in conexao.execute(
            'SELECT o.id,o.numero_os,c.nome cliente '
            'FROM ordens_servico o LEFT JOIN clientes c ON c.id=o.cliente_id '
            'ORDER BY o.id DESC LIMIT 300')]
    return {'prestadores': prestadores, 'oses': oses}
