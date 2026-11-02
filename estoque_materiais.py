"""Inventário AUTOSEG: edição somente pelo desktop; OS registram consumos transacionais.

Nenhuma rota HTTP de administração do estoque. Saldos negativos são permitidos.
A tabela de aplicações por OS impede baixa dupla em edições/reaberturas.
"""
import re
import unicodedata
from decimal import Decimal, InvalidOperation
import prestadores_ext as ext


def _chave(nome):
    v=unicodedata.normalize('NFKD',str(nome).strip().casefold())
    return re.sub(r'\s+',' ', ''.join(c for c in v if not unicodedata.combining(c)))


def _q(valor,permitir_negativo=False):
    try:
        v=Decimal(str(valor).strip().replace(',','.'))
        if not v.is_finite() or abs(v)>Decimal('1000000') or (v<=0 and not permitir_negativo):
            raise ValueError('Quantidade fora dos limites permitidos.')
        return v.quantize(Decimal('0.0001'))
    except (InvalidOperation,TypeError) as e:
        raise ValueError('Quantidade inválida.') from e


def instalar_conexao(c):
    c.execute('''CREATE TABLE IF NOT EXISTS estoque_produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
        chave TEXT NOT NULL UNIQUE, sku TEXT NOT NULL DEFAULT '',
        unidade TEXT NOT NULL DEFAULT 'un', custo_centavos INTEGER NOT NULL DEFAULT 0,
        venda_centavos INTEGER NOT NULL DEFAULT 0, saldo REAL NOT NULL DEFAULT 0,
        minimo REAL NOT NULL DEFAULT 0, ativo INTEGER NOT NULL DEFAULT 1,
        criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS estoque_movimentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, produto_id INTEGER NOT NULL,
        os_id INTEGER, tipo TEXT NOT NULL, delta REAL NOT NULL,
        motivo TEXT NOT NULL, ator TEXT NOT NULL, criado_em TEXT NOT NULL,
        FOREIGN KEY(produto_id) REFERENCES estoque_produtos(id))''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_est_mov_prod ON estoque_movimentos(produto_id,id)''')
    c.execute('''CREATE TABLE IF NOT EXISTS estoque_os_aplicacoes (
        os_id INTEGER NOT NULL, produto_id INTEGER NOT NULL, quantidade REAL NOT NULL,
        PRIMARY KEY(os_id,produto_id), FOREIGN KEY(produto_id) REFERENCES estoque_produtos(id))''')


def instalar(banco):
    """Cria estrutura e registra estoques antigos como referência, SEM baixa retroativa.

    Uma migração única guarda os consumos existentes como linha base. Depois disso,
    só as diferenças de novas edições passam a movimentar estoque.
    """
    with ext.db(banco) as c:
        instalar_conexao(c)
        c.execute("""CREATE TABLE IF NOT EXISTS estoque_migracao (
            nome TEXT PRIMARY KEY, aplicado_em TEXT NOT NULL)""")
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM estoque_migracao WHERE nome='rev04_base'").fetchone():return
        existe=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='materiais_os'").fetchone()
        if existe:
            linhas=c.execute("""SELECT m.os_id,m.item,m.quantidade,m.valor_unitario
                FROM materiais_os m JOIN ordens_servico o ON o.id=m.os_id
                WHERE 1=1 ORDER BY m.os_id,m.id""").fetchall()
            agrupado={}
            for m in linhas:
                nome=str(m['item'] or '').strip()
                if not nome:continue
                key=(int(m['os_id']),_chave(nome))
                if key not in agrupado:agrupado[key]=[nome,Decimal(0),m['valor_unitario']]
                agrupado[key][1]+=_q(m['quantidade'])
            for (os_id,chave),(nome,qtd,venda) in agrupado.items():
                r=c.execute('SELECT id FROM estoque_produtos WHERE chave=?',(chave,)).fetchone()
                if r:pid=r['id']
                else:
                    pid=c.execute("""INSERT INTO estoque_produtos
                        (nome,chave,unidade,venda_centavos,criado_em,atualizado_em)
                        VALUES(?,?,?,?,?,?)""",(nome,chave,'un',_valor_centavos(venda or 0),ext.agora(),ext.agora())).lastrowid
                c.execute("""INSERT OR IGNORE INTO estoque_os_aplicacoes(os_id,produto_id,quantidade)
                    VALUES(?,?,?)""",(os_id,pid,float(qtd)))
        c.execute("INSERT INTO estoque_migracao(nome,aplicado_em) VALUES('rev04_base',?)",(ext.agora(),))


def listar(banco,ativos=False):
    with ext.db(banco) as c:
        instalar_conexao(c)
        return [dict(r) for r in c.execute('SELECT * FROM estoque_produtos '+('WHERE ativo=1 ' if ativos else '')+'ORDER BY nome,id')]


def movimentos(banco,produto_id=None,limite=200):
    with ext.db(banco) as c:
        instalar_conexao(c)
        sql='''SELECT m.*,p.nome FROM estoque_movimentos m JOIN estoque_produtos p ON p.id=m.produto_id'''
        if produto_id is not None:
            sql+=' WHERE m.produto_id=? ORDER BY m.id DESC LIMIT ?'
            rows=c.execute(sql,(int(produto_id),int(limite)))
        else:
            rows=c.execute(sql+' ORDER BY m.id DESC LIMIT ?',(int(limite),))
        return [dict(r) for r in rows]


def _valor_centavos(valor):
    from catalogo_servicos import _centavos
    return _centavos(valor)


def cadastrar(banco,nome,sku='',unidade='un',custo='0',venda='0',minimo='0',identificador=None):
    nome=str(nome).strip()
    if not 2<=len(nome)<=160:raise ValueError('Nome do material deve ter entre 2 e 160 caracteres.')
    if len(str(sku))>50 or len(str(unidade))>15:raise ValueError('SKU ou unidade muito longos.')
    minimo_val=_q(minimo,True)
    if minimo_val<0:raise ValueError('Estoque mínimo não pode ser negativo.')
    campos=(nome,_chave(nome),str(sku).strip(),str(unidade).strip() or 'un',_valor_centavos(custo),_valor_centavos(venda),float(minimo_val),ext.agora())
    with ext.db(banco) as c:
        instalar_conexao(c)
        c.execute('BEGIN IMMEDIATE')
        if identificador is None:
            if c.execute('SELECT 1 FROM estoque_produtos WHERE chave=?',(campos[1],)).fetchone():
                raise ValueError('Material já cadastrado. Edite o cadastro existente.')
            return c.execute('''INSERT INTO estoque_produtos(nome,chave,sku,unidade,custo_centavos,venda_centavos,minimo,criado_em,atualizado_em)
                VALUES(?,?,?,?,?,?,?,?,?)''',campos+(ext.agora(),)).lastrowid
        identificador=int(identificador)
        if not c.execute('SELECT 1 FROM estoque_produtos WHERE id=?',(identificador,)).fetchone():raise ValueError('Produto não encontrado.')
        c.execute('''UPDATE estoque_produtos SET nome=?,chave=?,sku=?,unidade=?,custo_centavos=?,venda_centavos=?,minimo=?,atualizado_em=? WHERE id=?''',campos+(identificador,))
        return identificador


def _movimentar(c,pid,delta,tipo,motivo,ator,os_id=None):
    delta=_q(delta,True)
    if not delta:return
    c.execute('UPDATE estoque_produtos SET saldo=ROUND(saldo+?,4),atualizado_em=? WHERE id=?',(float(delta),ext.agora(),pid))
    c.execute('''INSERT INTO estoque_movimentos(produto_id,os_id,tipo,delta,motivo,ator,criado_em)
                 VALUES(?,?,?,?,?,?,?)''',(pid,os_id,tipo,float(delta),str(motivo)[:300],str(ator)[:120],ext.agora()))


def ajuste(banco,produto_id,delta,motivo,ator='Desktop'):
    if not str(motivo).strip():raise ValueError('Informe o motivo da movimentação.')
    with ext.db(banco) as c:
        instalar_conexao(c);c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM estoque_produtos WHERE id=?',(produto_id,)).fetchone():raise ValueError('Produto não encontrado.')
        _movimentar(c,int(produto_id),delta,'Ajuste manual',motivo,ator)


def reconciliar_os_conexao(c,os_id,ator='OS'):
    """Synchroniza materiais detalhados e estoque na MESMA transação que salvou a OS.

    Dados históricos antes da implantação não devem ser baixados retroativamente:
    marcar_aplicacoes_legadas() pode estabelecer referência sem desconto.
    """
    instalar_conexao(c)
    os_=c.execute('SELECT status FROM ordens_servico WHERE id=?',(int(os_id),)).fetchone()
    if os_ is None:raise ValueError('OS inexistente para movimentar estoque.')
    desejado={}
    # O cancelamento da OS NÃO implica devolução de materiais consumidos.
    # Somente uma edição explícita dos materiais/estorno pode ajustar o estoque.
    for item in c.execute('SELECT item,quantidade,valor_unitario FROM materiais_os WHERE os_id=?',(os_id,)).fetchall():
        nome=str(item['item'] or '').strip()
        if not nome:continue
        qtd=_q(item['quantidade'])
        chave=_chave(nome)
        if chave not in desejado:desejado[chave]=[nome,Decimal('0'),item['valor_unitario']]
        desejado[chave][1]+=qtd
    anterior={int(r['produto_id']):_q(r['quantidade'],True) for r in c.execute('SELECT produto_id,quantidade FROM estoque_os_aplicacoes WHERE os_id=?',(os_id,))}
    novo={}
    for chave,(nome,qtd,valor) in desejado.items():
        registro=c.execute('SELECT id FROM estoque_produtos WHERE chave=?',(chave,)).fetchone()
        if registro:pid=int(registro['id'])
        else:
            valor_centavos=_valor_centavos(valor or 0)
            pid=c.execute('''INSERT INTO estoque_produtos(nome,chave,unidade,venda_centavos,criado_em,atualizado_em)
                VALUES(?,?,?,?,?,?)''',(nome,chave,'un',valor_centavos,ext.agora(),ext.agora())).lastrowid
        novo[pid]=qtd
    for pid in set(anterior)|set(novo):
        delta=novo.get(pid,Decimal(0))-anterior.get(pid,Decimal(0))
        if delta:
            _movimentar(c,pid,-delta,'Consumo OS' if delta>0 else 'Estorno OS',f'OS #{os_id}',ator,os_id)
        if pid in novo:
            c.execute('''INSERT INTO estoque_os_aplicacoes(os_id,produto_id,quantidade)
                VALUES(?,?,?) ON CONFLICT(os_id,produto_id) DO UPDATE SET quantidade=excluded.quantidade''',(os_id,pid,float(novo[pid])))
        else:c.execute('DELETE FROM estoque_os_aplicacoes WHERE os_id=? AND produto_id=?',(os_id,pid))


def registrar_legado_sem_baixa(banco):
    """Uso manual antes da REV04: nunca executar como migração automática sem aprovação."""
    raise RuntimeError('Não é permitida importação retroativa automática de saldos.')


# REV08: lote transacional, sem inserções parciais e sem movimentar estoque.
def importar_lote(banco, materiais):
    '''Valida todos os materiais e cadastra em uma única transação com rollback.'''
    if not isinstance(materiais, list) or not 1 <= len(materiais) <= 100:
        raise ValueError('Informe de 1 a 100 materiais para importar.')
    preparados = []
    encontrados = set()
    for m in materiais:
        if not isinstance(m, dict):
            raise ValueError('Cada material deve ser um registro com campos válidos.')
        nome = str(m.get('nome', '')).strip()
        chave = _chave(nome)
        if not 2 <= len(nome) <= 160 or chave in encontrados:
            raise ValueError('Material duplicado ou nome inválido: ' + nome[:60])
        encontrados.add(chave)
        sku = str(m.get('sku', '')).strip()
        unidade = str(m.get('unidade', 'un')).strip() or 'un'
        if len(sku) > 50 or len(unidade) > 15:
            raise ValueError('Código ou unidade muito longos.')
        minimo = _q(m.get('minimo', '0'), True)
        if minimo < 0:
            raise ValueError('Estoque mínimo não pode ser negativo.')
        custo = _valor_centavos(m.get('custo', '0'))
        venda = _valor_centavos(m.get('venda', '0'))
        preparados.append((nome, chave, sku, unidade, custo, venda, float(minimo)))
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        instalar_conexao(c)
        existentes = c.execute(
            'SELECT nome FROM estoque_produtos WHERE chave IN (' +
            ','.join('?' * len(preparados)) + ')',
            [x[1] for x in preparados]).fetchall()
        if existentes:
            raise ValueError('Já existe material no catálogo: ' +
                             ', '.join(r['nome'] for r in existentes[:10]))
        agora = ext.agora()
        ids = []
        for nome, chave, sku, unidade, custo, venda, minimo in preparados:
            cur = c.execute('''INSERT INTO estoque_produtos
                (nome,chave,sku,unidade,custo_centavos,venda_centavos,
                 minimo,criado_em,atualizado_em)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (nome,chave,sku,unidade,custo,venda,minimo,agora,agora))
            ids.append(cur.lastrowid)
        return ids


def sugerir(banco, termo, limite=15):
    '''Busca tolerante a acentos, espaços e maiúsculas (somente ativos).'''
    chave = _chave(termo)
    limite = min(max(int(limite), 1), 50)
    if not chave:
        return []
    itens = listar(banco, ativos=True)
    itens = [x for x in itens if chave in x['chave'] or chave in _chave(x['sku'])]
    return sorted(itens, key=lambda x: (not x['chave'].startswith(chave), x['chave'], x['id']))[:limite]
