"""Casos de uso da conta pessoal e do atendimento PF (v9.4).

Sem dependência HTTP ou Tkinter. Preserva cliente legado/OS e não vincula
CPF informado na internet a OS históricas sem comprovação de titularidade.
"""
import re
import sqlite3
import prestadores_ext as ext
import cadastros_v9 as cad


def criar_conta(banco, cpf, senha):
    """Cadastro mínimo: CPF + senha; identidade pessoal compartilhada PF/PJ."""
    cpf = cad.digitos(cpf)
    if not cad.cpf_valido(cpf):
        raise ValueError('CPF inválido.')
    if len(senha) < 10:
        raise ValueError('A senha deve ter pelo menos 10 caracteres.')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT id FROM v9_usuarios WHERE cpf=?',(cpf,)).fetchone():
            raise ValueError('CPF já cadastrado. Entre com sua senha.')
        cur=c.execute('''INSERT INTO v9_usuarios(nome,cpf,telefone,email,senha_hash,criado_em,perfil_completo)
                         VALUES(?,?,?,?,?,?,0)''',
                      ('Cadastro '+cpf[-4:],cpf,'','',ext.senha_hash(senha),ext.agora()))
        return cur.lastrowid


def obter_perfil(banco,uid):
    with ext.db(banco) as c:
        v=c.execute('SELECT * FROM v9_usuarios WHERE id=? AND ativo=1',(uid,)).fetchone()
    if not v:raise PermissionError('Conta não encontrada ou inativa.')
    return dict(v)


def perfil_pronto(p):
    p=dict(p)
    return bool(p.get('perfil_completo') and all(str(p.get(k) or '').strip() for k in
                ('nome','telefone','email','endereco','numero','cidade','uf')))


def atualizar_perfil(banco,uid,d):
    nome=str(d.get('nome','')).strip()
    telefone=cad.digitos(d.get('telefone',''))
    email=str(d.get('email','')).strip().lower()
    endereco=str(d.get('endereco','')).strip()
    numero=str(d.get('numero','')).strip()
    bairro=str(d.get('bairro','')).strip()
    cidade=str(d.get('cidade','')).strip()
    uf=str(d.get('uf','')).strip().upper()
    cep=cad.digitos(d.get('cep',''))
    if not 3 <= len(nome) <= 120:raise ValueError('Informe seu nome completo.')
    if not 10 <= len(telefone) <= 13:raise ValueError('Informe seu telefone com DDD.')
    if len(email)>180 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
        raise ValueError('Informe um e-mail válido.')
    if not 4 <= len(endereco) <= 220:raise ValueError('Informe a rua e o endereço do atendimento.')
    if not 1 <= len(numero) <= 20:raise ValueError('Informe o número do endereço ou S/N.')
    if not 2 <= len(cidade) <= 100:raise ValueError('Informe a cidade.')
    if len(uf)!=2 or not uf.isalpha():raise ValueError('Informe a UF com duas letras.')
    if len(bairro)>100:raise ValueError('Bairro muito longo.')
    if cep and len(cep)!=8:raise ValueError('CEP deve ter 8 dígitos.')
    dados=(nome,telefone,email,endereco,numero,bairro,cidade,uf,cep)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        p=c.execute('SELECT cliente_pf_id FROM v9_usuarios WHERE id=? AND ativo=1',(uid,)).fetchone()
        if not p:raise PermissionError('Conta não encontrada.')
        c.execute('''UPDATE v9_usuarios SET nome=?,telefone=?,email=?,endereco=?,numero=?,
                     bairro=?,cidade=?,uf=?,cep=?,perfil_completo=1 WHERE id=?''',(*dados,uid))
        if p['cliente_pf_id']:
            c.execute('''UPDATE clientes SET nome=?,telefone=?,email=?,endereco=?,numero=?,
                        bairro=?,cidade=?,uf=?,cep=? WHERE id=? AND tipo_pessoa='Física' ''',
                      (*dados,p['cliente_pf_id']))
    return obter_perfil(banco,uid)


def listar_os_pf(banco,uid):
    p=obter_perfil(banco,uid)
    if not p['cliente_pf_id']:return []
    with ext.db(banco) as c:
        return c.execute('''SELECT id,numero_os,status,descricao,data_abertura FROM ordens_servico
                            WHERE cliente_id=? ORDER BY id DESC LIMIT 100''',(p['cliente_pf_id'],)).fetchall()


def registrar_os_pf(banco,uid,descricao,urgencia='Normal'):
    """Primeiro cria cliente PF próprio; nunca associa automaticamente ao cadastro antigo por CPF."""
    import atendimento_os as aten
    from banco import proximo_numero_os
    descricao=str(descricao).strip()
    if not 10<=len(descricao)<=2000:raise ValueError('Descreva o serviço (10 a 2.000 caracteres).')
    if urgencia not in ('Normal','Alta','Baixa'):raise ValueError('Urgência inválida.')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        p=c.execute('SELECT * FROM v9_usuarios WHERE id=? AND ativo=1',(uid,)).fetchone()
        if not p or not perfil_pronto(p):raise ValueError('Complete nome, telefone, e-mail e endereço antes de solicitar uma OS particular.')
        cid=p['cliente_pf_id']
        if cid:
            cl=c.execute("SELECT id FROM clientes WHERE id=? AND tipo_pessoa='Física' AND status!='Inativo'",(cid,)).fetchone()
            if not cl:raise ValueError('Seu cadastro PF está indisponível. Solicite atendimento à AUTOSEG.')
        else:
            cols={r['name'] for r in c.execute('PRAGMA table_info(clientes)')}
            valores={'tipo_pessoa':'Física','documento':p['cpf'],'nome':p['nome'],
                     'telefone':p['telefone'],'email':p['email'],'endereco':p['endereco'],
                     'numero':p['numero'],'bairro':p['bairro'],'cidade':p['cidade'],
                     'uf':p['uf'],'cep':p['cep'],'status':'Ativo','criado_em':ext.agora()}
            ks=[k for k in valores if k in cols]
            cur=c.execute(f'INSERT INTO clientes({",".join(ks)}) VALUES({",".join("?" for _ in ks)})',[valores[k] for k in ks])
            cid=cur.lastrowid
            c.execute('UPDATE v9_usuarios SET cliente_pf_id=? WHERE id=?',(cid,uid))
        numero_os=proximo_numero_os(c.cursor())
        dados={'numero_os':numero_os,'cliente_id':cid,'data_abertura':ext.agora(),
               'descricao':descricao,'valor_mao_obra':0,'valor_materiais':0,
               'valor_total':0,'forma_pagamento':'PIX','status':'Aberta',
               'origem':'Portal','urgencia':urgencia,'criado_em':ext.agora(),
               'observacoes':'Solicitação PF pelo portal pessoal; perfil completo.', 'tecnico':''}
        cols={r['name'] for r in c.execute('PRAGMA table_info(ordens_servico)')}
        ks=[k for k in dados if k in cols]
        oid=c.execute(f'INSERT INTO ordens_servico({",".join(ks)}) VALUES({",".join("?" for _ in ks)})',
                      [dados[k] for k in ks]).lastrowid
        aten.registrar_solicitacao(c,oid,cid,descricao,dados['observacoes'],'Portal PF')
        ext.evento(c,oid,'Solicitação PF',f'Conta pessoal #{uid} solicitou atendimento. Urgência: {urgencia}',ator='Cliente')
        return oid


def solicitar_administracao(banco,uid,org_id,cnpj,funcao=''):
    """Solicita vínculo de responsável PJ existente; nunca aprova privilégio automaticamente."""
    doc=cad.digitos(cnpj)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        org=c.execute('''SELECT id,tipo,cnpj FROM v9_organizacoes
                         WHERE id=? AND mesclado_em IS NULL''',(org_id,)).fetchone()
        if not org:raise ValueError('Organização não encontrada.')
        if org['cnpj']:
            if org['cnpj']!=doc:
                raise ValueError('O documento informado não corresponde ao cadastro. Solicite revisão à AUTOSEG.')
        elif doc and not cad.cnpj_valido(doc):
            raise ValueError('CNPJ inválido. Corrija o número ou deixe em branco.')
        papel='Síndico' if org['tipo']=='Condomínio' else 'Administrador'
        vinc=c.execute('SELECT id,papel,situacao FROM v9_vinculos WHERE usuario_id=? AND organizacao_id=?',
                       (uid,org_id)).fetchone()
        if vinc:
            if vinc['papel']==papel and vinc['situacao']=='Aprovado':return papel
            c.execute('''UPDATE v9_vinculos SET papel=?,situacao='Pendente',aprovado_em=NULL,
                         funcao_declarada=CASE WHEN ?<>'' THEN ? ELSE funcao_declarada END
                         WHERE id=?''',(papel,str(funcao).strip()[:60],str(funcao).strip()[:60],vinc['id']))
        else:
            c.execute('''INSERT INTO v9_vinculos(organizacao_id,usuario_id,papel,situacao,criado_em,funcao_declarada)
                         VALUES(?,?,?,'Pendente',?,?)''',
                      (org_id,uid,papel,ext.agora(),str(funcao).strip()[:60]))
        # O documento digitado NÃO é gravado no cadastro se este não possuía CNPJ verificado.
        return papel


def cadastrar_organizacao_responsavel(banco,uid,d):
    """Cadastra a PJ como responsável OU pede vínculo na PJ já existente (sem duplicar)."""
    tipo=str(d.get('tipo','')).strip()
    if tipo not in ('Condomínio','Empresa'):raise ValueError('Tipo de organização inválido.')
    nome=str(d.get('nome','')).strip()
    endereco=str(d.get('endereco','')).strip()
    cidade=str(d.get('cidade','')).strip()
    bairro=str(d.get('bairro','')).strip()
    cnpj=cad.digitos(d.get('cnpj',''))
    funcao=str(d.get('funcao','')).strip()[:60] or ('Síndico' if tipo=='Condomínio' else 'Representante legal')
    if not cad.cnpj_valido(cnpj):raise ValueError('Para se cadastrar como responsável, informe um CNPJ válido.')
    if len(endereco)<5:raise ValueError('Informe o endereço completo da organização.')
    papel='Síndico' if tipo=='Condomínio' else 'Administrador'
    existente=cad.organizacao_por_cnpj(banco,cnpj)
    if existente:
        # Nunca duplica a organização; apenas registra pedido de vínculo pendente.
        cad.solicitar_vinculo(banco,uid,existente['id'],papel,'',funcao)
        return existente['id'],True
    org_id=cad.criar_organizacao(banco,uid,nome,tipo,cnpj,cidade,bairro,papel,endereco,'',funcao)
    return org_id,False


def registrar_chamado_org(banco,uid,d):
    """Chamado de morador/funcionário/porteiro para condomínio ou empresa."""
    unidade=str(d.get('unidade','')).strip()
    papel=str(d.get('papel','')).strip()
    if not 1<=len(unidade)<=100:raise ValueError('Informe o apartamento ou o cargo/função.')
    if papel not in ('Morador','Funcionário'):raise ValueError('Escolha o seu papel no local.')
    try:org=int(d.get('org_id','0'))
    except (TypeError,ValueError):raise ValueError('Selecione uma organização.')
    return cad.registrar_chamado(banco,uid,org,str(d.get('descricao','')),str(d.get('urgencia','Normal')),
                                 unidade,papel,str(d.get('solicitante_nome','')))


def obter_os_pf(banco,uid,os_id):
    """OS particular do próprio usuário (nunca de outro CPF)."""
    p=obter_perfil(banco,uid)
    if not p.get('cliente_pf_id'):return None
    with ext.db(banco) as c:
        return c.execute('''SELECT id,numero_os,status,descricao,data_abertura
                            FROM ordens_servico WHERE id=? AND cliente_id=?''',
                         (os_id,p['cliente_pf_id'])).fetchone()


def obter_chamado(banco,uid,chamado_id):
    """Chamado do próprio usuário, com a organização e a OS quando já convertida."""
    with ext.db(banco) as c:
        return c.execute('''SELECT h.id,h.status,h.descricao,h.unidade,h.papel,h.criado_em,h.os_id,
                                   h.solicitante_nome,o.nome organizacao,o.tipo,os.numero_os
                            FROM v9_chamados h JOIN v9_organizacoes o ON o.id=h.organizacao_id
                            LEFT JOIN ordens_servico os ON os.id=h.os_id
                            WHERE h.id=? AND h.usuario_id=?''',(chamado_id,uid)).fetchone()

