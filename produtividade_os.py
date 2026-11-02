"""AUTOSEG produtividade REV07: estado de deslocamento, rascunhos e políticas.
Migrações aditivas em SQLite, sem rede externa e sem mover dados antigos.
"""
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import prestadores_ext as ext

CAMPOS = (
    'v9_diagnostico','v9_execucao','v9_resultado','relatorio_tecnico',
    'valor_mao_obra','valor_materiais_manual','valor_total_override',
    'forma_pagamento','tecnico','motivo_encerramento',
    'material_item[]','material_qtd[]','material_unit[]'
)


def instalar(banco):
    with ext.db(banco) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS produtividade_deslocamentos(
            os_id INTEGER PRIMARY KEY, prestador_id INTEGER NOT NULL,
            em_rota INTEGER NOT NULL DEFAULT 0,
            atualizado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS produtividade_rascunhos(
            os_id INTEGER PRIMARY KEY, prestador_id INTEGER NOT NULL,
            versao INTEGER NOT NULL DEFAULT 1,
            dados_json TEXT NOT NULL, atualizado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS produtividade_etapas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            os_id INTEGER NOT NULL, prestador_id INTEGER NOT NULL,
            situacao TEXT NOT NULL, dados_json TEXT NOT NULL,
            hash_conteudo TEXT NOT NULL, registrado_em TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_prod_etapas_os
            ON produtividade_etapas(os_id,id);
        CREATE TABLE IF NOT EXISTS produtividade_email(
            os_id INTEGER PRIMARY KEY,
            destinatarios_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente',
            message_id TEXT, erro TEXT, atualizado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS produtividade_rateios(
            os_id INTEGER NOT NULL, tecnico_id INTEGER NOT NULL,
            valor_centavos INTEGER NOT NULL CHECK(valor_centavos>=0),
            definidor_id INTEGER NOT NULL, registrado_em TEXT NOT NULL,
            PRIMARY KEY(os_id,tecnico_id));
        CREATE TABLE IF NOT EXISTS produtividade_repasses(
            os_id INTEGER NOT NULL, tecnico_id INTEGER NOT NULL,
            pago_centavos INTEGER NOT NULL DEFAULT 0 CHECK(pago_centavos>=0),
            atualizado_em TEXT NOT NULL,
            PRIMARY KEY(os_id,tecnico_id));
        CREATE TABLE IF NOT EXISTS produtividade_bancos(
            prestador_id INTEGER PRIMARY KEY, dados_texto TEXT NOT NULL,
            atualizado_em TEXT NOT NULL);
        """)


def _os_ativa_responsavel(c,os_id,pid):
    os_=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
    if not os_ or os_['status'] not in ext.ATIVAS:
        raise ValueError('OS não está aberta ou pendente.')
    if ext.responsavel_atual(c,os_id)!=pid:
        raise PermissionError('Somente o técnico atribuído pode alterar esta OS.')
    return os_


def em_rota(banco,os_id):
    with ext.db(banco) as c:
        r=c.execute('SELECT em_rota,prestador_id,atualizado_em FROM produtividade_deslocamentos WHERE os_id=?',(os_id,)).fetchone()
        return dict(r) if r else {'em_rota':0,'prestador_id':None,'atualizado_em':None}


def marcar_em_rota(banco,os_id,pid,ativo=True,admin=False):
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        o=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
        if not o or o['status'] not in ext.ATIVAS:
            raise ValueError('Somente OS abertas ou pendentes podem estar em rota.')
        responsavel=ext.responsavel_atual(c,os_id)
        if responsavel is None:
            raise ValueError('Atribua um técnico antes de marcar Em rota.')
        if not admin and responsavel!=pid:
            raise PermissionError('Somente o responsável ou administrador pode alterar Em rota.')
        novo=1 if ativo else 0
        c.execute("""INSERT INTO produtividade_deslocamentos(os_id,prestador_id,em_rota,atualizado_em)
            VALUES(?,?,?,?) ON CONFLICT(os_id) DO UPDATE SET
            prestador_id=excluded.prestador_id,em_rota=excluded.em_rota,
            atualizado_em=excluded.atualizado_em""",(os_id,responsavel,novo,ext.agora()))
        ext.evento(c,os_id,'Em rota' if ativo else 'Saiu de rota',
                   'Deslocamento informado manualmente, sem localização GPS.',pid,'Administrador' if admin else f'Prestador {pid}')
        return novo


def limpar_rota_ao_iniciar(banco,os_id):
    with ext.db(banco) as c:
        c.execute('UPDATE produtividade_deslocamentos SET em_rota=0, atualizado_em=? WHERE os_id=?',
                  (ext.agora(),os_id))


def _payload(d):
    resultado={}
    for campo in CAMPOS:
        valor=d.get(campo, [] if campo.endswith('[]') else '')
        if campo.endswith('[]'):
            if not isinstance(valor,list): valor=[valor]
            if len(valor)>100:raise ValueError('Rascunho com materiais demais.')
            resultado[campo]=[str(v)[:350] for v in valor]
        else:
            resultado[campo]=str(valor)[:20000]
    conteudo=json.dumps(resultado,ensure_ascii=False)
    if len(conteudo.encode('utf-8'))>250000:
        raise ValueError('Rascunho maior que 250 KB. Imagens são anexos separados.')
    return conteudo


def salvar_rascunho(banco,os_id,pid,d,versao_esperada=None):
    conteudo=_payload(d)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        _os_ativa_responsavel(c,os_id,pid)
        atual=c.execute('SELECT versao FROM produtividade_rascunhos WHERE os_id=?',(os_id,)).fetchone()
        if versao_esperada is not None and int(versao_esperada)!=(atual['versao'] if atual else 0):
            raise ValueError('O rascunho foi alterado. Recarregue antes de substituir a versão atual.')
        versao=(atual['versao']+1) if atual else 1
        c.execute("""INSERT INTO produtividade_rascunhos
            (os_id,prestador_id,versao,dados_json,atualizado_em) VALUES(?,?,?,?,?)
            ON CONFLICT(os_id) DO UPDATE SET prestador_id=excluded.prestador_id,
            versao=excluded.versao,dados_json=excluded.dados_json,
            atualizado_em=excluded.atualizado_em""",
            (os_id,pid,versao,conteudo,ext.agora()))
        return versao


def recuperar_rascunho(banco,os_id,pid):
    with ext.db(banco) as c:
        _os_ativa_responsavel(c,os_id,pid)
        r=c.execute('SELECT * FROM produtividade_rascunhos WHERE os_id=?',(os_id,)).fetchone()
        if not r:return None
        return {'versao':r['versao'],'autor_id':r['prestador_id'],
                'atualizado_em':r['atualizado_em'],'dados':json.loads(r['dados_json'])}


def registrar_etapa(banco,os_id,pid,situacao,d):
    if situacao not in ('Pendente','Concluída'):
        raise ValueError('Etapa de atendimento inválida.')
    conteudo=_payload(d)
    digest=sha256(conteudo.encode('utf-8')).hexdigest()
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        if ext.responsavel_atual(c,os_id)!=pid:
            raise PermissionError('Somente responsável registra etapa.')
        anterior=c.execute("""SELECT id FROM produtividade_etapas
            WHERE os_id=? AND prestador_id=? AND situacao=? AND hash_conteudo=?
            ORDER BY id DESC LIMIT 1""",(os_id,pid,situacao,digest)).fetchone()
        if anterior:return anterior['id']
        return c.execute("""INSERT INTO produtividade_etapas
            (os_id,prestador_id,situacao,dados_json,hash_conteudo,registrado_em)
            VALUES(?,?,?,?,?,?)""",(os_id,pid,situacao,conteudo,digest,ext.agora())).lastrowid


def listar_etapas(banco,os_id):
    with ext.db(banco) as c:
        return [dict(r) for r in c.execute("""SELECT e.*,p.nome tecnico
            FROM produtividade_etapas e LEFT JOIN prestadores p ON p.id=e.prestador_id
            WHERE e.os_id=? ORDER BY e.id""",(os_id,))]


def _email_validado(s):
    email=str(s or '').strip()
    if not email:return ''
    if len(email)>254 or re.fullmatch(r'[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+',email) is None:
        raise ValueError('E-mail de destino inválido.')
    return email.lower()


def contatos_email_os(banco,os_id):
    """Contatos autorizados da OS, sem escolher automaticamente por ninguém."""
    with ext.db(banco) as c:
        cl=c.execute("""SELECT cl.tipo_pessoa,cl.email,cl.sindico_email,cl.administradora_email
            FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id
            WHERE o.id=?""",(os_id,)).fetchone()
    if not cl:raise ValueError('OS não encontrada.')
    return {
        'cliente': cl['email'] or '',
        'sindico': cl['sindico_email'] or '',
        'administradora': cl['administradora_email'] or '',
        'tipo_pessoa': cl['tipo_pessoa'],
    }


def destinatarios_para_os(banco,os_id,selecionados=None,adicionais=''):
    """Monta a lista final a partir das caixas marcadas + e-mails manuais.

    Seleção explícita nunca é sobrescrita pelo síndico. Quando `selecionados`
    é None (desktop legado), usa o comportamento anterior: cliente + síndico.
    """
    import re as _re
    contatos=contatos_email_os(banco,os_id)
    if selecionados is None:
        chaves=['cliente'] if contatos['tipo_pessoa']=='Física' else ['sindico','cliente']
    else:
        if isinstance(selecionados,str):selecionados=[selecionados]
        chaves=[str(x) for x in selecionados]
    resultado=[]
    for chave in chaves:
        e=_email_validado(contatos.get(chave,''))
        if e and e not in resultado:resultado.append(e)
    for valor in _re.split(r'[,;\s]+',str(adicionais or '')):
        e=_email_validado(valor)
        if e and e not in resultado:resultado.append(e)
    if not resultado:
        raise ValueError('Selecione ao menos um destinatário válido para finalizar esta OS.')
    return resultado


def destinatarios_conclusao(banco,os_id,adicional=''):
    """Compatibilidade: cliente + síndico (desktop) + e-mail adicional."""
    return destinatarios_para_os(banco,os_id,None,adicional)


def participou(c,os_id,pid):
    if ext.responsavel_atual(c,os_id)==pid:return True
    if c.execute('SELECT 1 FROM os_prestadores WHERE os_id=? AND prestador_id=?',(os_id,pid)).fetchone():return True
    if c.execute('SELECT 1 FROM os_eventos WHERE os_id=? AND prestador_id=?',(os_id,pid)).fetchone():return True
    return bool(c.execute('SELECT 1 FROM os_conclusoes WHERE os_id=? AND prestador_id=?',(os_id,pid)).fetchone())


def controlar_pdf(banco,os_id,pid):
    with ext.db(banco) as c:
        if not participou(c,os_id,pid):
            raise PermissionError('Este prestador não participou da OS.')


def registrar_envio(banco,os_id,destinatarios,status='pendente',message_id=None,erro=''):
    if status not in ('pendente','enviado','falhou'):raise ValueError('Estado de e-mail inválido.')
    with ext.db(banco) as c:
        c.execute("""INSERT INTO produtividade_email
        (os_id,destinatarios_json,status,message_id,erro,atualizado_em)
        VALUES(?,?,?,?,?,?) ON CONFLICT(os_id) DO UPDATE SET
        destinatarios_json=excluded.destinatarios_json,status=excluded.status,
        message_id=excluded.message_id,erro=excluded.erro,
        atualizado_em=excluded.atualizado_em""",
        (os_id,json.dumps(destinatarios),status,message_id,(erro or '')[:500],ext.agora()))


def _centavos(valor):
    """Dinheiro em centavos inteiros, sem ponto flutuante."""
    try:
        entrada=str(valor or '0').strip().replace('R$','').replace(' ','')
        if ',' in entrada:entrada=entrada.replace('.','').replace(',','.')
        montante=Decimal(entrada)
        if not montante.is_finite() or montante<0 or montante>Decimal('10000000'):
            raise ValueError('Valor de rateio fora dos limites.')
        return int((montante*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    except (InvalidOperation,TypeError) as erro:
        raise ValueError('Valor de rateio inválido.') from erro


def registrar_rateios_na_transacao(c,os_id,finalizador_id,valor_bruto,d):
    """Chamar dentro da transação de conclusão; Pendente/Cancelada não têm rateio."""
    os_atual=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
    final=c.execute('SELECT prestador_id FROM os_encerramentos WHERE os_id=?',(os_id,)).fetchone()
    if not os_atual or os_atual['status']!='Concluída' or not final or final['prestador_id']!=finalizador_id:
        raise PermissionError('Somente o técnico finalizador pode definir valores ao concluir.')
    tecnicos=d.get('rateio_tecnico[]',[])
    valores=d.get('rateio_valor[]',[])
    if not isinstance(tecnicos,list):tecnicos=[tecnicos]
    if not isinstance(valores,list):valores=[valores]
    if len(tecnicos)>25 or len(tecnicos)!=len(valores):
        raise ValueError('Rateio incompleto ou com técnicos demais.')
    parcelas={}
    for tid,valor in zip(tecnicos,valores):
        if not str(tid).strip() and not str(valor).strip():continue
        if not str(tid).isdigit():
            raise ValueError('Selecione o técnico secundário.')
        ident=int(tid)
        if ident==finalizador_id or ident in parcelas:
            raise ValueError('Técnico duplicado ou finalizador indicado como secundário.')
        cents=_centavos(valor)
        if cents<=0:raise ValueError('Informe valor positivo para cada técnico secundário.')
        ativo=c.execute('SELECT 1 FROM prestadores WHERE id=? AND ativo=1',(ident,)).fetchone()
        if not ativo:raise ValueError('Técnico secundário não encontrado ou inativo.')
        parcelas[ident]=cents
    bruto=_centavos(valor_bruto)
    if sum(parcelas.values())>bruto:
        raise ValueError('As parcelas dos técnicos superam o valor cobrado pela OS.')
    # Esta função só roda na primeira conclusão. Mudanças posteriores exigem
    # fluxo formal de revisão com auditoria, nunca substituição silenciosa.
    if c.execute('SELECT 1 FROM produtividade_rateios WHERE os_id=?',(os_id,)).fetchone():
        raise ValueError('Esta OS já possui rateio registrado; não é possível sobrescrever.')
    for ident,cents in parcelas.items():
        c.execute("""INSERT INTO os_prestadores(os_id,prestador_id,atribuido_em,ativo)
            VALUES(?,?,?,1) ON CONFLICT(os_id,prestador_id) DO UPDATE SET ativo=1""",
            (os_id,ident,ext.agora()))
        c.execute("""INSERT INTO produtividade_rateios
            (os_id,tecnico_id,valor_centavos,definidor_id,registrado_em)
            VALUES(?,?,?,?,?)""",(os_id,ident,cents,finalizador_id,ext.agora()))
        c.execute("""INSERT INTO produtividade_repasses(os_id,tecnico_id,pago_centavos,atualizado_em)
            VALUES(?,?,0,?)""",(os_id,ident,ext.agora()))
    ext.evento(c,os_id,'Rateio definido',
              f'Bruto {bruto} centavos; secundários {sum(parcelas.values())} centavos; líquido do finalizador {bruto-sum(parcelas.values())} centavos.',
              finalizador_id,f'Prestador {finalizador_id}')
    return bruto-sum(parcelas.values())


def financeiro_pessoal(banco,pid):
    """Detalha obrigações internas sem somar repasses ao faturamento bruto."""
    with ext.db(banco) as c:
        proprio=[dict(r) for r in c.execute("""SELECT f.os_id,o.numero_os,f.valor,
            COALESCE((SELECT SUM(r.valor_centavos) FROM produtividade_rateios r
                      WHERE r.os_id=f.os_id),0) partes_centavos,f.status
            FROM financeiro f
            JOIN ordens_servico o ON o.id=f.os_id
            JOIN os_encerramentos e ON e.os_id=f.os_id
            WHERE e.prestador_id=? ORDER BY f.id DESC""",(pid,))]
        meus=[dict(r) for r in c.execute("""SELECT r.os_id,o.numero_os,r.valor_centavos,
            COALESCE(p.pago_centavos,0) pago_centavos,e.prestador_id de_tecnico
            FROM produtividade_rateios r
            JOIN ordens_servico o ON o.id=r.os_id
            JOIN os_encerramentos e ON e.os_id=r.os_id
            LEFT JOIN produtividade_repasses p ON p.os_id=r.os_id AND p.tecnico_id=r.tecnico_id
            WHERE r.tecnico_id=? ORDER BY r.os_id DESC""",(pid,))]
        repassar=[dict(r) for r in c.execute("""SELECT r.os_id,o.numero_os,r.tecnico_id,t.nome tecnico,
            r.valor_centavos,COALESCE(p.pago_centavos,0) pago_centavos
            FROM produtividade_rateios r
            JOIN ordens_servico o ON o.id=r.os_id
            JOIN prestadores t ON t.id=r.tecnico_id
            JOIN os_encerramentos e ON e.os_id=r.os_id
            LEFT JOIN produtividade_repasses p ON p.os_id=r.os_id AND p.tecnico_id=r.tecnico_id
            WHERE e.prestador_id=? ORDER BY r.os_id DESC""",(pid,))]
        return {'brutos_proprios':proprio,'receber_de_colegas':meus,'repassar_a_colegas':repassar}


def confirmar_repasse(banco,os_id,finalizador_id,secundario_id,valor):
    """Confirma transferência financeira já executada manualmente fora do AUTOSEG."""
    cents=_centavos(valor)
    if cents<=0:raise ValueError('Valor de repasse deve ser positivo.')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        e=c.execute('SELECT prestador_id FROM os_encerramentos WHERE os_id=?',(os_id,)).fetchone()
        if not e or e['prestador_id']!=finalizador_id:
            raise PermissionError('Somente o finalizador registra o repasse que realizou.')
        item=c.execute('SELECT valor_centavos FROM produtividade_rateios WHERE os_id=? AND tecnico_id=?',
                       (os_id,secundario_id)).fetchone()
        if not item:raise ValueError('Parcela deste técnico não existe.')
        atual=c.execute('SELECT pago_centavos FROM produtividade_repasses WHERE os_id=? AND tecnico_id=?',
                        (os_id,secundario_id)).fetchone()
        pago=atual['pago_centavos'] if atual else 0
        if cents+pago>item['valor_centavos']:
            raise ValueError('Repasse excede a parcela devida.')
        c.execute("""INSERT INTO produtividade_repasses
          (os_id,tecnico_id,pago_centavos,atualizado_em) VALUES(?,?,?,?)
          ON CONFLICT(os_id,tecnico_id) DO UPDATE SET
          pago_centavos=excluded.pago_centavos,atualizado_em=excluded.atualizado_em""",
          (os_id,secundario_id,pago+cents,ext.agora()))
        ext.evento(c,os_id,'Repasse confirmado',f'{cents} centavos para técnico {secundario_id}.',
                   finalizador_id,f'Prestador {finalizador_id}')
        return item['valor_centavos']-pago-cents


def salvar_dados_bancarios(banco,pid,texto):
    conteudo=str(texto or '').strip()
    if len(conteudo)>1500:raise ValueError('Dados bancários longos demais.')
    with ext.db(banco) as c:
        if not c.execute('SELECT 1 FROM prestadores WHERE id=? AND ativo=1',(pid,)).fetchone():
            raise PermissionError('Prestador inexistente.')
        c.execute("""INSERT INTO produtividade_bancos(prestador_id,dados_texto,atualizado_em)
            VALUES(?,?,?) ON CONFLICT(prestador_id) DO UPDATE SET
            dados_texto=excluded.dados_texto,atualizado_em=excluded.atualizado_em""",
            (pid,conteudo,ext.agora()))


def obter_dados_bancarios(banco,pid):
    with ext.db(banco) as c:
        r=c.execute('SELECT dados_texto FROM produtividade_bancos WHERE prestador_id=?',(pid,)).fetchone()
        return r['dados_texto'] if r else ''
