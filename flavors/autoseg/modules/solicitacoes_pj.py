"""Solicitações PJ públicas (sem cadastro PF) e verificação pelo prestador.

Fluxo: visitante escolhe condomínio/empresa, informa nome, telefone e pedido;
recebe um protocolo e um link wa.me. O prestador vê a solicitação em
"Solicitações PJ" e só pode Aceitar (cria a OS) ou Recusar (com motivo).
"""
import json
import re
from urllib.parse import quote

from officina.core import prestadores_ext as ext
from officina.core import portal_negocios as neg
from officina.core import cadastros_v9 as cad
from officina.core.banco import proximo_numero_os


def instalar(banco):
    with ext.db(banco) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS pj_solicitacoes_publicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organizacao_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            telefone TEXT NOT NULL,
            descricao TEXT NOT NULL,
            urgencia TEXT NOT NULL DEFAULT 'Normal',
            status TEXT NOT NULL DEFAULT 'Aguardando verificação',
            os_id INTEGER,
            criado_em TEXT NOT NULL,
            decidido_em TEXT,
            decidido_por TEXT NOT NULL DEFAULT '',
            motivo TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_pj_pub_status ON pj_solicitacoes_publicas(status,id);
        ''')


def _telefone(valor):
    n = cad.digitos(valor)
    if not 10 <= len(n) <= 13:
        raise ValueError('Informe telefone com DDD.')
    return n


def criar(banco, organizacao_id, nome, telefone, descricao, urgencia='Normal'):
    nome = ' '.join(str(nome or '').split())[:120]
    if not 3 <= len(nome):
        raise ValueError('Informe seu nome completo.')
    tel = _telefone(telefone)
    descricao = str(descricao or '').strip()
    if not 10 <= len(descricao) <= 2000:
        raise ValueError('Descreva a solicitação com 10 a 2.000 caracteres.')
    if urgencia not in ('Baixa', 'Normal', 'Alta'):
        raise ValueError('Urgência inválida.')
    instalar(banco)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        org = c.execute('SELECT id,nome,tipo FROM v9_organizacoes WHERE id=? AND mesclado_em IS NULL',
                        (int(organizacao_id),)).fetchone()
        if not org:
            raise ValueError('Condomínio ou empresa não encontrado.')
        cur = c.execute('''INSERT INTO pj_solicitacoes_publicas
            (organizacao_id,nome,telefone,descricao,urgencia,status,criado_em)
            VALUES(?,?,?,?,?,'Aguardando verificação',?)''',
            (org['id'], nome, tel, descricao, urgencia, ext.agora()))
        return {'id': cur.lastrowid, 'protocolo': f'PJ-{cur.lastrowid:04d}',
                'organizacao': org['nome'], 'nome': nome, 'telefone': tel}


def link_whatsapp(solicitacao):
    msg = (f"AUTOSEG — Solicitação de abertura de O.S. {solicitacao['protocolo']} "
           f"para {solicitacao['organizacao']}. Solicitante: {solicitacao['nome']}, "
           f"telefone {solicitacao['telefone']}. Por favor, verifiquem o pedido de abertura de O.S.")
    return 'https://wa.me/' + cad.WHATSAPP_AUTOSEG + '?text=' + quote(msg)


def obter(banco, solicitacao_id):
    instalar(banco)
    with ext.db(banco) as c:
        r = c.execute('''SELECT p.*,o.nome organizacao,o.tipo org_tipo
            FROM pj_solicitacoes_publicas p JOIN v9_organizacoes o ON o.id=p.organizacao_id
            WHERE p.id=?''', (int(solicitacao_id),)).fetchone()
        return dict(r) if r else None


def listar(banco, status=None, limite=200):
    instalar(banco)
    with ext.db(banco) as c:
        sql = '''SELECT p.*,o.nome organizacao,o.tipo org_tipo
                 FROM pj_solicitacoes_publicas p JOIN v9_organizacoes o ON o.id=p.organizacao_id'''
        params = []
        if status:
            sql += ' WHERE p.status=?'
            params.append(status)
        sql += ' ORDER BY p.id DESC LIMIT ?'
        params.append(int(limite))
        return [dict(x) for x in c.execute(sql, params).fetchall()]


def _cliente_da_organizacao(c, org):
    if org['cliente_id']:
        cl = c.execute("SELECT id FROM clientes WHERE id=? AND status!='Inativo'",
                       (org['cliente_id'],)).fetchone()
        if cl:
            return cl['id']
    if not org['cnpj']:
        raise ValueError('A organização não tem CNPJ nem cliente vinculado. Cadastre-a no desktop antes de aceitar.')
    doc = org['cnpj']
    existe = c.execute("SELECT id FROM clientes WHERE documento=? AND tipo_pessoa='Jurídica' ORDER BY id LIMIT 1",
                       (doc,)).fetchone()
    if existe:
        cid = existe['id']
    else:
        cid = c.execute('''INSERT INTO clientes
            (tipo_pessoa,documento,nome,endereco,cidade,bairro,status,observacoes,criado_em)
            VALUES('Jurídica',?,?,?,?,?,'Prospect',?,?)''',
            (doc, org['nome'], org['endereco'] or '', org['cidade'] or '', org['bairro'] or '',
             'Cadastro provisório criado ao aceitar solicitação pública PJ.', ext.agora())).lastrowid
    c.execute('UPDATE v9_organizacoes SET cliente_id=? WHERE id=? AND cliente_id IS NULL', (cid, org['id']))
    return cid


def aceitar(banco, solicitacao_id, ator='Prestador'):
    instalar(banco)
    from officina.core import atendimento_os as aten
    aten.instalar(banco)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        p = c.execute('SELECT * FROM pj_solicitacoes_publicas WHERE id=?', (int(solicitacao_id),)).fetchone()
        if not p:
            raise ValueError('Solicitação não encontrada.')
        if p['status'] != 'Aguardando verificação':
            raise ValueError('Esta solicitação já foi decidida.')
        org = c.execute('SELECT * FROM v9_organizacoes WHERE id=? AND mesclado_em IS NULL',
                        (p['organizacao_id'],)).fetchone()
        if not org:
            raise ValueError('Organização inexistente ou mesclada.')
        cid = _cliente_da_organizacao(c, org)
        numero = proximo_numero_os(c.cursor())
        observacoes = (f'Solicitação pública {p["id"]:04d} | Solicitante: {p["nome"]} | '
                       f'Telefone: {p["telefone"]} | Urgência: {p["urgencia"]} | '
                       f'Verificada por {ator}.')
        cur = c.execute('''INSERT INTO ordens_servico
            (numero_os,cliente_id,data_abertura,tecnico,descricao,valor_mao_obra,valor_materiais,
             valor_total,forma_pagamento,status,origem,urgencia,observacoes,criado_em)
            VALUES(?,?,?,'',?,0,0,0,'','Aberta','Portal PJ público',?,?,?)''',
            (numero, cid, ext.agora(), p['descricao'], p['urgencia'], observacoes, ext.agora()))
        oid = cur.lastrowid
        aten.registrar_solicitacao(c, oid, cid, p['descricao'], observacoes, 'Portal PJ público')
        ext.evento(c, oid, 'Solicitação PJ pública aceita',
                   f'{p["nome"]} / {p["telefone"]} — protocolo PJ-{p["id"]:04d}', ator=ator)
        c.execute('''UPDATE pj_solicitacoes_publicas SET status='Aceito',os_id=?,decidido_em=?,
                     decidido_por=? WHERE id=?''', (oid, ext.agora(), str(ator)[:120], p['id']))
        return {'os_id': oid, 'numero_os': numero, 'cliente_id': cid}


def recusar(banco, solicitacao_id, motivo, ator='Prestador'):
    motivo = str(motivo or '').strip()
    if len(motivo) < 5:
        raise ValueError('Informe o motivo da recusa (mínimo de 5 caracteres).')
    instalar(banco)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        p = c.execute('SELECT * FROM pj_solicitacoes_publicas WHERE id=?', (int(solicitacao_id),)).fetchone()
        if not p:
            raise ValueError('Solicitação não encontrada.')
        if p['status'] != 'Aguardando verificação':
            raise ValueError('Esta solicitação já foi decidida.')
        c.execute('''UPDATE pj_solicitacoes_publicas SET status='Recusado',motivo=?,decidido_em=?,
                     decidido_por=? WHERE id=?''', (motivo[:1000], ext.agora(), str(ator)[:120], p['id']))
        return True
