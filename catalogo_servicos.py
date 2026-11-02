"""Catálogo de preços AUTOSEG. Orçamentos consultivos; sem integração com financeiro.

Somente o prestador pode inserir/alterar preços. Clientes autenticados podem
solicitar PDF a partir dos preços *ativos*; o servidor nunca aceita preço do formulário.
"""
from decimal import Decimal, InvalidOperation
from io import BytesIO
from xml.sax.saxutils import escape
from datetime import datetime
import json
import prestadores_ext as ext


def instalar(banco):
    with ext.db(banco) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS catalogo_servicos (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          nome TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '',
          preco_servico_centavos INTEGER NOT NULL DEFAULT 0,
          materiais_json TEXT NOT NULL DEFAULT '[]',
          relatorio_padrao TEXT NOT NULL DEFAULT '',
          ativo INTEGER NOT NULL DEFAULT 1,
          criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL
        )''')


def _centavos(valor, nome='Valor'):
    t=str(valor if valor is not None else '').strip().replace('R$','').replace(' ','')
    if ',' in t:t=t.replace('.','').replace(',','.')
    try:
        d=Decimal(t or '0').quantize(Decimal('0.01'))
        if not d.is_finite() or d<0 or d>Decimal('1000000'):
            raise ValueError(f'{nome} fora do intervalo permitido.')
        return int(d*100)
    except (InvalidOperation,ValueError) as exc:
        if isinstance(exc,ValueError):raise
        raise ValueError(f'{nome} inválido.') from exc


def reais(centavos):
    d=Decimal(int(centavos))/100
    return 'R$ '+f'{d:,.2f}'.replace(',','@').replace('.',',').replace('@','.')


def normalizar_materiais(texto):
    """Uma linha por material: nome | quantidade | valor unitário."""
    linhas=[x.strip() for x in str(texto or '').splitlines() if x.strip()]
    if len(linhas)>30:raise ValueError('Máximo de 30 materiais por serviço.')
    saida=[]
    for linha in linhas:
        partes=[p.strip() for p in linha.split('|')]
        if len(partes)!=3:raise ValueError('Material deve ter: Nome | Quantidade | Valor unitário.')
        nome,qtd,preco=partes
        if not 1<=len(nome)<=160:raise ValueError('Nome do material inválido.')
        try:quantidade=Decimal(qtd.replace(',','.'))
        except InvalidOperation:raise ValueError('Quantidade do material inválida.')
        if not quantidade.is_finite() or quantidade<=0 or quantidade>1000:raise ValueError('Quantidade fora do intervalo.')
        saida.append({'nome':nome,'quantidade':str(quantidade),'preco_centavos':_centavos(preco,'Material')})
    return saida


def materiais_do_formulario(d):
    """Valida linhas visuais: não exige separadores especiais do usuário."""
    nomes=d.get('material_nome[]',[])
    qtds=d.get('material_qtd[]',[])
    precos=d.get('material_valor[]',[])
    if isinstance(nomes,str):nomes=[nomes]
    if isinstance(qtds,str):qtds=[qtds]
    if isinstance(precos,str):precos=[precos]
    if len(nomes)>30 or len(nomes)!=len(qtds) or len(nomes)!=len(precos):
        raise ValueError('Materiais incompletos ou acima do limite de 30 itens.')
    linhas=[]
    for nome,qtd,preco in zip(nomes,qtds,precos):
        if not any(str(x).strip() for x in (nome,qtd,preco)):continue
        if '|' in str(nome):raise ValueError('O nome do material não pode conter o caractere |.')
        if not str(nome).strip() or not str(qtd).strip() or not str(preco).strip():
            raise ValueError('Preencha nome, quantidade e valor de cada material, ou remova a linha.')
        linhas.append(f'{nome} | {qtd} | {preco}')
    return normalizar_materiais('\n'.join(linhas))


def _materiais_entrada(d):
    if 'material_nome[]' in d or 'material_qtd[]' in d or 'material_valor[]' in d:
        return materiais_do_formulario(d)
    return normalizar_materiais(d.get('materiais',''))


def salvar(banco,d,identificador=None):
    nome=str(d.get('nome','')).strip()
    desc=str(d.get('descricao','')).strip()
    relatorio=str(d.get('relatorio_padrao','')).strip()
    if not 3<=len(nome)<=140:raise ValueError('Informe o nome do serviço (3–140 caracteres).')
    if len(desc)>1500 or len(relatorio)>5000:raise ValueError('Descrição ou relatório muito longo.')
    materiais=_materiais_entrada(d)
    preco=_centavos(d.get('preco_servico','0'),'Preço do serviço')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        # REV08: materiais de serviços entram no catálogo central, nunca no saldo.
        from estoque_materiais import instalar_conexao, _chave
        instalar_conexao(c)
        for material in materiais:
            material_nome = material['nome'].strip()
            chave_material = _chave(material_nome)
            if not c.execute('SELECT 1 FROM estoque_produtos WHERE chave=?',
                             (chave_material,)).fetchone():
                c.execute('''INSERT INTO estoque_produtos
                    (nome,chave,unidade,venda_centavos,criado_em,atualizado_em)
                    VALUES (?,?,?,?,?,?)''',
                    (material_nome,chave_material,'un',int(material['preco_centavos']),
                     ext.agora(),ext.agora()))
        if identificador is None:
            return c.execute('''INSERT INTO catalogo_servicos
              (nome,descricao,preco_servico_centavos,materiais_json,relatorio_padrao,criado_em,atualizado_em)
              VALUES(?,?,?,?,?,?,?)''',
              (nome,desc,preco,json.dumps(materiais,ensure_ascii=False),relatorio,ext.agora(),ext.agora())).lastrowid
        if not c.execute('SELECT 1 FROM catalogo_servicos WHERE id=?',(identificador,)).fetchone():
            raise ValueError('Serviço não encontrado.')
        c.execute('''UPDATE catalogo_servicos SET nome=?,descricao=?,preco_servico_centavos=?,
          materiais_json=?,relatorio_padrao=?,atualizado_em=? WHERE id=?''',
          (nome,desc,preco,json.dumps(materiais,ensure_ascii=False),relatorio,ext.agora(),identificador))
        return identificador


def listar(banco,ativos=False):
    with ext.db(banco) as c:
        return [dict(x) for x in c.execute('SELECT * FROM catalogo_servicos '+('WHERE ativo=1 ' if ativos else '')+'ORDER BY nome LIMIT 500')]


def obter(banco,identificador,ativos=False):
    with ext.db(banco) as c:
        row=c.execute('SELECT * FROM catalogo_servicos WHERE id=?'+(' AND ativo=1' if ativos else ''),(identificador,)).fetchone()
        return dict(row) if row else None


def reativar(banco,identificador):
    with ext.db(banco) as c:
        if not c.execute('UPDATE catalogo_servicos SET ativo=1,atualizado_em=? WHERE id=?',(ext.agora(),identificador)).rowcount:
            raise ValueError('Serviço não encontrado.')


def arquivar(banco,identificador):
    with ext.db(banco) as c:
        if not c.execute('UPDATE catalogo_servicos SET ativo=0,atualizado_em=? WHERE id=?',(ext.agora(),identificador)).rowcount:
            raise ValueError('Serviço não encontrado.')


def valores_orcamento(banco,identificador,quantidade=1):
    try:quantidade=int(quantidade)
    except (ValueError,TypeError):raise ValueError('Quantidade inválida.')
    if not 1<=quantidade<=20:raise ValueError('Quantidade deve estar entre 1 e 20.')
    servico=obter(banco,identificador,ativos=True)
    if not servico:raise ValueError('Serviço indisponível.')
    materiais=json.loads(servico['materiais_json'])
    materiais_total=sum(int(Decimal(m['quantidade'])*m['preco_centavos']) for m in materiais)
    return {'servico':servico,'quantidade':quantidade,'materiais':materiais,
            'subtotal_servico':quantidade*servico['preco_servico_centavos'],
            'subtotal_materiais':quantidade*materiais_total,
            'total':quantidade*(servico['preco_servico_centavos']+materiais_total)}


def pdf_orcamento(banco,identificador,quantidade=1,cliente='Cliente'):
    """Gera orçamento não vinculante e sem dados financeiros confidenciais."""
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
    from reportlab.lib.pagesizes import A4
    dados=valores_orcamento(banco,identificador,quantidade)
    servico=dados['servico']
    nome_cliente=str(cliente or 'Cliente')[:120]
    bio=BytesIO()
    doc=SimpleDocTemplate(bio,pagesize=A4,leftMargin=45,rightMargin=45,topMargin=48,bottomMargin=48)
    styles=getSampleStyleSheet()
    normal=styles['BodyText']
    def par(s):return Paragraph(escape(str(s)),normal)
    content=[Paragraph('AUTOSEG — Orçamento estimativo',styles['Title']),Spacer(1,14),
             par('Emitido em: '+datetime.now().strftime('%d/%m/%Y %H:%M')),
             par('Solicitante: '+nome_cliente),Spacer(1,12),
             Paragraph(escape(servico['nome']),styles['Heading2']),par(servico['descricao'] or 'Serviço conforme catálogo'),Spacer(1,12)]
    linhas=[[par('Item'),par('Qtde.'),par('Total')],
            [par('Mão de obra: '+servico['nome']),str(dados['quantidade']),reais(dados['subtotal_servico'])]]
    for m in dados['materiais']:
        linhas.append([par('Material: '+m['nome']),par(str(m['quantidade'])+' × '+str(dados['quantidade'])),
                       reais(int(Decimal(m['quantidade'])*m['preco_centavos'])*dados['quantidade'])])
    linhas.append([par('TOTAL ESTIMADO'),' ',reais(dados['total'])])
    tabela=Table(linhas,colWidths=[330,70,100],repeatRows=1,hAlign='LEFT')
    tabela.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eee8c9')),
                                ('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.35,colors.grey),
                                ('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    content.extend([tabela,Spacer(1,18),par('Estimativa automática, não é nota fiscal nem proposta contratual. Valores sujeitos a vistoria, disponibilidade e confirmação do prestador.')])
    doc.build(content)
    return bio.getvalue()
