"""Relatório limpo, voltado ao cliente. Auditoria técnica permanece no banco, não no PDF."""
from pathlib import Path
from xml.sax.saxutils import escape
from datetime import datetime
import re
from officina.core import prestadores_ext as ext
from officina.core import pdf_identidade as identidade
from officina.core import composicao
from officina.core import cadastros_v9 as cad
from flavors.autoseg.modules import texto_os
def data_br(valor):
    s=str(valor or '').strip()
    try:return datetime.fromisoformat(s.replace('Z','+00:00')).strftime('%d/%m/%Y às %H:%M')
    except ValueError:return s or 'Não informado'

def brl(v):
    return 'R$ '+f'{float(v or 0):,.2f}'.replace(',','@').replace('.',',').replace('@','.')

def _cnpj_no_texto(texto):
    """Extrai um CNPJ formatado ou de 14 dígitos de dados cadastrais livres."""
    texto=str(texto or '')
    for padrao in (r'CNPJ[^\d]{0,30}(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})',
                   r'\b(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b',
                   r'\b(\d{14})\b'):
        for achado in re.finditer(padrao,texto,re.IGNORECASE):
            cnpj=identidade.formatar_cnpj(achado.group(1))
            if cnpj and cad.cnpj_valido(cnpj):
                return cnpj
    return ''

def gerar(banco,os_id):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image as PdfImage,KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.enums import TA_CENTER,TA_RIGHT
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from PIL import Image, ImageOps
    import io
    with ext.db(banco) as c:
        os_=c.execute('SELECT o.*,cl.nome cliente,cl.documento cliente_documento FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id WHERE o.id=?',(os_id,)).fetchone()
        if not os_:raise ValueError('Ordem de serviço não encontrada.')
        sol=c.execute('SELECT descricao_original FROM os_solicitacoes WHERE os_id=?',(os_id,)).fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE name='os_solicitacoes'").fetchone() else None
        enc=c.execute('SELECT relatorio,motivo,encerrado_em FROM os_encerramentos WHERE os_id=?',(os_id,)).fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE name='os_encerramentos'").fetchone() else None
        resp=c.execute('SELECT p.id,p.nome,p.documento FROM os_responsaveis r JOIN prestadores p ON p.id=r.prestador_id WHERE r.os_id=?',(os_id,)).fetchone()
        mats=c.execute('SELECT item,quantidade,unidade,valor_total FROM materiais_os WHERE os_id=? ORDER BY id',(os_id,)).fetchall()
        financeiro=c.execute('SELECT status FROM financeiro WHERE os_id=? ORDER BY id DESC LIMIT 1',(os_id,)).fetchone()
        detalhes=c.execute('SELECT diagnostico,execucao,resultado FROM v9_detalhes_os WHERE os_id=?',(os_id,)).fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE name='v9_detalhes_os'").fetchone() else None
        atendimento=c.execute('SELECT rascunho FROM os_atendimentos WHERE os_id=?',(os_id,)).fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE name='os_atendimentos'").fetchone() else None
        comp=composicao.de_json(os_['composicao_json']) if 'composicao_json' in os_.keys() else None
        if not comp or int(comp.get('total_centavos',0))!=composicao.centavos_de_reais(os_['valor_total']):
            try:
                comp=composicao.calcular_os(
                    total_centavos=composicao.centavos_de_reais(os_['valor_total']),
                    materiais_centavos=composicao.centavos_de_reais(os_['valor_materiais']),
                    horas=os_['tempo_horas'] if 'tempo_horas' in os_.keys() else 0,
                    mao_obra_centavos=composicao.centavos_de_reais(os_['valor_mao_obra']))
            except Exception:
                comp=None
        anexos=[]
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='v9_anexos_visiveis'").fetchone():
            anexos=c.execute('''SELECT a.caminho,a.nome_original,COALESCE(v.legenda,'') AS legenda FROM os_anexos a LEFT JOIN v9_anexos_visiveis v ON v.anexo_id=a.id WHERE a.os_id=? AND COALESCE(v.visivel,1)=1 ORDER BY a.ordem,a.id''',(os_id,)).fetchall()
    estilo=getSampleStyleSheet()
    preto=colors.HexColor('#171717');amarelo=colors.HexColor('#E2B800');cinza=colors.HexColor('#666666')
    estilo.add(ParagraphStyle(name='AutosegTituloV9',fontName='Helvetica-Bold',fontSize=14,leading=18,textColor=preto,spaceAfter=8))
    estilo.add(ParagraphStyle(name='AutosegSecaoV9',fontName='Helvetica-Bold',fontSize=10,leading=14,textColor=preto,spaceBefore=13,spaceAfter=7))
    estilo.add(ParagraphStyle(name='AutosegCorpoV9',fontName='Helvetica',fontSize=9,leading=13,textColor=preto,spaceAfter=5))
    estilo.add(ParagraphStyle(name='AutosegPequenoV9',fontName='Helvetica',fontSize=8,leading=11,textColor=cinza,spaceAfter=6))
    P=lambda s:Paragraph(escape(str(s or 'Não informado')).replace('\n','<br/>'),estilo['AutosegCorpoV9'])
    PB=lambda s:Paragraph('<b>'+escape(str(s or ''))+'</b>',estilo['AutosegCorpoV9'])
    S=lambda s:Paragraph(escape(str(s)),estilo['AutosegSecaoV9'])
    # Filhos da composição declarativa: recuados e em cinza para diferenciar do pai.
    Pfilho=lambda s:Paragraph('&nbsp;&nbsp;&nbsp;&nbsp;<font color="#555555">— '+escape(str(s or ''))+'</font>',estilo['AutosegCorpoV9'])
    # CNPJ do prestador: usa o documento quando for CNPJ; senão procura um
    # CNPJ nos dados bancários/cadastrais unificados. Sem CNPJ, usa o principal.
    cnpj_prestador = identidade.formatar_cnpj(resp['documento']) if resp else ''
    if not cnpj_prestador and resp:
        try:
            config=ext.obter_config_prestador(banco,resp['id'])
            cnpj_prestador=_cnpj_no_texto(config.get('dados_bancarios_texto',''))
        except Exception:
            cnpj_prestador=''
    if not cnpj_prestador:
        cnpj_prestador = identidade.CNPJ_PRINCIPAL
    prestador_texto = (resp['nome'] if resp else 'Não informado') + ' — CNPJ ' + cnpj_prestador
    # Documento do cliente (CPF ou CNPJ) exibido no cabeçalho.
    doc_cliente = identidade.formatar_documento(os_['cliente_documento'] if 'cliente_documento' in os_.keys() else '')
    cliente_texto = str(os_['cliente'])
    if doc_cliente:
        cliente_texto += ' — ' + doc_cliente
    linhas=[]
    logo_texto=Paragraph('<font color="#FFFFFF">AUTO</font><font color="#FFD400">SEG</font>',
        ParagraphStyle('LogoV9',fontName='Helvetica-Bold',fontSize=19,leading=21))
    logo=identidade.logo_flowable(175,38) or logo_texto
    marca=Paragraph('<font color="#FFD400"><b>AUTOMAÇÃO E SEGURANÇA</b></font>',
        ParagraphStyle('TagV9',fontName='Helvetica-Bold',fontSize=8,alignment=TA_RIGHT))
    topo=Table([[logo,marca]],colWidths=[255,255])
    topo.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),preto),('TOPPADDING',(0,0),(-1,-1),13),('BOTTOMPADDING',(0,0),(-1,-1),13)]))
    linhas.extend([topo,Spacer(1,13),Paragraph('RELATÓRIO TÉCNICO DE SERVIÇO',estilo['AutosegTituloV9'])])
    dados=[[P('Ordem de serviço: '+str(os_['numero_os'])),P('Situação: '+str(os_['status']))],
           [P('Cliente: '+cliente_texto),P('Prestador: '+prestador_texto)],
           [P('Abertura: '+data_br(os_['data_abertura'])),P('Encerramento: '+data_br(enc['encerrado_em'] if enc else os_['data_conclusao']))]]
    tb=Table(dados,colWidths=[255,255]);tb.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#F7F7F7')),('BOTTOMPADDING',(0,0),(-1,-1),8)]));linhas.append(tb)
    linhas.extend([S('01  SOLICITAÇÃO ORIGINAL'),P(sol['descricao_original'] if sol else os_['descricao'])])
    linhas.append(S('02  ATENDIMENTO REALIZADO'))
    # OS pendente: além do resumo em três campos, o e-mail/PDF leva o relatório
    # técnico completo que o prestador escreveu. OS já encerradas continuam com
    # o comportamento anterior.
    relato_pendente=''
    if os_['status']=='Pendente':
        relato_pendente=((atendimento['rascunho'] if atendimento else '') or
                         (enc['relatorio'] if enc else '')).strip()
    tem_resumo=bool(detalhes and any(detalhes[x] for x in ('diagnostico','execucao','resultado')))
    if tem_resumo:
        for label,field in [('Diagnóstico','diagnostico'),('Serviço executado','execucao'),('Resultado e testes','resultado')]:
            if detalhes[field]:linhas.append(P(label+': '+detalhes[field]))
    if relato_pendente:
        if tem_resumo:linhas.append(PB('Relatório técnico'))
        linhas.append(P(relato_pendente))
    elif not tem_resumo:
        if enc and enc['relatorio']:linhas.append(P(enc['relatorio']))
        else:linhas.append(P('Relato técnico não informado.'))
    if enc and enc['motivo']:linhas.append(P('Motivo: '+enc['motivo']))
    linhas.append(S('03  MATERIAIS UTILIZADOS'))
    cab=[Paragraph('<b>Material</b>',estilo['AutosegCorpoV9']),Paragraph('<b>Quantidade</b>',estilo['AutosegCorpoV9']),Paragraph('<b>Valor</b>',estilo['AutosegCorpoV9'])]
    registros=[cab]
    for m in mats:
        qtd=m['quantidade']; unidade=str(m['unidade'] or '').strip()
        if qtd is None:
            quantidade='—' + (' '+unidade if unidade else '')
        else:
            quantidade=f'{float(qtd):g}' + (' '+unidade if unidade else ' un.')
        registros.append([P(m['item']),P(quantidade),P(brl(m['valor_total']))])
    if len(registros)==1:registros.append([P('Nenhum material detalhado'),P('—'),P('—')])
    tm=Table(registros,colWidths=[315,85,110],repeatRows=1)
    tm.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F0F0F0')),('LINEBELOW',(0,0),(-1,0),1,amarelo),('LINEBELOW',(0,1),(-1,-1),0.3,colors.HexColor('#DDDDDD')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    linhas.append(tm)
    if comp:
        linhas_comp=[[Paragraph('<b>Componente</b>',estilo['AutosegCorpoV9']),
                      Paragraph('<b>Valor</b>',estilo['AutosegCorpoV9']),
                      Paragraph('<b>%</b>',estilo['AutosegCorpoV9'])]]
        for item in comp.get('componentes',[]):
            linhas_comp.append([P(item.get('nome','')),P(brl(item.get('valor_centavos',0)/100)),
                                P(f"{item.get('percentual',0):.2f}%".replace('.',','))])
            for filho in item.get('filhos',[]):
                linhas_comp.append([Pfilho(filho.get('nome','')),P(brl(filho.get('valor_centavos',0)/100)),
                                    P(f"{filho.get('percentual',0):.2f}%".replace('.',','))])
        linhas_comp.append([PB('TOTAL'),PB(brl(comp.get('total_centavos',0)/100)),PB('100,00%')])
        tc=Table(linhas_comp,colWidths=[300,100,60],repeatRows=1)
        tc.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F0F0F0')),
            ('LINEBELOW',(0,0),(-1,0),1,amarelo),('LINEBELOW',(0,1),(-1,-1),0.3,colors.HexColor('#DDDDDD')),
            ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#FFF7D9')),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        # Mantém o cabeçalho da seção e a tabela (inclusive a linha TOTAL)
        # unidos, evitando linha órfã na página seguinte.
        linhas.append(KeepTogether([S('04  COMPOSIÇÃO DO VALOR (VALOR ESTIMADO)'), tc]))
        if comp.get('aviso'):linhas.append(P(comp['aviso']))
    else:
        linhas.append(S('04  COMPOSIÇÃO DO VALOR (VALOR ESTIMADO)'))
        linhas.append(P('Composição não disponível para esta OS.'))
    linhas.append(S('05  VALORES E PAGAMENTO'))
    valores=[['TOTAL',brl(os_['valor_total'])],
            ['Forma de pagamento',str(os_['forma_pagamento'] or 'Não informada')],['Situação financeira',str(financeiro['status'] if financeiro else 'Sem lançamento')]]
    tf=Table([[P(a),P(b)] for a,b in valores],colWidths=[330,180]);tf.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#FFF7D9')),('LINEABOVE',(0,0),(-1,0),1,amarelo),('BOTTOMPADDING',(0,0),(-1,-1),7)]));linhas.append(tf)
    texto_adicional=str(os_['texto_adicional'] or '').strip() if 'texto_adicional' in os_.keys() else ''
    if texto_adicional:
        linhas.append(S(texto_os.titulo_pdf()))
        linhas.append(P(texto_adicional))
    if anexos:
        comprimir=True
        if 'comprimir_fotos_pdf' in os_.keys():
            comprimir=bool(os_['comprimir_fotos_pdf'])
        primeira_foto=True
        for a in anexos:
            p=Path(a['caminho'])
            if not p.is_file():continue
            try:
                with Image.open(p) as im:
                    # Aplica a orientação EXIF: o navegador já gira a prévia,
                    # mas o PDF precisa do mesmo resultado.
                    im=ImageOps.exif_transpose(im)
                    if comprimir:
                        # Resolução preservada para tela e impressão; reduz
                        # apenas imagens maiores que o limite.
                        im.thumbnail((1400, 1400))
                        qualidade=85
                    else:
                        qualidade=95
                    buf=io.BytesIO();im.convert('RGB').save(buf,format='JPEG',quality=qualidade);buf.seek(0)
                    w,h=im.size
                # Usa a largura útil da página (A4 com margens de 42pt) sem
                # distorcer: a escala preserva a proporção original.
                escala=min(480/w, 540/h)
                foto=PdfImage(buf,width=w*escala,height=h*escala)
                bloco=([S('06  REGISTRO FOTOGRÁFICO')] if primeira_foto else []) + [P(a['legenda'] or 'Registro do atendimento'),foto,Spacer(1,8)]
                linhas.append(KeepTogether(bloco))
                primeira_foto=False
            except Exception:continue
    linhas.append(Spacer(1,9))
    linhas.append(Paragraph('Documento de atendimento técnico. A situação financeira não equivale a comprovante de quitação nem a nota fiscal.',estilo['AutosegPequenoV9']))
    numero_limpo=re.sub(r"[^A-Za-z0-9_-]","_",str(os_["numero_os"] or "")).strip("_")
    if not numero_limpo:
        raise ValueError('OS sem número público; não é possível gerar o PDF.')
    nome=f'{numero_limpo}.pdf'
    destino=ext.RELATORIOS/nome
    def rodape(cv,doc):
        cv.setStrokeColor(amarelo);cv.line(40,34,A4[0]-40,34)
        cv.setFillColor(cinza);cv.setFont('Helvetica',8)
        cv.drawString(40,22,'AUTOSEG • Relatório técnico para o cliente')
        cv.drawRightString(A4[0]-40,22,'Página '+str(doc.page))
        identidade.desenhar_selo(cv,doc)
    SimpleDocTemplate(str(destino),pagesize=A4,leftMargin=42,rightMargin=42,topMargin=35,bottomMargin=49,
        title='AUTOSEG - Relatório '+str(os_['numero_os'])).build(linhas,onFirstPage=rodape,onLaterPages=rodape)
    return str(destino)
