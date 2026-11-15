"""Leituras de ordens de serviço usadas pelo portal e pelo painel GTK.

O SQL fica nesta camada de repositório; as interfaces continuam responsáveis
por formato, rótulos e ações. As consultas preservam filtros, ordens, limites
e colunas do código legado.
"""
from __future__ import annotations

from officina.core import prestadores_ext as ext
from officina.core.banco import BANCO


def _banco(banco=None):
    return banco or BANCO


def resumo(banco=None) -> dict[str, int]:
    """Contagens do painel inicial, ignorando OS arquivadas."""
    with ext.db(_banco(banco)) as conexao:
        linha = conexao.execute("""
            SELECT COUNT(*) total,
                   SUM(CASE WHEN status='Aberta' THEN 1 ELSE 0 END) abertas,
                   SUM(CASE WHEN status='Iniciada' THEN 1 ELSE 0 END) iniciadas,
                   SUM(CASE WHEN status='Pendente' THEN 1 ELSE 0 END) pendentes,
                   SUM(CASE WHEN status='Concluída' THEN 1 ELSE 0 END) concluidas
            FROM ordens_servico WHERE COALESCE(arquivada,0)=0
        """).fetchone()
    return {chave: int(linha[chave] or 0)
            for chave in ('total', 'abertas', 'iniciadas', 'pendentes', 'concluidas')}


def financeiro_resumo(banco=None) -> dict[str, float]:
    """Recebido e a receber para os cartões iniciais.

    ``a_receber`` é um alias histórico de ``pendente``; os dois consumidores
    usam nomes diferentes para o mesmo valor.
    """
    with ext.db(_banco(banco)) as conexao:
        linha = conexao.execute("""
            SELECT SUM(CASE WHEN status='Recebido' THEN valor ELSE 0 END) recebido,
                   SUM(CASE WHEN status='Aguardando pagamento' THEN valor ELSE 0 END) pendente
            FROM financeiro
        """).fetchone()
    recebido = float(linha['recebido'] or 0)
    pendente = float(linha['pendente'] or 0)
    return {'recebido': recebido, 'pendente': pendente, 'a_receber': pendente}


def recentes(banco=None, limite=6) -> list[dict]:
    """Últimas OS não arquivadas para a visão geral."""
    with ext.db(_banco(banco)) as conexao:
        linhas = conexao.execute("""
            SELECT o.id,o.numero_os,o.status,o.valor_total,o.data_abertura,
                   o.cliente_id,cl.nome cliente
            FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id
            WHERE COALESCE(o.arquivada,0)=0
            ORDER BY o.id DESC LIMIT ?
        """, (int(limite),)).fetchall()
    return [dict(linha) for linha in linhas]


def listar_historico(banco=None, limite=500) -> list[dict]:
    """OS encerradas com a última versão publicada do relatório."""
    with ext.db(_banco(banco)) as conexao:
        linhas = conexao.execute("""
            SELECT o.id,o.numero_os,o.status,o.descricao,o.data_abertura,
                   o.valor_total,cl.nome cliente,MAX(d.versao) versao
            FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id
            LEFT JOIN os_documentos d ON d.os_id=o.id AND d.tipo='relatorio_pdf'
            WHERE o.status NOT IN ('Aberta','Iniciada','Pendente')
              AND COALESCE(o.arquivada,0)=0
            GROUP BY o.id ORDER BY o.id DESC LIMIT ?
        """, (int(limite),)).fetchall()
    return [dict(linha) for linha in linhas]


def listar_relatorios(banco=None, limite=500) -> list[dict]:
    """OS não arquivadas para as telas de relatórios/e-mails/notas."""
    with ext.db(_banco(banco)) as conexao:
        linhas = conexao.execute("""
            SELECT o.id,o.numero_os,o.status,o.valor_total,o.data_abertura,
                   c.nome cliente
            FROM ordens_servico o JOIN clientes c ON c.id=o.cliente_id
            WHERE COALESCE(o.arquivada,0)=0 ORDER BY o.id DESC LIMIT ?
        """, (int(limite),)).fetchall()
    return [dict(linha) for linha in linhas]


def listar_origem_portal(banco=None, limite=100) -> list[dict]:
    """Solicitações criadas pelo Portal do Cliente."""
    with ext.db(_banco(banco)) as conexao:
        linhas = conexao.execute("""
            SELECT id,numero_os,status,data_abertura FROM ordens_servico
            WHERE origem='Portal' ORDER BY id DESC LIMIT ?
        """, (int(limite),)).fetchall()
    return [dict(linha) for linha in linhas]


def resumo_portal(banco=None) -> dict[str, int]:
    """Counts for the portal cards, preserving the previous SQL semantics."""
    with ext.db(_banco(banco)) as conexao:
        linha = conexao.execute("""
            SELECT COUNT(*) total,
                   COALESCE(SUM(status IN ('Aberta','Iniciada','Pendente')),0) andamento,
                   COALESCE(SUM(status='Concluída'),0) concluidas
            FROM ordens_servico WHERE origem='Portal'
        """).fetchone()
    return {chave: int(linha[chave] or 0)
            for chave in ('total', 'andamento', 'concluidas')}


def listar_solicitacoes_portal(banco=None, limite=50) -> list[dict]:
    """Portal rows with the client name, as shown in the desktop table."""
    with ext.db(_banco(banco)) as conexao:
        linhas = conexao.execute("""
            SELECT os.id,os.numero_os,c.nome cliente,os.data_abertura,
                   os.urgencia,os.status FROM ordens_servico os
            JOIN clientes c ON c.id=os.cliente_id
            WHERE os.origem='Portal' ORDER BY os.id DESC LIMIT ?
        """, (int(limite),)).fetchall()
    return [dict(linha) for linha in linhas]


def numero_os(banco, os_id) -> str:
    """Return the public number for an OS id, or an empty string."""
    try:
        with ext.db(_banco(banco)) as conexao:
            linha = conexao.execute(
                'SELECT numero_os FROM ordens_servico WHERE id=?',
                (int(os_id),)).fetchone()
    except (TypeError, ValueError):
        return ''
    return str(linha['numero_os'] or '') if linha else ''


def obter_por_token(banco, token) -> dict | None:
    """Resolve a public number, a legacy alias or a numeric id to an OS row.

    Public number wins over legacy alias, which wins over the internal id. That
    avoids a future custom numbering that happens to look like an old id.
    """
    texto = str(token or '').strip()
    if not texto:
        return None
    with ext.db(_banco(banco)) as conexao:
        linha = conexao.execute(
            'SELECT id,numero_os,status FROM ordens_servico WHERE numero_os=?',
            (texto,)).fetchone()
        if linha:
            return dict(linha)
        tabela = conexao.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='os_numero_alias'"
        ).fetchone()
        if tabela:
            linha = conexao.execute(
                '''SELECT o.id,o.numero_os,o.status
                   FROM os_numero_alias a JOIN ordens_servico o ON o.id=a.os_id
                   WHERE a.alias=?''', (texto,)).fetchone()
            if linha:
                return dict(linha)
        if texto.isdigit():
            linha = conexao.execute(
                'SELECT id,numero_os,status FROM ordens_servico WHERE id=?',
                (int(texto),)).fetchone()
            if linha:
                return dict(linha)
    return None


def url_os(banco, token, sufixo: str = '') -> str:
    """Canonical public URL for an OS number, alias or id."""
    from urllib.parse import quote
    registro = obter_por_token(banco, token)
    numero = str(registro['numero_os'] or '') if registro else str(token or '')
    return '/os/' + quote(numero, safe='') + (sufixo or '')

# Read aggregates must be scoped in SQL to avoid materializing other providers' data.
_INVOLVED = """(EXISTS (SELECT 1 FROM os_responsaveis r
                       WHERE r.os_id=o.id AND r.prestador_id=?)
                OR EXISTS (SELECT 1 FROM os_prestadores op
                       WHERE op.os_id=o.id AND op.prestador_id=? AND op.ativo=1))"""


def resumo_scoped(banco, provider_id):
    with ext.db(_banco(banco)) as connection:
        row = connection.execute(f"""SELECT COUNT(*) total,
             SUM(CASE WHEN status='Aberta' THEN 1 ELSE 0 END) abertas,
             SUM(CASE WHEN status='Iniciada' THEN 1 ELSE 0 END) iniciadas,
             SUM(CASE WHEN status='Pendente' THEN 1 ELSE 0 END) pendentes,
             SUM(CASE WHEN status='Concluída' THEN 1 ELSE 0 END) concluidas
             FROM ordens_servico o WHERE COALESCE(o.arquivada,0)=0
             AND {_INVOLVED}""", (provider_id, provider_id)).fetchone()
    return {k: int(row[k] or 0) for k in
            ('total','abertas','iniciadas','pendentes','concluidas')}


def financeiro_resumo_scoped(banco, provider_id):
    with ext.db(_banco(banco)) as connection:
        row = connection.execute(f"""SELECT
          SUM(CASE WHEN f.status='Recebido' THEN f.valor ELSE 0 END) recebido,
          SUM(CASE WHEN f.status='Aguardando pagamento' THEN f.valor ELSE 0 END) pendente
          FROM financeiro f JOIN ordens_servico o ON o.id=f.os_id
          WHERE {_INVOLVED}""", (provider_id,provider_id)).fetchone()
    recebido = float(row['recebido'] or 0)
    pendente = float(row['pendente'] or 0)
    return {'recebido':recebido,'pendente':pendente,'a_receber':pendente}


def recentes_scoped(banco, provider_id, limite=6):
    with ext.db(_banco(banco)) as connection:
        rows = connection.execute(f"""SELECT o.id,o.numero_os,o.status,o.valor_total,
          o.data_abertura,o.cliente_id,cl.nome cliente
          FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id
          WHERE COALESCE(o.arquivada,0)=0 AND {_INVOLVED}
          ORDER BY o.id DESC LIMIT ?""", (provider_id,provider_id,int(limite))).fetchall()
    return [dict(row) for row in rows]


def clientes_ativos_scoped(banco, provider_id):
    with ext.db(_banco(banco)) as connection:
        return int(connection.execute("""SELECT COUNT(*) FROM clientes cl
          WHERE cl.status NOT IN ('Inativo','A definir') AND EXISTS (
          SELECT 1 FROM ordens_servico o WHERE o.cliente_id=cl.id
          AND (EXISTS (SELECT 1 FROM os_responsaveis r WHERE r.os_id=o.id AND r.prestador_id=?)
          OR EXISTS (SELECT 1 FROM os_prestadores op WHERE op.os_id=o.id
                     AND op.prestador_id=? AND op.ativo=1)))""",
          (provider_id,provider_id)).fetchone()[0])


def listar_historico_scoped(banco, provider_id, limite=500):
    with ext.db(_banco(banco)) as connection:
        rows = connection.execute(f"""SELECT o.id,o.numero_os,o.status,o.descricao,
          o.data_abertura,o.valor_total,cl.nome cliente,MAX(d.versao) versao
          FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id
          LEFT JOIN os_documentos d ON d.os_id=o.id AND d.tipo='relatorio_pdf'
          WHERE o.status NOT IN ('Aberta','Iniciada','Pendente')
          AND COALESCE(o.arquivada,0)=0 AND {_INVOLVED}
          GROUP BY o.id ORDER BY o.id DESC LIMIT ?""",
          (provider_id,provider_id,int(limite))).fetchall()
    return [dict(row) for row in rows]
