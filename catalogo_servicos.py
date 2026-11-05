"""Catálogo de preços AUTOSEG. Orçamentos consultivos; sem integração com financeiro.

Somente o prestador pode inserir/alterar preços. Clientes autenticados podem
solicitar PDF a partir dos preços *ativos*; o servidor nunca aceita preço do formulário.
"""
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO
from xml.sax.saxutils import escape
from datetime import datetime
import json
import prestadores_ext as ext
import composicao
import pdf_identidade as marca


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
    try:
        tempo_horas=float(str(d.get('tempo_horas','0') or '0').replace(',','.'))
    except ValueError:
        raise ValueError('Tempo estimado inválido.') from None
    if tempo_horas<0:raise ValueError('Tempo estimado não pode ser negativo.')
    total_materiais=sum(int(Decimal(m['quantidade'])*m['preco_centavos']) for m in materiais)
    comp=composicao.calcular(
        total_centavos=preco+total_materiais, materiais_centavos=total_materiais,
        horas=tempo_horas, tipo_servico=nome, mao_obra_centavos=preco)
    comp_json=composicao.para_json(comp)
    composicao.instalar_banco(banco)
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
              (nome,descricao,preco_servico_centavos,materiais_json,relatorio_padrao,
               tempo_horas,composicao_json,criado_em,atualizado_em)
              VALUES(?,?,?,?,?,?,?,?,?)''',
              (nome,desc,preco,json.dumps(materiais,ensure_ascii=False),relatorio,
               tempo_horas,comp_json,ext.agora(),ext.agora())).lastrowid
        if not c.execute('SELECT 1 FROM catalogo_servicos WHERE id=?',(identificador,)).fetchone():
            raise ValueError('Serviço não encontrado.')
        c.execute('''UPDATE catalogo_servicos SET nome=?,descricao=?,preco_servico_centavos=?,
          materiais_json=?,relatorio_padrao=?,tempo_horas=?,composicao_json=?,atualizado_em=?
          WHERE id=?''',
          (nome,desc,preco,json.dumps(materiais,ensure_ascii=False),relatorio,
           tempo_horas,comp_json,ext.agora(),identificador))
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


def excluir(banco,identificador):
    """Remove o serviço do catálogo. OS antigas preservam seus próprios valores."""
    with ext.db(banco) as c:
        if not c.execute('DELETE FROM catalogo_servicos WHERE id=?',(int(identificador),)).rowcount:
            raise ValueError('Serviço não encontrado.')


def valores_orcamento(banco,identificador,quantidade=1):
    try:quantidade=int(quantidade)
    except (ValueError,TypeError):raise ValueError('Quantidade inválida.')
    if not 1<=quantidade<=20:raise ValueError('Quantidade deve estar entre 1 e 20.')
    servico=obter(banco,identificador,ativos=True)
    if not servico:raise ValueError('Serviço indisponível.')
    materiais=json.loads(servico['materiais_json'])
    materiais_total=sum(int(Decimal(m['quantidade'])*m['preco_centavos']) for m in materiais)
    comp=composicao.de_json(servico.get('composicao_json'))
    if not comp:
        try:
            comp=composicao.calcular(
                total_centavos=servico['preco_servico_centavos']+materiais_total,
                materiais_centavos=materiais_total,
                horas=servico.get('tempo_horas') or 0,
                tipo_servico=servico.get('nome') or '',
                mao_obra_centavos=servico['preco_servico_centavos'])
        except Exception:
            comp=None
    return {'servico':servico,'quantidade':quantidade,'materiais':materiais,
            'subtotal_servico':quantidade*servico['preco_servico_centavos'],
            'subtotal_materiais':quantidade*materiais_total,
            'total':quantidade*(servico['preco_servico_centavos']+materiais_total),
            'composicao':comp}


LIMITE_SERVICOS_ORCAMENTO = 20
LIMITE_MATERIAIS_ORCAMENTO = 50


def _lista_formulario(valor):
    if valor is None:
        return []
    if isinstance(valor, (list, tuple)):
        return list(valor)
    return [valor]


def _quantidade_servico(valor):
    if isinstance(valor, bool):
        raise ValueError('Quantidade do serviço inválida.')
    try:
        quantidade = int(str(valor).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError('Quantidade do serviço deve ser um número inteiro entre 1 e 20.') from exc
    if not 1 <= quantidade <= 20:
        raise ValueError('Quantidade do serviço deve estar entre 1 e 20.')
    return quantidade


def _quantidade_material(valor):
    if isinstance(valor, bool):
        raise ValueError('Quantidade do material inválida.')
    texto = str(valor).strip().replace(',', '.')
    try:
        quantidade = Decimal(texto)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Quantidade do material inválida.') from exc
    if not quantidade.is_finite() or quantidade <= 0 or quantidade > Decimal('1000'):
        raise ValueError('Quantidade do material deve ser maior que zero e no máximo 1.000.')
    return quantidade


def _quantidade_texto(valor):
    if isinstance(valor, Decimal):
        return format(valor.normalize(), 'f').replace('.', ',')
    return str(valor)


def _servico_orcamento_por_id(banco, identificador):
    try:
        identificador = int(identificador)
    except (TypeError, ValueError) as exc:
        raise ValueError('ID do serviço inválido.') from exc
    servico = obter(banco, identificador, ativos=True)
    if not servico:
        raise ValueError(f'Serviço {identificador} não encontrado ou inativo.')
    return servico


def _servico_orcamento_por_nome(banco, nome):
    nome = str(nome or '').strip()
    if not nome:
        raise ValueError('Nome do serviço não informado.')
    encontrados = [x for x in listar(banco, ativos=True)
                   if x['nome'].strip().casefold() == nome.casefold()]
    if not encontrados:
        raise ValueError(f'Serviço não encontrado ou inativo: {nome[:120]}')
    if len(encontrados) > 1:
        raise ValueError(f'Há mais de um serviço ativo com o nome "{nome[:120]}". Use o ID.')
    return encontrados[0]


def _material_orcamento_por_id(banco, identificador):
    from estoque_materiais import listar as listar_estoque
    try:
        identificador = int(identificador)
    except (TypeError, ValueError) as exc:
        raise ValueError('ID do material inválido.') from exc
    encontrados = [x for x in listar_estoque(banco, ativos=True)
                   if int(x['id']) == identificador]
    if not encontrados:
        raise ValueError(f'Material {identificador} não encontrado ou inativo.')
    return encontrados[0]


def _material_orcamento_por_nome(banco, nome):
    from estoque_materiais import listar as listar_estoque
    nome = str(nome or '').strip()
    if not nome:
        raise ValueError('Nome do material não informado.')
    encontrados = [x for x in listar_estoque(banco, ativos=True)
                   if x['nome'].strip().casefold() == nome.casefold()]
    if not encontrados:
        raise ValueError(f'Material não encontrado ou inativo: {nome[:120]}')
    if len(encontrados) > 1:
        raise ValueError(f'Há mais de um material ativo com o nome "{nome[:120]}". Use o ID.')
    return encontrados[0]


def montar_itens_orcamento(banco, servicos=None, materiais=None):
    """Resolve itens do catálogo/estoque e calcula o total no servidor.

    O formulário e o YAML nunca enviam preços. Serviços usam o preço ativo do
    catálogo (já incluindo seus materiais); materiais adicionais usam o preço de
    venda ativo do estoque.
    """
    servicos = servicos or []
    materiais = materiais or []
    if len(servicos) > LIMITE_SERVICOS_ORCAMENTO:
        raise ValueError(f'Máximo de {LIMITE_SERVICOS_ORCAMENTO} serviços por orçamento.')
    if len(materiais) > LIMITE_MATERIAIS_ORCAMENTO:
        raise ValueError(f'Máximo de {LIMITE_MATERIAIS_ORCAMENTO} materiais por orçamento.')

    servicos_saida = []
    ids_servico = set()
    for indice, item in enumerate(servicos, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f'Serviço {indice}: formato inválido.')
        if set(item) - {'id', 'nome', 'quantidade'}:
            raise ValueError(f'Serviço {indice}: campo desconhecido.')
        tem_id = item.get('id') not in (None, '')
        tem_nome = item.get('nome') not in (None, '')
        if tem_id == tem_nome:
            raise ValueError(f'Serviço {indice}: informe o id OU o nome, não ambos.')
        try:
            servico = (_servico_orcamento_por_id(banco, item['id']) if tem_id
                       else _servico_orcamento_por_nome(banco, item['nome']))
            quantidade = _quantidade_servico(item.get('quantidade', 1))
        except ValueError as exc:
            raise ValueError(f'Serviço {indice}: {exc}') from exc
        if servico['id'] in ids_servico:
            raise ValueError(f'Serviço repetido: {servico["nome"]}. Ajuste a quantidade em uma única linha.')
        ids_servico.add(servico['id'])
        unitario = int(valores_orcamento(banco, servico['id'], 1)['total'])
        total = int((Decimal(quantidade) * Decimal(unitario)).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP))
        servicos_saida.append({
            'id': servico['id'], 'nome': servico['nome'],
            'descricao': servico.get('descricao') or '',
            'quantidade': quantidade, 'unitario_centavos': unitario,
            'total_centavos': total,
        })

    materiais_saida = []
    ids_material = set()
    for indice, item in enumerate(materiais, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f'Material {indice}: formato inválido.')
        if set(item) - {'id', 'nome', 'quantidade'}:
            raise ValueError(f'Material {indice}: campo desconhecido.')
        tem_id = item.get('id') not in (None, '')
        tem_nome = item.get('nome') not in (None, '')
        if tem_id == tem_nome:
            raise ValueError(f'Material {indice}: informe o id OU o nome, não ambos.')
        try:
            material = (_material_orcamento_por_id(banco, item['id']) if tem_id
                        else _material_orcamento_por_nome(banco, item['nome']))
            quantidade = _quantidade_material(item.get('quantidade', 1))
        except ValueError as exc:
            raise ValueError(f'Material {indice}: {exc}') from exc
        if material['id'] in ids_material:
            raise ValueError(f'Material repetido: {material["nome"]}. Ajuste a quantidade em uma única linha.')
        ids_material.add(material['id'])
        unitario = int(material.get('venda_centavos') or 0)
        total = int((quantidade * Decimal(unitario)).quantize(
            Decimal('1'), rounding=ROUND_HALF_UP))
        materiais_saida.append({
            'id': material['id'], 'nome': material['nome'],
            'unidade': material.get('unidade') or 'un',
            'quantidade': quantidade, 'unitario_centavos': unitario,
            'total_centavos': total,
        })

    if not servicos_saida and not materiais_saida:
        raise ValueError('Adicione pelo menos um serviço ou material ao orçamento.')
    return {
        'servicos': servicos_saida,
        'materiais': materiais_saida,
        'total_centavos': sum(x['total_centavos'] for x in servicos_saida + materiais_saida),
    }


def linhas_orcamento_formulario(d):
    """Lê as linhas visíveis do formulário sem resolver preços ou IDs."""
    servicos_ids = _lista_formulario(d.get('servico_id[]'))
    servicos_qtd = _lista_formulario(d.get('servico_qtd[]'))
    if not servicos_ids and d.get('servico_id'):
        servicos_ids = [d.get('servico_id')]
        servicos_qtd = [d.get('quantidade', '1')]
    if len(servicos_ids) != len(servicos_qtd):
        raise ValueError('Linhas de serviço incompletas.')
    servicos = []
    for identificador, quantidade in zip(servicos_ids, servicos_qtd):
        if not str(identificador or '').strip():
            if str(quantidade or '').strip() not in ('', '1'):
                raise ValueError('Selecione o serviço ou remova a linha.')
            continue
        servicos.append({'id': str(identificador).strip(),
                         'quantidade': str(quantidade or '1').strip()})

    materiais_ids = _lista_formulario(d.get('material_id[]'))
    materiais_qtd = _lista_formulario(d.get('material_qtd[]'))
    if len(materiais_ids) != len(materiais_qtd):
        raise ValueError('Linhas de material incompletas.')
    materiais = []
    for identificador, quantidade in zip(materiais_ids, materiais_qtd):
        if not str(identificador or '').strip():
            if str(quantidade or '').strip() not in ('', '1'):
                raise ValueError('Selecione o material ou remova a linha.')
            continue
        materiais.append({'id': str(identificador).strip(),
                          'quantidade': str(quantidade or '1').strip()})
    if not servicos and not materiais:
        raise ValueError('Adicione pelo menos um serviço ou material ao orçamento.')
    return {'servicos': servicos, 'materiais': materiais}


def itens_orcamento_formulario(banco, d):
    linhas = linhas_orcamento_formulario(d)
    return montar_itens_orcamento(banco, linhas['servicos'], linhas['materiais'])


def pdf_orcamento_itens(banco, cliente, cliente_documento, itens,
                        validade=30, condicoes=''):
    """PDF de orçamento com vários serviços e materiais adicionais."""
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.pagesizes import A4

    nome_cliente = str(cliente or 'Cliente')[:120]
    doc_formato = marca.formatar_documento(cliente_documento)
    bio = BytesIO()
    doc = SimpleDocTemplate(bio, pagesize=A4, leftMargin=45, rightMargin=45,
                            topMargin=48, bottomMargin=48)
    styles = getSampleStyleSheet()
    normal = styles['BodyText']

    def par(s):
        return Paragraph(escape(str(s)), normal)

    logo = marca.logo_flowable(180, 42)
    titulo = Paragraph('<font color="#FFFFFF">Orçamento estimativo</font>', styles['Title'])
    content = []
    if logo is not None:
        cabecalho = Table([[logo, titulo]], colWidths=[200, 300], hAlign='LEFT')
        cabecalho.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#171717')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        content.append(cabecalho)
    else:
        content.append(titulo)
    content.extend([
        Spacer(1, 10),
        par('AUTOSEG — CNPJ ' + marca.CNPJ_PRINCIPAL),
        par('Emitido em: ' + datetime.now().strftime('%d/%m/%Y %H:%M')),
        par('Validade: ' + str(int(validade)) + ' dia(s)'),
        par('Solicitante: ' + nome_cliente + (' — ' + doc_formato if doc_formato else '')),
        *([par('Condições e observações: ' + str(condicoes)[:1000])] if condicoes else []),
        Spacer(1, 12),
    ])

    if itens['servicos']:
        content.append(Paragraph('Serviços', styles['Heading2']))
        linhas = [[par('Serviço'), par('Qtde.'), par('Unitário'), par('Total')]]
        for item in itens['servicos']:
            nome = escape(item['nome'])
            if item.get('descricao'):
                nome += '<br/><font size="8">' + escape(item['descricao'][:300]) + '</font>'
            linhas.append([
                Paragraph(nome, normal),
                par(str(item['quantidade'])),
                par(reais(item['unitario_centavos'])),
                par(reais(item['total_centavos'])),
            ])
        tabela = Table(linhas, colWidths=[270, 55, 90, 90], repeatRows=1, hAlign='LEFT')
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eee8c9')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), .35, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        content.append(tabela)
        content.append(Spacer(1, 12))

    if itens['materiais']:
        content.append(Paragraph('Materiais adicionais', styles['Heading2']))
        linhas = [[par('Material'), par('Qtde.'), par('Unitário'), par('Total')]]
        for item in itens['materiais']:
            linhas.append([
                par(item['nome'] + (' (' + item['unidade'] + ')' if item.get('unidade') else '')),
                par(_quantidade_texto(item['quantidade'])),
                par(reais(item['unitario_centavos'])),
                par(reais(item['total_centavos'])),
            ])
        tabela = Table(linhas, colWidths=[270, 55, 90, 90], repeatRows=1, hAlign='LEFT')
        tabela.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eee8c9')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), .35, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        content.append(tabela)
        content.append(Spacer(1, 12))

    resumo = []
    subtotal_servicos = sum(x['total_centavos'] for x in itens['servicos'])
    subtotal_materiais = sum(x['total_centavos'] for x in itens['materiais'])
    if itens['servicos']:
        resumo.append([par('Subtotal de serviços'), par(reais(subtotal_servicos))])
    if itens['materiais']:
        resumo.append([par('Subtotal de materiais adicionais'), par(reais(subtotal_materiais))])
    resumo.append([par('TOTAL ESTIMADO'), par(reais(itens['total_centavos']))])
    tabela_total = Table(resumo, colWidths=[350, 145], hAlign='LEFT')
    tabela_total.setStyle(TableStyle([
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FFF7D9')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), .35, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    content.extend([
        tabela_total,
        Spacer(1, 10),
        par('O valor unitário dos serviços já inclui os materiais cadastrados no '
            'próprio serviço. Materiais adicionais são cobrados separadamente.'),
        Spacer(1, 18),
        par('Estimativa automática, não é nota fiscal nem proposta contratual. '
            'Valores sujeitos a vistoria, disponibilidade e confirmação do prestador.'),
    ])

    def rodape(cv, doc):
        cv.setStrokeColor(colors.HexColor('#E2B800'))
        cv.line(45, 40, A4[0] - 45, 40)
        cv.setFillColor(colors.HexColor('#666666'))
        cv.setFont('Helvetica', 8)
        cv.drawString(45, 26, 'AUTOSEG — Orçamento estimativo · CNPJ ' + marca.CNPJ_PRINCIPAL)
        cv.drawRightString(A4[0] - 45, 26, 'Página ' + str(doc.page))
        marca.desenhar_selo(cv, doc)

    doc.build(content, onFirstPage=rodape, onLaterPages=rodape)
    return bio.getvalue()


def pdf_orcamento(banco,identificador,quantidade=1,cliente='Cliente',cliente_documento='',
                  validade=30,condicoes=''):
    """Gera orçamento não vinculante e sem dados financeiros confidenciais."""
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
    from reportlab.lib.pagesizes import A4
    dados=valores_orcamento(banco,identificador,quantidade)
    servico=dados['servico']
    nome_cliente=str(cliente or 'Cliente')[:120]
    doc_formato = marca.formatar_documento(cliente_documento)
    bio=BytesIO()
    doc=SimpleDocTemplate(bio,pagesize=A4,leftMargin=45,rightMargin=45,topMargin=48,bottomMargin=48)
    styles=getSampleStyleSheet()
    normal=styles['BodyText']
    def par(s):return Paragraph(escape(str(s)),normal)
    logo=marca.logo_flowable(180,42)
    titulo=Paragraph('<font color="#FFFFFF">Orçamento estimativo</font>',styles['Title'])
    content=[]
    if logo is not None:
        # O logo.png tem partes brancas com transparência: a faixa preta garante
        # contraste também em impressão e em telas claras.
        cabecalho=Table([[logo,titulo]],colWidths=[200,300],hAlign='LEFT')
        cabecalho.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#171717')),
                                       ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                                       ('LEFTPADDING',(0,0),(-1,-1),10),
                                       ('RIGHTPADDING',(0,0),(-1,-1),10),
                                       ('TOPPADDING',(0,0),(-1,-1),10),
                                       ('BOTTOMPADDING',(0,0),(-1,-1),10)]))
        content.append(cabecalho)
    else:
        content.append(titulo)
    content.extend([Spacer(1,10),
             par('AUTOSEG — CNPJ '+marca.CNPJ_PRINCIPAL),
             par('Emitido em: '+datetime.now().strftime('%d/%m/%Y %H:%M')),
             par('Validade: '+str(int(validade))+' dia(s)'),
             par('Solicitante: '+nome_cliente + (' — '+doc_formato if doc_formato else '')),
             *([par('Condições e observações: '+str(condicoes)[:1000])] if condicoes else []),
             Spacer(1,12),
             Paragraph(escape(servico['nome']),styles['Heading2']),par(servico['descricao'] or 'Serviço conforme catálogo'),Spacer(1,12)])
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
    content.append(tabela)
    comp=dados.get('composicao')
    if comp:
        comp=composicao.multiplicar(comp,dados['quantidade'])
        if int(comp.get('total_centavos',0))!=int(dados['total']):
            comp=composicao.calcular(
                total_centavos=dados['total'],materiais_centavos=dados['subtotal_materiais'],
                horas=(servico.get('tempo_horas') or 0)*dados['quantidade'],
                tipo_servico=servico.get('nome') or '',
                mao_obra_centavos=dados['subtotal_servico'])
        linhas_comp=[[par('Componente'),par('Valor'),par('%')]]
        for item in comp.get('componentes',[]):
            linhas_comp.append([par(item['nome']),par(reais(item['valor_centavos'])),
                                par(f"{item['percentual']:.2f}%".replace('.',','))])
        linhas_comp.append([par('TOTAL'),par(reais(comp['total_centavos'])),par('100,00%')])
        tabela_comp=Table(linhas_comp,colWidths=[280,110,80],repeatRows=1,hAlign='LEFT')
        tabela_comp.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eee8c9')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.35,colors.grey),
            ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#FFF7D9')),
            ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        content.extend([Spacer(1,14),Paragraph('Composição do valor (valor estimado)',styles['Heading3']),tabela_comp])
        if comp.get('aviso'):
            content.append(Spacer(1,6))
            content.append(par(comp['aviso']))
    content.extend([Spacer(1,18),par('Estimativa automática, não é nota fiscal nem proposta contratual. Valores sujeitos a vistoria, disponibilidade e confirmação do prestador.')])
    def rodape(cv, doc):
        cv.setStrokeColor(colors.HexColor('#E2B800'))
        cv.line(45, 40, A4[0]-45, 40)
        cv.setFillColor(colors.HexColor('#666666'))
        cv.setFont('Helvetica', 8)
        cv.drawString(45, 26, 'AUTOSEG — Orçamento estimativo · CNPJ '+marca.CNPJ_PRINCIPAL)
        cv.drawRightString(A4[0]-45, 26, 'Página '+str(doc.page))
        marca.desenhar_selo(cv, doc)
    doc.build(content, onFirstPage=rodape, onLaterPages=rodape)
    return bio.getvalue()
