"""AUTOSEG produtividade REV07: estado de deslocamento, rascunhos e políticas.
Migrações aditivas em SQLite, sem rede externa e sem mover dados antigos.
"""
import json
import re
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


def destinatarios_conclusao(banco,os_id,adicional=''):
    with ext.db(banco) as c:
        cl=c.execute("""SELECT cl.tipo_pessoa,cl.email,cl.sindico_email
            FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id
            WHERE o.id=?""",(os_id,)).fetchone()
        if not cl:raise ValueError('OS não encontrada.')
        # Morador solicitante nunca é destinatário automático.
        fontes=[cl['email']] if cl['tipo_pessoa']=='Física' else [cl['sindico_email'],cl['email']]
    resultado=[]
    for valor in fontes+[adicional]:
        e=_email_validado(valor)
        if e and e not in resultado:resultado.append(e)
    if not resultado:
        raise ValueError('Informe ao menos um e-mail para finalizar esta OS.')
    return resultado


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
