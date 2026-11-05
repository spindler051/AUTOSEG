"""Company cash ledger for investor contributions and operating expenses.

This module is intentionally separate from OS revenue, stock and rateios.
A material purchase may reference an OS for context, but it never changes the
OS cost, the stock balance or the customer-facing financial record.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import prestadores_ext as ext

TIPOS = {
    'aporte': 'Aporte de investidor',
    'material': 'Compra de material',
    'api': 'Despesa com API',
    'despesa': 'Outra despesa',
}
TIPOS_DESPESA = ('material', 'api', 'despesa')
CATEGORIAS_PADRAO = {
    'aporte': 'Capital',
    'material': 'Material',
    'api': 'API DeepSeek',
    'despesa': 'Geral',
}


def instalar(banco):
    """Create the additive company ledger table; safe to run repeatedly."""
    with ext.db(banco) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS empresa_movimentos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL CHECK(tipo IN ('aporte','material','api','despesa')),
            data TEXT NOT NULL,
            descricao TEXT NOT NULL,
            categoria TEXT NOT NULL DEFAULT '',
            valor_centavos INTEGER NOT NULL CHECK(valor_centavos > 0),
            prestador_id INTEGER,
            os_id INTEGER,
            observacao TEXT NOT NULL DEFAULT '',
            ativo INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL,
            criado_por TEXT NOT NULL DEFAULT 'Desktop',
            arquivado_em TEXT,
            arquivado_por TEXT,
            FOREIGN KEY(prestador_id) REFERENCES prestadores(id),
            FOREIGN KEY(os_id) REFERENCES ordens_servico(id)
        );
        CREATE INDEX IF NOT EXISTS idx_empresa_mov_data
            ON empresa_movimentos(ativo,data,id);
        CREATE INDEX IF NOT EXISTS idx_empresa_mov_prestador
            ON empresa_movimentos(prestador_id,id);
        CREATE INDEX IF NOT EXISTS idx_empresa_mov_os
            ON empresa_movimentos(os_id,id);
        """)


def _centavos(valor):
    texto = str(valor if valor is not None else '').strip()
    texto = texto.replace('R$', '').replace(' ', '')
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    try:
        montante = Decimal(texto or '0')
        if (not montante.is_finite() or montante <= 0
                or montante > Decimal('10000000')):
            raise ValueError('Valor deve ser maior que zero e menor que R$ 10.000.000,00.')
        return int((montante * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except InvalidOperation as erro:
        raise ValueError('Valor inválido.') from erro


def _data_iso(data):
    texto = str(data or '').strip()
    if not texto:
        return datetime.now().strftime('%Y-%m-%d')
    for formato in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(texto, formato).strftime('%Y-%m-%d')
        except ValueError:
            continue
    raise ValueError('Data inválida. Use dd/mm/aaaa.')


def _inteiro_ou_nulo(valor):
    if valor is None or str(valor).strip() == '':
        return None
    try:
        return int(valor)
    except (TypeError, ValueError) as erro:
        raise ValueError('Identificador inválido.') from erro


def registrar(banco, tipo, descricao, valor, data='', prestador_id=None,
              os_id=None, categoria='', observacao='', criado_por='Desktop'):
    """Register one confirmed cash movement.

    ``aporte`` needs an active investor. ``material`` may point to an OS only
    as a reference; nothing else in the OS, stock or finance is changed.
    """
    tipo = str(tipo or '').strip()
    if tipo not in TIPOS:
        raise ValueError('Tipo de lançamento inválido.')
    descricao = str(descricao or '').strip()
    if not 2 <= len(descricao) <= 200:
        raise ValueError('A descrição deve ter entre 2 e 200 caracteres.')
    valor_centavos = _centavos(valor)
    data_iso = _data_iso(data)
    prestador_id = _inteiro_ou_nulo(prestador_id)
    os_id = _inteiro_ou_nulo(os_id)
    categoria = str(categoria or '').strip()[:80] or CATEGORIAS_PADRAO[tipo]
    observacao = str(observacao or '').strip()[:1000]
    criado_por = str(criado_por or 'Desktop').strip()[:120] or 'Desktop'

    with ext.db(banco) as c:
        if tipo == 'aporte' and prestador_id is None:
            raise ValueError('Selecione o investidor do aporte.')
        if prestador_id is not None:
            pessoa = c.execute(
                'SELECT 1 FROM prestadores WHERE id=? AND ativo=1 AND excluido=0',
                (prestador_id,)).fetchone()
            if not pessoa:
                raise ValueError('Investidor não encontrado ou inativo.')
        if os_id is not None:
            if tipo != 'material':
                raise ValueError('Vincular OS é permitido apenas em compra de material.')
            if not c.execute('SELECT 1 FROM ordens_servico WHERE id=?', (os_id,)).fetchone():
                raise ValueError('OS vinculada não encontrada.')
        return c.execute(
            'INSERT INTO empresa_movimentos'
            '(tipo,data,descricao,categoria,valor_centavos,prestador_id,os_id,'
            'observacao,ativo,criado_em,criado_por) '
            'VALUES(?,?,?,?,?,?,?,?,1,?,?)',
            (tipo, data_iso, descricao, categoria, valor_centavos,
             prestador_id, os_id, observacao, ext.agora(), criado_por)).lastrowid


def listar(banco, incluir_arquivados=False):
    with ext.db(banco) as c:
        filtro = '' if incluir_arquivados else 'WHERE m.ativo=1'
        return [dict(r) for r in c.execute(
            f'''SELECT m.*,p.nome prestador_nome,o.numero_os
                FROM empresa_movimentos m
                LEFT JOIN prestadores p ON p.id=m.prestador_id
                LEFT JOIN ordens_servico o ON o.id=m.os_id
                {filtro}
                ORDER BY m.data DESC,m.id DESC''')]


def resumo(banco):
    """Return totals in cents; OS revenue is deliberately not included."""
    with ext.db(banco) as c:
        totais = {
            linha['tipo']: int(linha['total'] or 0)
            for linha in c.execute(
                'SELECT tipo,SUM(valor_centavos) total FROM empresa_movimentos '
                'WHERE ativo=1 GROUP BY tipo')
        }
        investidores = [dict(r) for r in c.execute(
            '''SELECT m.prestador_id,p.nome,SUM(m.valor_centavos) total_centavos
               FROM empresa_movimentos m
               JOIN prestadores p ON p.id=m.prestador_id
               WHERE m.ativo=1 AND m.tipo='aporte'
               GROUP BY m.prestador_id,p.nome
               ORDER BY p.nome''')]
        categorias = [dict(r) for r in c.execute(
            '''SELECT tipo,categoria,SUM(valor_centavos) total_centavos
               FROM empresa_movimentos
               WHERE ativo=1 AND tipo IN ('material','api','despesa')
               GROUP BY tipo,categoria
               ORDER BY tipo,categoria''')]
    aportes = totais.get('aporte', 0)
    despesas = sum(totais.get(tipo, 0) for tipo in TIPOS_DESPESA)
    return {
        'aportes_centavos': aportes,
        'material_centavos': totais.get('material', 0),
        'api_centavos': totais.get('api', 0),
        'outras_despesas_centavos': totais.get('despesa', 0),
        'despesas_centavos': despesas,
        'saldo_centavos': aportes - despesas,
        'por_investidor': investidores,
        'por_categoria': categorias,
    }


def arquivar(banco, movimento_id, ator='Desktop'):
    """Archive a movement without deleting its history."""
    with ext.db(banco) as c:
        linha = c.execute(
            'SELECT ativo FROM empresa_movimentos WHERE id=?',
            (int(movimento_id),)).fetchone()
        if not linha:
            raise ValueError('Lançamento não encontrado.')
        if not linha['ativo']:
            return False
        c.execute(
            'UPDATE empresa_movimentos SET ativo=0,arquivado_em=?,arquivado_por=? '
            'WHERE id=?',
            (ext.agora(), str(ator or 'Desktop')[:120], int(movimento_id)))
        return True
