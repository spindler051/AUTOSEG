"""AUTOSEG v5 — ciclo de encerramento, credenciais do cliente e PDF publicado.

Os mesmos serviços são usados por Tkinter e portal web. Não altera nem remove
registros antigos. O histórico de eventos é append-only.
"""
import hashlib
import os
import secrets
import re
import shutil
import threading
from pathlib import Path

import prestadores_ext as ext

FIM = ('Concluída', 'Cancelada', 'Não realizada')
FIM_TODOS = FIM
LOCK_PDF = threading.RLock()


def instalar(banco):
    with ext.db(banco) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS os_encerramentos (
            os_id INTEGER PRIMARY KEY,
            situacao TEXT NOT NULL,
            motivo TEXT NOT NULL DEFAULT '',
            relatorio TEXT NOT NULL DEFAULT '',
            ator TEXT NOT NULL,
            prestador_id INTEGER,
            encerrado_em TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS os_documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            os_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            versao INTEGER NOT NULL,
            caminho TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            publicado_em TEXT NOT NULL,
            UNIQUE(os_id,tipo,versao)
        );
        CREATE INDEX IF NOT EXISTS idx_os_doc_ultimo ON os_documentos(os_id,tipo,versao);
        CREATE TABLE IF NOT EXISTS cliente_acessos (
            cliente_id INTEGER PRIMARY KEY,
            senha_hash TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1,
            alterado_em TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS os_entregas (
            os_id INTEGER PRIMARY KEY,
            documento_id INTEGER,
            destinatario TEXT NOT NULL DEFAULT '',
            email_status TEXT NOT NULL DEFAULT 'aguardando_api',
            nf_status TEXT NOT NULL DEFAULT 'aguardando_api',
            atualizado_em TEXT NOT NULL
        );
        ''')


def definir_senha_cliente(banco,cliente_id,senha=None):
    """Usar somente do desktop. Retorna a senha uma ÚNICA vez."""
    senha = senha or secrets.token_urlsafe(16)
    if len(senha)<10:raise ValueError('A senha deve ter pelo menos 10 caracteres.')
    with ext.db(banco) as c:
        cliente=c.execute("SELECT id FROM clientes WHERE id=? AND status!='Inativo'",(cliente_id,)).fetchone()
        if not cliente: raise ValueError('Cliente inexistente ou inativo.')
        h=ext.senha_hash(senha)
        c.execute('''INSERT INTO cliente_acessos(cliente_id,senha_hash,ativo,alterado_em)
                 VALUES(?,?,1,?) ON CONFLICT(cliente_id) DO UPDATE SET
                 senha_hash=excluded.senha_hash,ativo=1,alterado_em=excluded.alterado_em''',
                 (cliente_id,h,ext.agora()))
    return senha


def revogar_cliente(banco,cliente_id):
    with ext.db(banco) as c:
        c.execute('UPDATE cliente_acessos SET ativo=0,alterado_em=? WHERE cliente_id=?',(ext.agora(),cliente_id))


def autenticar_cliente(banco,cliente_id,senha):
    try:cid=int(cliente_id)
    except (ValueError,TypeError): return None
    with ext.db(banco) as c:
        r=c.execute('''SELECT c.id,c.nome FROM clientes c JOIN cliente_acessos a
            ON a.cliente_id=c.id WHERE c.id=? AND a.ativo=1 AND c.status!='Inativo' ''',(cid,)).fetchone()
        a=c.execute('SELECT senha_hash FROM cliente_acessos WHERE cliente_id=? AND ativo=1',(cid,)).fetchone()
        if r and a and ext.verificar_senha(senha,a['senha_hash']):return dict(r)
    return None


def aplicar_encerramento(c, os_id, status, relato, motivo='', prestador_id=None, ator='Administrador'):
    """Parte transacional do encerramento: chamada dentro de BEGIN IMMEDIATE.
    Nunca confirma PIX automaticamente e não cria cobrança para cancelamentos.
    """
    if status not in FIM: raise ValueError('Situação final inválida.')
    relato=(relato or '').strip()
    motivo=(motivo or '').strip()
    if not relato: raise ValueError('O relatório técnico é obrigatório.')
    if status != 'Concluída' and not motivo:
        raise ValueError('Informe o motivo do cancelamento ou não realização.')
    if len(relato)>5000 or len(motivo)>2000:
        raise ValueError('Relatório ou motivo excedeu o tamanho permitido.')
    o=c.execute('SELECT * FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
    if not o or o['status'] not in ext.ATIVAS:
        raise ValueError('Esta OS não está aberta ou pendente.')
    # Condição evita duplo fechamento em edições concorrentes.
    mod=c.execute('''UPDATE ordens_servico SET status=?,data_conclusao=?,atualizado_em=?
        WHERE id=? AND status IN ('Aberta','Pendente')''',
        (status,ext.agora(),ext.agora(),os_id))
    if mod.rowcount!=1: raise ValueError('A OS já foi encerrada por outro usuário.')
    c.execute('''INSERT INTO os_encerramentos(os_id,situacao,motivo,relatorio,ator,prestador_id,encerrado_em)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(os_id) DO UPDATE SET
        situacao=excluded.situacao,motivo=excluded.motivo,relatorio=excluded.relatorio,
        ator=excluded.ator,prestador_id=excluded.prestador_id,encerrado_em=excluded.encerrado_em''',
        (os_id,status,motivo,relato,ator,prestador_id,ext.agora()))
    ext.evento(c,os_id,'Encerramento: '+status,
              (('Motivo: '+motivo+' | ') if motivo else '')+'Relatório: '+relato,
              prestador_id,ator)
    if status=='Concluída':
        f=c.execute('SELECT id,status FROM financeiro WHERE os_id=? ORDER BY id DESC LIMIT 1',(os_id,)).fetchone()
        titulo=f'OS {o["numero_os"]} - {(o["descricao"] or "Serviço")[:140]}'
        if f:
            if f['status']!='Recebido':
                c.execute('''UPDATE financeiro SET cliente_id=?,descricao=?,valor=?,forma_pagamento=?,
                    status='Aguardando pagamento',data_lancamento=? WHERE id=?''',
                    (o['cliente_id'],titulo,o['valor_total'],o['forma_pagamento'],ext.agora()[:10],f['id']))
        else:
            c.execute('''INSERT INTO financeiro(os_id,cliente_id,descricao,valor,forma_pagamento,status,data_lancamento)
                VALUES(?,?,?,?,?,'Aguardando pagamento',?)''',
                (os_id,o['cliente_id'],titulo,o['valor_total'],o['forma_pagamento'],ext.agora()[:10]))
        c.execute('UPDATE os_conclusoes SET aprovado_em=? WHERE os_id=?',(ext.agora(),os_id))
    else:
        # Não apaga financeiro anterior; impede fingir que dívida foi cancelada.
        pendente=c.execute("SELECT 1 FROM financeiro WHERE os_id=? AND status='Aguardando pagamento'",(os_id,)).fetchone()
        if pendente:
            ext.evento(c,os_id,'Financeiro exige revisão',
                      'OS encerrada sem execução concluída, mas existe lançamento aguardando pagamento.',
                      prestador_id,ator)
    return status


def encerrar_desktop(banco,os_id,status,relato,motivo):
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        aplicar_encerramento(c,os_id,status,relato,motivo,ator='Administrador desktop')
    return publicar_relatorio(banco,os_id)


def recuperar_relatorios_antigos(banco, os_id=None):
    """Importa PDFs antigos já gerados, sem alterar a OS ou o documento original.

    Aceita somente o padrão histórico OS_<numero_os>_<id>.pdf e exige
    correspondência exata com a OS concluída/cancelada. Cópia imutável,
    registro sha256 e versionamento em os_documentos.
    """
    instalar(banco)
    encontrados=[]
    raiz=ext.RELATORIOS
    publicados=raiz/'publicados'
    publicados.mkdir(parents=True,exist_ok=True)
    with LOCK_PDF:
        with ext.db(banco) as c:
            sql="SELECT id,numero_os,status FROM ordens_servico WHERE status IN ('Concluída','Cancelada','Não realizada')"
            params=()
            if os_id is not None:
                sql+=' AND id=?'; params=(int(os_id),)
            registros=c.execute(sql,params).fetchall()
            for o in registros:
                anterior=c.execute("SELECT 1 FROM os_documentos WHERE os_id=? AND tipo='relatorio_pdf' LIMIT 1",(o['id'],)).fetchone()
                if anterior:continue
                # Formato que gerar_pdf produz nas versões anteriores.
                nome_limpo=re.sub(r'[^a-zA-Z0-9_-]','_',str(o['numero_os']))
                origem=raiz/f'OS_{nome_limpo}_{o["id"]}.pdf'
                if not origem.is_file() or origem.is_symlink():continue
                if origem.stat().st_size<100:continue
                with origem.open('rb') as arq:
                    if arq.read(5)!=b'%PDF-':continue
                destino=publicados/f'OS_{o["id"]}_relatorio_v1.pdf'
                if destino.exists():
                    # Não substitui um documento órfão; exige intervenção manual.
                    continue
                temp=publicados/f'.recuperar_{secrets.token_hex(12)}.tmp'
                try:
                    shutil.copyfile(origem,temp)
                    os.replace(temp,destino)
                    sha=hashlib.sha256(destino.read_bytes()).hexdigest()
                    c.execute("INSERT INTO os_documentos(os_id,tipo,versao,caminho,sha256,publicado_em) VALUES(?,?,?,?,?,?)",(o['id'],'relatorio_pdf',1,str(destino),sha,ext.agora()))
                    encontrados.append(str(destino))
                finally:
                    temp.unlink(missing_ok=True)
    return encontrados


def ultimo_documento(banco,os_id):
    with ext.db(banco) as c:
        r=c.execute('''SELECT * FROM os_documentos WHERE os_id=? AND tipo='relatorio_pdf'
            ORDER BY versao DESC LIMIT 1''',(os_id,)).fetchone()
        return dict(r) if r else None


def publicar_relatorio(banco,os_id):
    """Cria uma cópia imutável do PDF que será servida ao cliente e prestador.
    Invocar depois de commit do status. Se falhar, OS permanece encerrada e
    administrador pode republicar sem modificar status.
    """
    instalar(banco)
    with LOCK_PDF:
        with ext.db(banco) as c:
            o=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
            if not o or o['status'] not in FIM:
                raise ValueError('O relatório só é publicado após um encerramento final.')
            proximo=c.execute("SELECT COALESCE(MAX(versao),0)+1 FROM os_documentos WHERE os_id=? AND tipo='relatorio_pdf'",(os_id,)).fetchone()[0]
        arq=Path(ext.gerar_pdf(banco,os_id))
        if not arq.is_file() or arq.stat().st_size<100: raise ValueError('PDF não foi gerado corretamente.')
        pasta=ext.RELATORIOS/'publicados';pasta.mkdir(parents=True,exist_ok=True)
        destino=pasta/f'OS_{os_id}_relatorio_v{proximo}.pdf'
        temp=pasta/f'.{secrets.token_hex(12)}.tmp'
        try:
            shutil.copyfile(arq,temp)
            os.replace(temp,destino)
            sha=hashlib.sha256(destino.read_bytes()).hexdigest()
            with ext.db(banco) as c:
                cur=c.execute('INSERT INTO os_documentos(os_id,tipo,versao,caminho,sha256,publicado_em) VALUES(?,?,?,?,?,?)',
                          (os_id,'relatorio_pdf',proximo,str(destino),sha,ext.agora()))
                cliente=c.execute('SELECT cl.email,o.status FROM clientes cl JOIN ordens_servico o ON o.cliente_id=cl.id WHERE o.id=?',(os_id,)).fetchone()
                email=(cliente['email'] or '').strip() if cliente else ''
                c.execute('''INSERT INTO os_entregas(os_id,documento_id,destinatario,email_status,nf_status,atualizado_em)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(os_id) DO UPDATE SET
                    documento_id=excluded.documento_id,destinatario=excluded.destinatario,
                    email_status=excluded.email_status,nf_status=excluded.nf_status,atualizado_em=excluded.atualizado_em''',
                    (os_id,cur.lastrowid,email,'aguardando_api' if email else 'email_nao_cadastrado',
                     'aguardando_api' if cliente and cliente['status']=='Concluída' else 'nao_aplicavel',ext.agora()))
            return str(destino)
        finally:
            temp.unlink(missing_ok=True)


def validar_pdf_publicado(documento):
    """Serve somente o arquivo publicado, verificando caminho, integridade e PDF."""
    from pathlib import Path
    arq=Path(documento['caminho']).resolve()
    raiz=(ext.RELATORIOS/'publicados').resolve()
    if not arq.is_relative_to(raiz) or not arq.is_file():
        raise ValueError('PDF publicado não encontrado no servidor. Republicar pelo Histórico e Relatórios.')
    if arq.stat().st_size<100 or arq.read_bytes()[:5]!=b'%PDF-':
        raise ValueError('Arquivo publicado não é um PDF válido. Republicar o relatório.')
    if hashlib.sha256(arq.read_bytes()).hexdigest()!=documento['sha256']:
        raise ValueError('Integridade do PDF divergente. Republicar o relatório.')
    return str(arq)
