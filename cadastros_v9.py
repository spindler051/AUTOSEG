"""AUTOSEG v9: pessoas vinculadas a organizações, chamados e aprovação em camadas.
Migração aditiva; nenhuma tabela legada é apagada ou renomeada.
"""
import re
import secrets
import sqlite3
from datetime import datetime
import prestadores_ext as ext

SITUACOES = ('Aguardando AUTOSEG', 'Aguardando síndico', 'Autorizado', 'Recusado', 'Mais informações', 'Cancelado')
PAPEIS = ('Morador', 'Funcionário', 'Síndico', 'Administrador')

def digitos(s): return re.sub(r'\D','',str(s or ''))

def cpf_valido(s):
    s=digitos(s)
    if len(s)!=11 or s==s[:1]*11:return False
    for n in (9,10):
        dig=(sum(int(s[i])*(n+1-i) for i in range(n))*10)%11
        if dig==10:dig=0
        if dig!=int(s[n]):return False
    return True

def cnpj_valido(s):
    s=digitos(s)
    if len(s)!=14 or s==s[0]*14:return False
    for n,pesos in [(12,[5,4,3,2,9,8,7,6,5,4,3,2]),(13,[6,5,4,3,2,9,8,7,6,5,4,3,2])]:
        z=sum(int(s[i])*pesos[i] for i in range(n))%11
        if (0 if z<2 else 11-z)!=int(s[n]):return False
    return True

def instalar(banco):
    with ext.db(banco) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS v9_admin_prestadores(
          prestador_id INTEGER PRIMARY KEY, autorizado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS v9_usuarios(
          id INTEGER PRIMARY KEY, nome TEXT NOT NULL, cpf TEXT NOT NULL UNIQUE,
          telefone TEXT NOT NULL, email TEXT DEFAULT '', senha_hash TEXT NOT NULL,
          ativo INTEGER NOT NULL DEFAULT 1, criado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS v9_organizacoes(
          id INTEGER PRIMARY KEY, cliente_id INTEGER, nome TEXT NOT NULL,
          tipo TEXT NOT NULL CHECK(tipo IN ('Condomínio','Empresa')),
          cnpj TEXT UNIQUE, cidade TEXT DEFAULT '', bairro TEXT DEFAULT '',
          situacao TEXT NOT NULL DEFAULT 'Pendente', criado_em TEXT NOT NULL,
          criado_por INTEGER, mesclado_em INTEGER);
        CREATE TABLE IF NOT EXISTS v9_vinculos(
          id INTEGER PRIMARY KEY, organizacao_id INTEGER NOT NULL, usuario_id INTEGER NOT NULL,
          papel TEXT NOT NULL, situacao TEXT NOT NULL DEFAULT 'Pendente',
          criado_em TEXT NOT NULL, aprovado_em TEXT,
          UNIQUE(organizacao_id,usuario_id));
        CREATE TABLE IF NOT EXISTS v9_chamados(
          id INTEGER PRIMARY KEY, organizacao_id INTEGER NOT NULL,
          usuario_id INTEGER NOT NULL, descricao TEXT NOT NULL, urgencia TEXT NOT NULL,
          unidade TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'Aguardando AUTOSEG',
          criado_em TEXT NOT NULL, avaliado_em TEXT, avaliado_por TEXT,
          confirmado_em TEXT, confirmado_por TEXT, motivo TEXT DEFAULT '', os_id INTEGER,
          FOREIGN KEY(organizacao_id) REFERENCES v9_organizacoes(id),
          FOREIGN KEY(usuario_id) REFERENCES v9_usuarios(id));
        CREATE TABLE IF NOT EXISTS v9_notificacoes(
          id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL,
          chamado_id INTEGER, texto TEXT NOT NULL, visto INTEGER NOT NULL DEFAULT 0,
          criado_em TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_v9_notif_user ON v9_notificacoes(usuario_id,visto,id);
        CREATE TABLE IF NOT EXISTS v9_eventos(
          id INTEGER PRIMARY KEY, chamado_id INTEGER NOT NULL, ator TEXT NOT NULL,
          acao TEXT NOT NULL, descricao TEXT DEFAULT '', criado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS v9_anexos_visiveis(
          anexo_id INTEGER PRIMARY KEY, visivel INTEGER NOT NULL DEFAULT 0,
          legenda TEXT DEFAULT '', autorizado_em TEXT);
        CREATE TABLE IF NOT EXISTS v9_detalhes_os(
          os_id INTEGER PRIMARY KEY, diagnostico TEXT DEFAULT '',
          execucao TEXT DEFAULT '', resultado TEXT DEFAULT '', alterado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS v9_historico_clientes(
          id INTEGER PRIMARY KEY, cliente_id INTEGER, origem_id INTEGER,
          acao TEXT NOT NULL, descricao TEXT DEFAULT '',
          autor TEXT NOT NULL, criado_em TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_v9_chamados_org ON v9_chamados(organizacao_id,status);
        CREATE INDEX IF NOT EXISTS idx_v9_vinculos_user ON v9_vinculos(usuario_id,situacao);
        ''')
        # Migração aditiva: contato do síndico confirmado pelo operador AUTOSEG.
        cols_org={r['name'] for r in c.execute('PRAGMA table_info(v9_organizacoes)')}
        if 'sindico_telefone' not in cols_org:
            c.execute("ALTER TABLE v9_organizacoes ADD COLUMN sindico_telefone TEXT DEFAULT ''")
        if 'sindico_nome' not in cols_org:
            c.execute("ALTER TABLE v9_organizacoes ADD COLUMN sindico_nome TEXT DEFAULT ''")
        # v9.4: conta pessoal mínima (CPF/senha), perfil PF progressivo e
        # pré-cadastros com endereço e identificação da unidade/cargo.
        cols_u={r['name'] for r in c.execute('PRAGMA table_info(v9_usuarios)')}
        for coluna,tipo in {
            'endereco':"TEXT DEFAULT ''", 'numero':"TEXT DEFAULT ''",
            'bairro':"TEXT DEFAULT ''", 'cidade':"TEXT DEFAULT ''",
            'uf':"TEXT DEFAULT ''", 'cep':"TEXT DEFAULT ''",
            'perfil_completo':'INTEGER NOT NULL DEFAULT 0',
            'cliente_pf_id':'INTEGER',
        }.items():
            if coluna not in cols_u:
                c.execute(f'ALTER TABLE v9_usuarios ADD COLUMN {coluna} {tipo}')
        if 'endereco' not in cols_org:
            c.execute("ALTER TABLE v9_organizacoes ADD COLUMN endereco TEXT DEFAULT ''")
        cols_v={r['name'] for r in c.execute('PRAGMA table_info(v9_vinculos)')}
        if 'unidade' not in cols_v:
            c.execute("ALTER TABLE v9_vinculos ADD COLUMN unidade TEXT DEFAULT ''")
        # v9.4.1: função declarada pelo solicitante (síndico/proprietário/representante)
        # e papel (morador/funcionário) registrado no próprio chamado.
        if 'funcao_declarada' not in cols_v:
            c.execute("ALTER TABLE v9_vinculos ADD COLUMN funcao_declarada TEXT DEFAULT ''")
        cols_ch={r['name'] for r in c.execute('PRAGMA table_info(v9_chamados)')}
        if 'papel' not in cols_ch:
            c.execute("ALTER TABLE v9_chamados ADD COLUMN papel TEXT DEFAULT ''")
        if 'solicitante_nome' not in cols_ch:
            c.execute("ALTER TABLE v9_chamados ADD COLUMN solicitante_nome TEXT DEFAULT ''")
        # Importa cadastros PJ existentes, de modo idempotente, sem expor CNPJ ao público.
        cols={r['name'] for r in c.execute('PRAGMA table_info(clientes)')}
        if {'id','nome','tipo_pessoa','documento'}.issubset(cols):
            sql="SELECT id,nome,documento,cidade,bairro FROM clientes WHERE tipo_pessoa='Jurídica' AND status!='Inativo'" if 'bairro' in cols and 'cidade' in cols else "SELECT id,nome,documento,'' cidade,'' bairro FROM clientes WHERE tipo_pessoa='Jurídica' AND status!='Inativo'"
            for x in c.execute(sql).fetchall():
                if c.execute('SELECT 1 FROM v9_organizacoes WHERE cliente_id=?',(x['id'],)).fetchone():continue
                doc=digitos(x['documento'])
                # CNPJ inválido/duplicado é deixado em branco para revisão; não inventa dado.
                if not cnpj_valido(doc) or c.execute('SELECT 1 FROM v9_organizacoes WHERE cnpj=?',(doc,)).fetchone():doc=None
                c.execute('INSERT INTO v9_organizacoes(cliente_id,nome,tipo,cnpj,cidade,bairro,situacao,criado_em) VALUES(?,?,?,?,?,?,?,?)',
                    (x['id'],x['nome'],'Condomínio' if 'condom' in x['nome'].lower() else 'Empresa',doc,x['cidade'] or '',x['bairro'] or '', 'Importado - revisar',ext.agora()))
        if 'sindico_telefone' in cols:
            for x in c.execute("SELECT id,sindico_nome,sindico_telefone FROM clientes WHERE tipo_pessoa='Jurídica'").fetchall():
                if x['sindico_telefone']:
                    c.execute("UPDATE v9_organizacoes SET sindico_telefone=CASE WHEN COALESCE(sindico_telefone,'')='' THEN ? ELSE sindico_telefone END, sindico_nome=CASE WHEN COALESCE(sindico_nome,'')='' THEN ? ELSE sindico_nome END WHERE cliente_id=?", (digitos(x['sindico_telefone']),x['sindico_nome'] or '',x['id']))

def cadastrar_usuario(banco,nome,cpf,telefone,senha,email=''):
    cpf=digitos(cpf);fone=digitos(telefone)
    if not 3<=len(nome.strip())<=120:raise ValueError('Informe nome completo (3 a 120 caracteres).')
    if not cpf_valido(cpf):raise ValueError('CPF inválido.')
    if not 10<=len(fone)<=13:raise ValueError('Informe telefone válido com DDD.')
    if len(senha)<10:raise ValueError('A senha deve ter pelo menos 10 caracteres.')
    with ext.db(banco) as c:
        if c.execute('SELECT 1 FROM v9_usuarios WHERE cpf=?',(cpf,)).fetchone():raise ValueError('CPF já cadastrado. Entre com sua senha.')
        cur=c.execute('INSERT INTO v9_usuarios(nome,cpf,telefone,email,senha_hash,criado_em) VALUES(?,?,?,?,?,?)',
            (nome.strip(),cpf,fone,str(email).strip()[:180],ext.senha_hash(senha),ext.agora()))
        return cur.lastrowid

def autenticar(banco,cpf,senha):
    with ext.db(banco) as c:
        x=c.execute('SELECT * FROM v9_usuarios WHERE cpf=? AND ativo=1',(digitos(cpf),)).fetchone()
        if x and ext.verificar_senha(senha,x['senha_hash']):return dict(x)
    return None

def criar_organizacao(banco,usuario_id,nome,tipo,cnpj='',cidade='',bairro='',papel='Morador',endereco='',unidade='',funcao=''):
    nome=nome.strip();cnpj=digitos(cnpj) or None
    if not 3<=len(nome)<=160:raise ValueError('Informe o nome completo da organização.')
    if tipo not in ('Condomínio','Empresa'):raise ValueError('Tipo inválido.')
    if cnpj and not cnpj_valido(cnpj):raise ValueError('CNPJ inválido.')
    if papel not in PAPEIS:raise ValueError('Perfil inválido.')
    if papel in ('Síndico','Administrador') and not cnpj:
        raise ValueError('Informe o CNPJ ao solicitar cadastro como síndico/administrador. Caso não o tenha, solicite vínculo como Morador.')
    cidade=str(cidade or '').strip()[:100];bairro=str(bairro or '').strip()[:100]
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        if cnpj and c.execute('SELECT 1 FROM v9_organizacoes WHERE cnpj=? AND mesclado_em IS NULL',(cnpj,)).fetchone():
            raise ValueError('Organização já cadastrada. Pesquise na lista e solicite vínculo.')
        # Sem CNPJ: reaproveita pré-cadastro idêntico (nome + cidade) para não duplicar.
        if not cnpj:
            igual=c.execute('''SELECT id FROM v9_organizacoes
                               WHERE mesclado_em IS NULL AND cnpj IS NULL
                                 AND lower(trim(nome))=? AND lower(trim(COALESCE(cidade,'')))=?''',
                            (nome.lower(),cidade.lower())).fetchone()
            if igual:
                atual=c.execute('SELECT id,papel,situacao FROM v9_vinculos WHERE organizacao_id=? AND usuario_id=?',
                                (igual['id'],usuario_id)).fetchone()
                if atual and atual['papel']==papel and atual['situacao']=='Aprovado':
                    return igual['id']
                if atual:
                    c.execute('''UPDATE v9_vinculos SET papel=?,situacao='Pendente',aprovado_em=NULL,
                                 unidade=CASE WHEN ?<>'' THEN ? ELSE unidade END,
                                 funcao_declarada=CASE WHEN ?<>'' THEN ? ELSE funcao_declarada END
                                 WHERE id=?''',
                              (papel,str(unidade).strip()[:100],str(unidade).strip()[:100],
                               str(funcao).strip()[:60],str(funcao).strip()[:60],atual['id']))
                else:
                    c.execute('''INSERT INTO v9_vinculos(organizacao_id,usuario_id,papel,situacao,criado_em,unidade,funcao_declarada)
                                 VALUES(?,?,?,'Pendente',?,?,?)''',
                              (igual['id'],usuario_id,papel,ext.agora(),str(unidade).strip()[:100],str(funcao).strip()[:60]))
                return igual['id']
        x=c.execute('INSERT INTO v9_organizacoes(nome,tipo,cnpj,cidade,bairro,criado_em,criado_por) VALUES(?,?,?,?,?,?,?)',
                    (nome,tipo,cnpj,cidade,bairro,ext.agora(),usuario_id))
        c.execute('UPDATE v9_organizacoes SET endereco=? WHERE id=?',
                  (str(endereco).strip()[:240],x.lastrowid))
        c.execute('INSERT INTO v9_vinculos(organizacao_id,usuario_id,papel,criado_em,unidade,funcao_declarada) VALUES(?,?,?,?,?,?)',
                  (x.lastrowid,usuario_id,papel,ext.agora(),str(unidade).strip()[:100],str(funcao).strip()[:60]))
        return x.lastrowid


def organizacao_por_cnpj(banco,cnpj):
    """Localiza organização ativa pelo CNPJ (comparação exata em dígitos)."""
    doc=digitos(cnpj)
    if len(doc)!=14:return None
    with ext.db(banco) as c:
        return c.execute('''SELECT id,nome,tipo,cnpj,situacao FROM v9_organizacoes
                            WHERE cnpj=? AND mesclado_em IS NULL''',(doc,)).fetchone()


def localizar_organizacoes(banco,nome='',cidade=''):
    """Pré-cadastro sem CNPJ: evita duplicar nome+cidade já existentes."""
    n=str(nome or '').strip().lower();cid=str(cidade or '').strip().lower()
    if not n:return None
    with ext.db(banco) as c:
        return c.execute('''SELECT id,nome,tipo FROM v9_organizacoes
                            WHERE mesclado_em IS NULL AND lower(trim(nome))=?
                              AND lower(trim(COALESCE(cidade,'')))=?''',(n,cid)).fetchone()


def solicitar_vinculo(banco,usuario_id,org_id,papel,unidade='',funcao=''):
    """Pedido de vínculo sempre pendente; nunca concede privilégio por conhecimento do CNPJ."""
    if papel not in PAPEIS:raise ValueError('Perfil inválido.')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        o=c.execute('SELECT id FROM v9_organizacoes WHERE id=? AND mesclado_em IS NULL',(org_id,)).fetchone()
        if not o:raise ValueError('Condomínio/empresa não encontrado.')
        atual=c.execute('SELECT id,papel,situacao FROM v9_vinculos WHERE organizacao_id=? AND usuario_id=?',
                        (org_id,usuario_id)).fetchone()
        if atual and atual['papel']==papel and atual['situacao']=='Aprovado':
            return 'Aprovado'
        if atual:
            c.execute('''UPDATE v9_vinculos SET papel=?,situacao='Pendente',aprovado_em=NULL,
                         unidade=CASE WHEN ?<>'' THEN ? ELSE unidade END,
                         funcao_declarada=CASE WHEN ?<>'' THEN ? ELSE funcao_declarada END
                         WHERE id=?''',
                      (papel,str(unidade).strip()[:100],str(unidade).strip()[:100],
                       str(funcao).strip()[:60],str(funcao).strip()[:60],atual['id']))
        else:
            c.execute('''INSERT INTO v9_vinculos(organizacao_id,usuario_id,papel,situacao,criado_em,unidade,funcao_declarada)
                         VALUES(?,?,?,'Pendente',?,?,?)''',
                      (org_id,usuario_id,papel,ext.agora(),str(unidade).strip()[:100],str(funcao).strip()[:60]))
        return 'Pendente'

def vincular(banco,usuario_id,org_id,papel):
    if papel not in PAPEIS:raise ValueError('Perfil inválido.')
    with ext.db(banco) as c:
        o=c.execute('SELECT id FROM v9_organizacoes WHERE id=? AND mesclado_em IS NULL',(org_id,)).fetchone()
        if not o:raise ValueError('Condomínio/empresa não encontrado.')
        c.execute('INSERT OR IGNORE INTO v9_vinculos(organizacao_id,usuario_id,papel,criado_em) VALUES(?,?,?,?)',
                  (org_id,usuario_id,papel,ext.agora()))

def vinculo_aprovado(banco,uid,org,papel=None):
    with ext.db(banco) as c:
        r=c.execute('SELECT papel FROM v9_vinculos WHERE usuario_id=? AND organizacao_id=? AND situacao=?',(uid,org,'Aprovado')).fetchone()
        return bool(r and (not papel or r['papel'] in papel))

def registrar_chamado(banco,uid,org,descricao,urgencia,unidade='',papel='',solicitante_nome=''):
    descricao=descricao.strip()
    if not 10<=len(descricao)<=2000:raise ValueError('Descreva o problema com 10 a 2.000 caracteres.')
    if urgencia not in ('Baixa','Normal','Alta'):raise ValueError('Urgência inválida.')
    papel=str(papel or '').strip()[:40]
    if papel and papel not in PAPEIS:raise ValueError('Papel inválido. Informe morador, funcionário, porteiro ou cargo equivalente.')
    unidade=str(unidade or '').strip()[:100]
    if not 1<=len(unidade):raise ValueError('Informe o apartamento ou o cargo/função do solicitante.')
    nome_sol=str(solicitante_nome or '').strip()[:120]
    with ext.db(banco) as c:
        x=c.execute('SELECT id FROM v9_organizacoes WHERE id=? AND mesclado_em IS NULL',(org,)).fetchone()
        if not x:raise ValueError('Condomínio ou empresa não encontrado.')
        # Acionamento pode ser feito por qualquer usuário com CPF e senha válidos,
        # mesmo quando ainda não foi aprovado como morador/síndico.
        c.execute('BEGIN IMMEDIATE')
        cur=c.execute('''INSERT INTO v9_chamados(organizacao_id,usuario_id,descricao,urgencia,unidade,papel,
                            solicitante_nome,criado_em) VALUES(?,?,?,?,?,?,?,?)''',
                      (org,uid,descricao,urgencia,unidade,papel,nome_sol,ext.agora()))
        evento(c,cur.lastrowid,'Solicitante','Chamado registrado',descricao[:200]+f' | {unidade} | {papel}'.rstrip(' |'))
        _criar_os_no_registro(c,cur.lastrowid,'Portal do Cliente')
        for si in c.execute("SELECT usuario_id FROM v9_vinculos WHERE organizacao_id=? AND situacao='Aprovado' AND papel IN ('Síndico','Administrador')",(org,)).fetchall():
            notificar(c,si['usuario_id'],cur.lastrowid,'Novo chamado recebido no condomínio; aguarda análise AUTOSEG.')
        return cur.lastrowid

def notificar(c,uid,chamado,msg):
    c.execute('INSERT INTO v9_notificacoes(usuario_id,chamado_id,texto,criado_em) VALUES(?,?,?,?)',
              (uid,chamado,msg[:400],ext.agora()))

def evento(c,chamado,ator,acao,descricao=''):
    c.execute('INSERT INTO v9_eventos(chamado_id,ator,acao,descricao,criado_em) VALUES(?,?,?,?,?)',
        (chamado,ator,acao,descricao[:500],ext.agora()))

def analisar(banco,chamado_id,administrador,decisao,observacao=''):
    if decisao not in ('Aguardando síndico','Recusado','Mais informações'):raise ValueError('Decisão inválida.')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        atual=c.execute('SELECT status FROM v9_chamados WHERE id=?',(chamado_id,)).fetchone()
        if not atual or atual['status'] not in ('Aguardando AUTOSEG','Mais informações'):
            raise ValueError('Chamado não está aguardando análise.')
        c.execute('UPDATE v9_chamados SET status=?,avaliado_em=?,avaliado_por=?,motivo=? WHERE id=?',
            (decisao,ext.agora(),administrador,observacao[:1500],chamado_id))
        evento(c,chamado_id,administrador,'Análise AUTOSEG',decisao+' '+observacao)
        uid=c.execute('SELECT usuario_id FROM v9_chamados WHERE id=?',(chamado_id,)).fetchone()['usuario_id']
        notificar(c,uid,chamado_id,'Situação do chamado atualizada: '+decisao)

def confirmar(banco,chamado_id,ator,aprovar,uid=None):
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        x=c.execute('SELECT * FROM v9_chamados WHERE id=?',(chamado_id,)).fetchone()
        if not x or x['status']!='Aguardando síndico':raise ValueError('Chamado não aguarda confirmação.')
        if uid is not None:
            v=c.execute("SELECT 1 FROM v9_vinculos WHERE organizacao_id=? AND usuario_id=? AND situacao='Aprovado' AND papel IN ('Síndico','Administrador')",(x['organizacao_id'],uid)).fetchone()
            if not v:raise PermissionError('Somente síndico autorizado pode confirmar.')
        status='Autorizado' if aprovar else 'Recusado'
        c.execute('UPDATE v9_chamados SET status=?,confirmado_em=?,confirmado_por=? WHERE id=?',
                 (status,ext.agora(),ator,chamado_id))
        evento(c,chamado_id,ator,'Confirmação do síndico',status)
        notificar(c,x['usuario_id'],chamado_id,'Confirmação do síndico: '+status)
        return status

def _criar_os_no_registro(c, chamado_id, ator):
    """Cria OS efetiva no ato do chamado; não concede autorização de execução."""
    from banco import proximo_numero_os
    import atendimento_os as aten
    ch=c.execute("""SELECT h.*,o.cliente_id,o.nome org_nome,o.tipo org_tipo,
                           o.cnpj org_cnpj,o.endereco org_endereco,o.cidade org_cidade,o.bairro org_bairro
                    FROM v9_chamados h JOIN v9_organizacoes o ON o.id=h.organizacao_id
                    WHERE h.id=?""",(chamado_id,)).fetchone()
    if not ch:raise ValueError('Solicitação inexistente.')
    if ch['os_id']:return ch['os_id']
    if ch['status'] in ('Recusado','Cancelado'):return None
    cid=ch['cliente_id']
    if cid is None:
        # Cliente provisório: NÃO equivale à validação do CNPJ nem à autorização.
        doc=ch['org_cnpj'] or ''
        row=c.execute("SELECT id FROM clientes WHERE documento=? AND documento<>'' AND tipo_pessoa='Jurídica' ORDER BY id LIMIT 1",(doc,)).fetchone() if doc else None
        if row:
            cid=row['id']
        else:
            cols={r['name'] for r in c.execute('PRAGMA table_info(clientes)')}
            attrs={'tipo_pessoa':'Jurídica','documento':doc,'nome':ch['org_nome'],
                   'endereco':ch['org_endereco'] or '', 'cidade':ch['org_cidade'] or '',
                   'bairro':ch['org_bairro'] or '', 'status':'Prospect',
                   'observacoes':'Cadastro provisório gerado por solicitação; verificar dados antes de executar.',
                   'criado_em':ext.agora()}
            keys=[k for k in attrs if k in cols]
            cid=c.execute('INSERT INTO clientes('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',
                          [attrs[k] for k in keys]).lastrowid
        c.execute('UPDATE v9_organizacoes SET cliente_id=? WHERE id=? AND cliente_id IS NULL',(cid,ch['organizacao_id']))
    numero=proximo_numero_os(c.cursor())
    cols={r['name'] for r in c.execute('PRAGMA table_info(ordens_servico)')}
    dados={'numero_os':numero,'cliente_id':cid,'data_abertura':ext.agora(),
           'descricao':ch['descricao'],'valor_mao_obra':0,'valor_materiais':0,'valor_total':0,
           'forma_pagamento':'PIX','status':'Pendente','origem':'Portal',
           'observacoes':f'Solicitação #{chamado_id} | Apartamento/cargo: {ch["unidade"] or "Não informado"} | Papel: {ch["papel"] or "Solicitante"} | Execução não autorizada',
           'tecnico':'','criado_em':ext.agora(),'urgencia':ch['urgencia']}
    keys=[k for k in dados if k in cols]
    oid=c.execute('INSERT INTO ordens_servico('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',
                  [dados[k] for k in keys]).lastrowid
    aten.registrar_solicitacao(c,oid,cid,ch['descricao'],dados['observacoes'],'Portal PJ')
    ext.evento(c,oid,'Solicitação recebida',f'Solicitação #{chamado_id}; análise e autorização de execução pendentes.',ator=ator)
    c.execute('UPDATE v9_chamados SET os_id=? WHERE id=?',(oid,chamado_id))
    evento(c,chamado_id,ator,'OS registrada',numero)
    return oid


def gerar_os(banco,chamado_id,ator):
    """Compatibilidade: idempotente, inclusive para chamados anteriores à correção."""
    import atendimento_os as aten
    aten.instalar(banco)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        return _criar_os_no_registro(c,chamado_id,ator)


def sincronizar_solicitacoes_pendentes(banco):
    """Recupera chamados históricos ativos que nunca viraram OS; sem duplicar."""
    import atendimento_os as aten
    aten.instalar(banco)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        ids=[r['id'] for r in c.execute("SELECT id FROM v9_chamados WHERE os_id IS NULL AND status NOT IN ('Recusado','Cancelado') ORDER BY id")]
        for identificador in ids:_criar_os_no_registro(c,identificador,'Migração AUTOSEG')
        return len(ids)


def cancelar_chamado(banco,chamado_id,ator,motivo):
    """Cancela antes de executar, preservando OS, chamado e auditoria."""
    motivo=str(motivo or '').strip()
    if len(motivo)<5:raise ValueError('Informe o motivo do cancelamento (mínimo de 5 caracteres).')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        ch=c.execute('SELECT * FROM v9_chamados WHERE id=?',(chamado_id,)).fetchone()
        if not ch:raise ValueError('Solicitação inexistente.')
        if ch['status'] in ('Cancelado','Recusado'):raise ValueError('Solicitação já cancelada/recusada.')
        if ch['os_id']:
            osat=c.execute('SELECT status FROM ordens_servico WHERE id=?',(ch['os_id'],)).fetchone()
            if not osat or osat['status'] not in ('Aberta','Pendente'):
                raise ValueError('A OS já começou seu encerramento; use o fluxo normal de finalização.')
            andam=c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='os_atendimentos'").fetchone()
            if andam:
                cols={r['name'] for r in c.execute('PRAGMA table_info(os_atendimentos)')}
                if 'iniciado_em' in cols and c.execute('SELECT 1 FROM os_atendimentos WHERE os_id=? AND iniciado_em IS NOT NULL',(ch['os_id'],)).fetchone():
                    raise ValueError('O atendimento já foi iniciado; utilize o encerramento normal da OS.')
            c.execute("UPDATE ordens_servico SET status='Cancelada',observacoes=COALESCE(observacoes,'')||? WHERE id=?",('\nCancelada antes da execução: '+motivo[:400],ch['os_id']))
            ext.evento(c,ch['os_id'],'Solicitação cancelada antes da execução',motivo[:400],ator=ator)
        c.execute("UPDATE v9_chamados SET status='Cancelado',motivo=?,avaliado_em=?,avaliado_por=? WHERE id=?",(motivo[:1500],ext.agora(),ator,chamado_id))
        evento(c,chamado_id,ator,'Cancelado',motivo)
        notificar(c,ch['usuario_id'],chamado_id,'Solicitação cancelada: '+motivo[:200])
        return ch['os_id']


def alterar_vinculo(banco,vinculo_id,aprovar,administrador):
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        v=c.execute('SELECT * FROM v9_vinculos WHERE id=?',(vinculo_id,)).fetchone()
        if not v:raise ValueError('Vínculo inexistente.')
        situacao='Aprovado' if aprovar else 'Recusado'
        c.execute('UPDATE v9_vinculos SET situacao=?,aprovado_em=? WHERE id=?',(situacao,ext.agora(),vinculo_id))
        c.execute('INSERT INTO v9_historico_clientes(cliente_id,origem_id,acao,descricao,autor,criado_em) VALUES(NULL,?,?,?,?,?)',
                  (v['organizacao_id'],'Vínculo '+situacao,'Vínculo '+str(vinculo_id),administrador,ext.agora()))

def validar_organizacao(banco,org_id,cliente_id,administrador):
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        x=c.execute('SELECT * FROM v9_organizacoes WHERE id=? AND mesclado_em IS NULL',(org_id,)).fetchone()
        cl=c.execute('SELECT id FROM clientes WHERE id=?',(cliente_id,)).fetchone()
        if not x or not cl:raise ValueError('Organização ou cliente inexistente.')
        if c.execute('SELECT 1 FROM v9_organizacoes WHERE cliente_id=? AND id!=? AND mesclado_em IS NULL',(cliente_id,org_id)).fetchone():
            raise ValueError('Este cliente já está associado a outra organização. Use mesclagem.')
        c.execute("UPDATE v9_organizacoes SET cliente_id=?,situacao='Validado' WHERE id=?",(cliente_id,org_id))
        c.execute('INSERT INTO v9_historico_clientes(cliente_id,origem_id,acao,descricao,autor,criado_em) VALUES(?,?,?,?,?,?)',
                  (cliente_id,org_id,'Organização validada',x['nome'],administrador,ext.agora()))

def mesclar_organizacoes(banco,origem,destino,autor):
    if origem==destino:raise ValueError('Escolha organizações diferentes.')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        a=c.execute('SELECT * FROM v9_organizacoes WHERE id=? AND mesclado_em IS NULL',(origem,)).fetchone()
        b=c.execute('SELECT * FROM v9_organizacoes WHERE id=? AND mesclado_em IS NULL',(destino,)).fetchone()
        if not a or not b:raise ValueError('Organização inexistente ou já mesclada.')
        if a['cnpj'] and b['cnpj'] and a['cnpj']!=b['cnpj']:
            raise ValueError('CNPJs distintos: revisão manual obrigatória; mesclagem bloqueada.')
        if a['cliente_id'] and b['cliente_id'] and a['cliente_id']!=b['cliente_id']:
            raise ValueError('Clientes históricos distintos: revisar OS antes da fusão.')
        if not b['cliente_id'] and a['cliente_id']:
            c.execute("UPDATE v9_organizacoes SET cliente_id=?,situacao='Validado' WHERE id=?",(a['cliente_id'],destino))
        if not b['cnpj'] and a['cnpj']:
            c.execute('UPDATE v9_organizacoes SET cnpj=? WHERE id=?',(a['cnpj'],destino))
        c.execute('UPDATE v9_chamados SET organizacao_id=? WHERE organizacao_id=?',(destino,origem))
        for v in c.execute('SELECT * FROM v9_vinculos WHERE organizacao_id=?',(origem,)).fetchall():
            if not c.execute('SELECT 1 FROM v9_vinculos WHERE organizacao_id=? AND usuario_id=?',(destino,v['usuario_id'])).fetchone():
                c.execute('UPDATE v9_vinculos SET organizacao_id=? WHERE id=?',(destino,v['id']))
            else:c.execute('DELETE FROM v9_vinculos WHERE id=?',(v['id'],))
        c.execute('UPDATE v9_organizacoes SET situacao=?,mesclado_em=?,cnpj=NULL WHERE id=?',('Mesclado',destino,origem))
        c.execute('INSERT INTO v9_historico_clientes(cliente_id,origem_id,acao,descricao,autor,criado_em) VALUES(?,?,?,?,?,?)',
                  (b['cliente_id'],origem,'Mesclagem',f'{origem} -> {destino}',autor,ext.agora()))
        return destino

def desativar_cliente(banco,cliente_id,autor):
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        cl=c.execute('SELECT nome FROM clientes WHERE id=?',(cliente_id,)).fetchone()
        if not cl:raise ValueError('Cliente não encontrado.')
        c.execute("UPDATE clientes SET status='Inativo' WHERE id=?",(cliente_id,))
        c.execute('INSERT INTO v9_historico_clientes(cliente_id,origem_id,acao,descricao,autor,criado_em) VALUES(?,?,?,?,?,?)',
                  (cliente_id,None,'Desativação',cl['nome'],autor,ext.agora()))

def salvar_detalhes(banco,os_id,diagnostico,execucao,resultado):
    with ext.db(banco) as c:
        c.execute('''INSERT INTO v9_detalhes_os(os_id,diagnostico,execucao,resultado,alterado_em)
                    VALUES(?,?,?,?,?) ON CONFLICT(os_id) DO UPDATE SET
                    diagnostico=excluded.diagnostico,execucao=excluded.execucao,
                    resultado=excluded.resultado,alterado_em=excluded.alterado_em''',
                  (os_id,diagnostico[:5000],execucao[:5000],resultado[:5000],ext.agora()))

def aprovar_anexo(banco,anexo_id,visivel,legenda,ator):
    with ext.db(banco) as c:
        a=c.execute('SELECT os_id FROM os_anexos WHERE id=?',(anexo_id,)).fetchone()
        if not a:raise ValueError('Anexo não encontrado.')
        c.execute('''INSERT INTO v9_anexos_visiveis(anexo_id,visivel,legenda,autorizado_em)
                     VALUES(?,?,?,?) ON CONFLICT(anexo_id) DO UPDATE SET
                     visivel=excluded.visivel,legenda=excluded.legenda,autorizado_em=excluded.autorizado_em''',
                  (anexo_id,int(visivel),legenda[:160],ext.agora()))
        ext.evento(c,a['os_id'],'Evidência para o cliente',('Aprovada' if visivel else 'Ocultada')+' por '+ator)


def prestador_admin(banco,pid):
    with ext.db(banco) as c:
        return bool(c.execute('SELECT 1 FROM v9_admin_prestadores WHERE prestador_id=?',(pid,)).fetchone())

def definir_admin(banco,pid,ativo):
    with ext.db(banco) as c:
        row=c.execute('SELECT id FROM prestadores WHERE id=?',(pid,)).fetchone()
        if not row:raise ValueError('Prestador inexistente.')
        if ativo:
            c.execute('INSERT OR REPLACE INTO v9_admin_prestadores(prestador_id,autorizado_em) VALUES(?,?)',(pid,ext.agora()))
        else:c.execute('DELETE FROM v9_admin_prestadores WHERE prestador_id=?',(pid,))


WHATSAPP_AUTOSEG = '5551992692007'

TIPOS_WHATSAPP = {'particular':'PARTICULAR','condominio':'CONDOMÍNIO','condomínio':'CONDOMÍNIO','empresa':'EMPRESA'}


def url_whatsapp_cliente(protocolo, nome, tipo, organizacao=''):
    """Link pré-preenchido para o cliente avisar a AUTOSEG após a OS ser salva.

    O wa.me NÃO envia nada sozinho: o próprio cliente confirma o envio no WhatsApp.
    A mensagem nunca inclui CPF/CNPJ, senha ou endereço residencial.
    """
    from urllib.parse import quote
    tipo_txt = TIPOS_WHATSAPP.get(str(tipo or '').strip().lower(), str(tipo or 'PARTICULAR').upper())
    linhas = ['Olá, AUTOSEG! Acabei de abrir uma nova ordem de serviço pelo Portal do Cliente.',
              '',
              'Protocolo: ' + str(protocolo),
              'Solicitante: ' + str(nome or '').strip(),
              'Tipo: ' + tipo_txt]
    if organizacao:
        linhas.append('Organização: ' + str(organizacao).strip())
    linhas += ['', 'Gostaria de confirmar o recebimento da minha solicitação.']
    return 'https://wa.me/' + WHATSAPP_AUTOSEG + '?text=' + quote('\n'.join(linhas), safe='')


def contato_sindico(banco, organizacao_id):
    """Retorna contato validado do síndico; não utiliza telefone fornecido por usuário pendente."""
    with ext.db(banco) as c:
        o=c.execute('SELECT sindico_telefone,situacao FROM v9_organizacoes WHERE id=? AND mesclado_em IS NULL',(organizacao_id,)).fetchone()
        if not o:return WHATSAPP_AUTOSEG
        if o['situacao']=='Validado':
            n=digitos(o['sindico_telefone'])
            if len(n) in (10,11):return '55'+n
            if len(n) in (12,13) and n.startswith('55'):return n
        x=c.execute("""SELECT u.telefone FROM v9_vinculos v JOIN v9_usuarios u ON u.id=v.usuario_id
            WHERE v.organizacao_id=? AND v.situacao='Aprovado' AND v.papel IN ('Síndico','Administrador')
            AND u.ativo=1 ORDER BY v.id LIMIT 1""",(organizacao_id,)).fetchone()
        n=digitos(x['telefone']) if x else ''
        return '55'+n if len(n) in (10,11) else (n if n.startswith('55') and len(n) in (12,13) else WHATSAPP_AUTOSEG)

def url_whatsapp(banco, chamado_id, url_publica=''):
    """Gera link pré-preenchido. wa.me NÃO envia automaticamente a mensagem."""
    from urllib.parse import quote
    with ext.db(banco) as c:
        h=c.execute('SELECT h.id,h.organizacao_id,o.nome FROM v9_chamados h JOIN v9_organizacoes o ON o.id=h.organizacao_id WHERE h.id=?',(chamado_id,)).fetchone()
        if not h:raise ValueError('Chamado não encontrado.')
    contato=contato_sindico(banco,h['organizacao_id'])
    destino='síndico' if contato!=WHATSAPP_AUTOSEG else 'AUTOSEG (sem síndico validado)'
    msg=f'AUTOSEG — Foi aberta a solicitação #{h["id"]} para {h["nome"]}. Favor confirmar o recebimento e a necessidade de atendimento com a AUTOSEG.'
    if url_publica.startswith('https://'):
        msg+=' Acompanhe no portal: '+url_publica.rstrip('/')+'/pj/sindico?org='+str(h['organizacao_id'])
    return 'https://wa.me/'+contato+'?text='+quote(msg),destino

def atualizar_sindico(banco, organizacao_id, nome, telefone, ator):
    numero=digitos(telefone)
    if numero and len(numero) not in (10,11,12,13):raise ValueError('Telefone do síndico precisa ter DDD.')
    with ext.db(banco) as c:
        org=c.execute('SELECT id FROM v9_organizacoes WHERE id=? AND mesclado_em IS NULL',(organizacao_id,)).fetchone()
        if not org:raise ValueError('Organização não encontrada.')
        c.execute('UPDATE v9_organizacoes SET sindico_nome=?,sindico_telefone=? WHERE id=?',(str(nome).strip()[:120],numero,organizacao_id))
        c.execute('INSERT INTO v9_historico_clientes(cliente_id,origem_id,acao,descricao,autor,criado_em) VALUES(NULL,?,?,?,?,?)',
                  (organizacao_id,'Contato síndico atualizado','Contato validado pela AUTOSEG.',ator,ext.agora()))
