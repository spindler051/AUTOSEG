"""Extensões AUTOSEG: prestadores, auditoria, anexos, PDF, e-mail e rascunho fiscal.
Não modifica o esquema antigo; adiciona tabelas independentes ao mesmo banco SQLite.
"""
import os, sqlite3, hashlib, hmac, secrets, json, mimetypes, shutil, re
from datetime import datetime
from pathlib import Path
from email.message import EmailMessage
from email.policy import SMTP
from contextlib import contextmanager

BASE = Path(os.environ.get('AUTOSEG_BASE') or Path(__file__).resolve().parent)
ANEXOS = BASE / 'anexos_os'
RELATORIOS = BASE / 'relatorios_pdf'
RASCUNHOS = BASE / 'rascunhos'
NOTAS = BASE / 'notas_fiscais'
for p in (ANEXOS, RELATORIOS, RASCUNHOS):
    try: p.mkdir(parents=True, exist_ok=True)
    except OSError: pass

def agora(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def nome_icone():
    """Nome do ícone do aplicativo: DEV usa icone_devel.png; MAIN usa icone.png."""
    return 'icone_devel.png' if os.environ.get('AUTOSEG_DEV') == '1' else 'icone.png'


def caminho_icone(diretorio):
    """Caminho do ícone disponível em `diretorio`, com fallback para o outro nome."""
    diretorio = Path(diretorio)
    preferido = diretorio / nome_icone()
    if preferido.is_file():
        return preferido
    alternativo = diretorio / ('icone.png' if nome_icone() == 'icone_devel.png' else 'icone_devel.png')
    return alternativo if alternativo.is_file() else None


@contextmanager
def db(banco):
    """Commit ou rollback da transação e SEMPRE fecha a conexão SQLite."""
    c = sqlite3.connect(str(banco), timeout=20)
    c.row_factory = sqlite3.Row
    try:
        c.execute('PRAGMA busy_timeout=20000')
        c.execute('PRAGMA foreign_keys=ON')
        with c:
            yield c
    finally:
        c.close()

def instalar(banco):
    with db(banco) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS prestadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
            telefone TEXT DEFAULT '', email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            documento TEXT DEFAULT '', especialidade TEXT DEFAULT '',
            senha_hash TEXT NOT NULL, ativo INTEGER NOT NULL DEFAULT 1,
            criado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS os_prestadores (
            os_id INTEGER NOT NULL, prestador_id INTEGER NOT NULL,
            atribuido_em TEXT NOT NULL, ativo INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(os_id,prestador_id),
            FOREIGN KEY(prestador_id) REFERENCES prestadores(id));
        CREATE TABLE IF NOT EXISTS os_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, os_id INTEGER NOT NULL,
            prestador_id INTEGER, ator TEXT NOT NULL, acao TEXT NOT NULL,
            descricao TEXT NOT NULL, criado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS os_anexos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, os_id INTEGER NOT NULL,
            prestador_id INTEGER, nome_original TEXT NOT NULL, caminho TEXT NOT NULL,
            tipo TEXT NOT NULL, criado_em TEXT NOT NULL,
            ordem INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS os_conclusoes (
            os_id INTEGER PRIMARY KEY, prestador_id INTEGER NOT NULL,
            relato TEXT NOT NULL, informado_em TEXT NOT NULL, aprovado_em TEXT);
        CREATE TABLE IF NOT EXISTS os_responsaveis (
            os_id INTEGER PRIMARY KEY, prestador_id INTEGER NOT NULL,
            assumido_em TEXT NOT NULL,
            FOREIGN KEY(prestador_id) REFERENCES prestadores(id));
        CREATE TABLE IF NOT EXISTS os_deslocamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            os_id INTEGER NOT NULL,
            prestador_id INTEGER NOT NULL,
            em_rota_em TEXT NOT NULL,
            finalizado_em TEXT,
            ator TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS os_rascunhos_web (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            os_id INTEGER NOT NULL,
            prestador_id INTEGER,
            dados_json TEXT NOT NULL,
            atualizado_em TEXT NOT NULL,
            UNIQUE(os_id, prestador_id)
        );
        CREATE TABLE IF NOT EXISTS os_leituras (
            os_id INTEGER NOT NULL,
            prestador_id INTEGER NOT NULL,
            lido_em TEXT NOT NULL,
            PRIMARY KEY(os_id, prestador_id)
        );
        CREATE INDEX IF NOT EXISTS idx_os_prestadores_prestador ON os_prestadores(prestador_id,os_id);
        CREATE INDEX IF NOT EXISTS idx_os_responsaveis_prestador ON os_responsaveis(prestador_id);
        CREATE INDEX IF NOT EXISTS idx_eventos_os ON os_eventos(os_id,id);
        CREATE INDEX IF NOT EXISTS idx_anexos_os ON os_anexos(os_id);
        CREATE TABLE IF NOT EXISTS prestadores_config (
            prestador_id INTEGER PRIMARY KEY,
            provedor_email TEXT DEFAULT '',
            email_remetente TEXT DEFAULT '',
            credencial_env TEXT DEFAULT '',
            banco_nome TEXT DEFAULT '',
            banco_titular TEXT DEFAULT '',
            banco_agencia TEXT DEFAULT '',
            banco_conta TEXT DEFAULT '',
            chave_pix TEXT DEFAULT '',
            dados_bancarios_texto TEXT NOT NULL DEFAULT '',
            atualizado_em TEXT NOT NULL,
            FOREIGN KEY(prestador_id) REFERENCES prestadores(id));
        ''')
        # REV05: dados bancários/cadastrais em bloco livre por prestador.
        col_conf={r[1] for r in c.execute('PRAGMA table_info(prestadores_config)').fetchall()}
        if 'dados_bancarios_texto' not in col_conf:
            c.execute("ALTER TABLE prestadores_config ADD COLUMN dados_bancarios_texto TEXT NOT NULL DEFAULT ''")
        # REV12: custo real dos materiais é interno e não entra no valor cobrado.
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ordens_servico'").fetchone():
            colunas_os={r[1] for r in c.execute('PRAGMA table_info(ordens_servico)').fetchall()}
            if 'custo_materiais' not in colunas_os:
                c.execute('ALTER TABLE ordens_servico ADD COLUMN custo_materiais REAL DEFAULT 0')
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='materiais_os'").fetchone():
            colunas_mat={r[1] for r in c.execute('PRAGMA table_info(materiais_os)').fetchall()}
            if 'unidade' not in colunas_mat:
                c.execute("ALTER TABLE materiais_os ADD COLUMN unidade TEXT NOT NULL DEFAULT ''")
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ordens_servico'").fetchone():
            colunas_os={r[1] for r in c.execute('PRAGMA table_info(ordens_servico)').fetchall()}
            if 'base_percentuais' not in colunas_os:
                c.execute("ALTER TABLE ordens_servico ADD COLUMN base_percentuais TEXT NOT NULL DEFAULT 'total'")
            if 'arquivada' not in colunas_os:
                c.execute("ALTER TABLE ordens_servico ADD COLUMN arquivada INTEGER NOT NULL DEFAULT 0")
            if 'comprimir_fotos_pdf' not in colunas_os:
                c.execute("ALTER TABLE ordens_servico ADD COLUMN comprimir_fotos_pdf INTEGER NOT NULL DEFAULT 1")
        # REV05: exclusão lógica com preservação dos vínculos históricos.
        colunas={r[1] for r in c.execute('PRAGMA table_info(prestadores)').fetchall()}
        if 'excluido' not in colunas:
            c.execute('ALTER TABLE prestadores ADD COLUMN excluido INTEGER NOT NULL DEFAULT 0')
        # REV10: chave estável e hash para não duplicar fotos ao salvar rascunho.
        col_anexos={r[1] for r in c.execute('PRAGMA table_info(os_anexos)').fetchall()}
        if 'chave' not in col_anexos:
            c.execute('ALTER TABLE os_anexos ADD COLUMN chave TEXT')
        if 'sha256' not in col_anexos:
            c.execute('ALTER TABLE os_anexos ADD COLUMN sha256 TEXT')
        if 'ordem' not in col_anexos:
            c.execute('ALTER TABLE os_anexos ADD COLUMN ordem INTEGER NOT NULL DEFAULT 0')
        c.execute('UPDATE os_anexos SET ordem=id WHERE ordem=0')
        c.execute('CREATE INDEX IF NOT EXISTS idx_anexos_os_chave ON os_anexos(os_id,chave)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_anexos_os_sha ON os_anexos(os_id,sha256)')
        c.execute('''CREATE TABLE IF NOT EXISTS v9_anexos_visiveis(
            anexo_id INTEGER PRIMARY KEY, visivel INTEGER NOT NULL DEFAULT 0,
            legenda TEXT DEFAULT '', autorizado_em TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS os_notas_fiscais(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            os_id INTEGER NOT NULL,
            prestador_id INTEGER,
            nome_original TEXT NOT NULL,
            caminho TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            UNIQUE(os_id,sha256))''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_notas_os ON os_notas_fiscais(os_id,id)')
        # Migração sem alterações destrutivas: atribuições antigas continuam disponíveis.
        # Escolhe a mais recente somente onde ainda não existe responsável atual.
        c.execute('''INSERT OR IGNORE INTO os_responsaveis(os_id, prestador_id, assumido_em)
                     SELECT op.os_id, op.prestador_id, op.atribuido_em
                     FROM os_prestadores op
                     JOIN ordens_servico o ON o.id=op.os_id
                     WHERE op.ativo=1 AND o.status IN ('Aberta','Iniciada','Pendente')
                       AND op.rowid = (SELECT op2.rowid FROM os_prestadores op2
                                       WHERE op2.os_id=op.os_id AND op2.ativo=1
                                       ORDER BY op2.atribuido_em DESC,op2.rowid DESC LIMIT 1)''')

def senha_hash(s):
    if len(s) < 10: raise ValueError('A senha precisa ter no mínimo 10 caracteres.')
    salt = secrets.token_bytes(16)
    dig = hashlib.pbkdf2_hmac('sha256', s.encode(), salt, 250000)
    return 'pbkdf2$250000$'+salt.hex()+'$'+dig.hex()

def verificar_senha(s, hash_):
    try:
        tag, loops, salt, digest = hash_.split('$')
        if tag != 'pbkdf2': return False
        esperado = hashlib.pbkdf2_hmac('sha256',s.encode(),bytes.fromhex(salt),int(loops))
        return hmac.compare_digest(esperado,bytes.fromhex(digest))
    except (ValueError, TypeError): return False

def cadastrar(banco,nome,email,senha,telefone='',documento='',especialidade=''):
    if not nome.strip() or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email.strip()):
        raise ValueError('Informe nome e e-mail válido.')
    if documento:
        import cadastros_v9 as cad
        documento=cad.validar_documento_auto(documento)
    with db(banco) as c:
        cur=c.execute('INSERT INTO prestadores(nome,email,senha_hash,telefone,documento,especialidade,criado_em) VALUES(?,?,?,?,?,?,?)',
        (nome.strip(),email.strip().lower(),senha_hash(senha),telefone.strip(),documento.strip(),especialidade.strip(),agora()))
        return cur.lastrowid

def definir_documento_prestador(banco, prestador_id, documento):
    """Atualiza o CNPJ do prestador. O mesmo CNPJ pode existir em vários prestadores."""
    import cadastros_v9 as cad
    doc = cad.validar_documento_auto(str(documento or '').strip())
    with db(banco) as c:
        if not c.execute('SELECT 1 FROM prestadores WHERE id=?', (int(prestador_id),)).fetchone():
            raise ValueError('Prestador não encontrado.')
        c.execute('UPDATE prestadores SET documento=? WHERE id=?', (doc, int(prestador_id)))
    return doc


def redefinir_senha_prestador_desktop(banco,prestador_id,nova_senha):
    """Somente uma ação administrativa local do desktop deve chamar esta função."""
    if len(nova_senha)<10:raise ValueError('A nova senha deve ter pelo menos dez caracteres.')
    with db(banco) as c:
        p=c.execute('SELECT id FROM prestadores WHERE id=?',(prestador_id,)).fetchone()
        if not p:raise ValueError('Prestador não encontrado.')
        c.execute('UPDATE prestadores SET senha_hash=? WHERE id=?',
                  (senha_hash(nova_senha),prestador_id))
    return True


def autenticar(banco,email,senha):
    with db(banco) as c:
        p=c.execute('SELECT * FROM prestadores WHERE email=? AND ativo=1',(email.strip().lower(),)).fetchone()
        if p and verificar_senha(senha,p['senha_hash']): return dict(p)
    return None

def evento(c,os_id,acao,descricao,prestador_id=None,ator='Administrador'):
    c.execute('INSERT INTO os_eventos(os_id,prestador_id,ator,acao,descricao,criado_em) VALUES(?,?,?,?,?,?)',
              (os_id,prestador_id,ator,acao,descricao,agora()))

ATIVAS = ('Aberta', 'Iniciada', 'Pendente')

def listar_os_compartilhadas(banco, ordem='status', pid=None):
    """Todas as OS ativas para todo prestador autenticado, atribuídas ou não.

    ``ordem`` is a whitelist key, never SQL from the caller. The default puts
    in-progress and pending OS above open ones.
    """
    ordens = {
        'status': (
            "CASE WHEN o.status='Iniciada' THEN 0 "
            "WHEN o.status='Pendente' THEN 1 ELSE 2 END, o.id DESC"),
        'data': 'o.data_abertura DESC, o.id DESC',
        'cliente': 'cl.nome COLLATE NOCASE ASC, o.id DESC',
        'os': 'o.numero_os COLLATE NOCASE ASC, o.id DESC',
        'alteracao': 'COALESCE(o.atualizado_em, o.data_abertura) DESC, o.id DESC',
        'abertura': 'l.lido_em DESC, o.id DESC',
    }
    clausula = ordens.get(str(ordem or ''), ordens['status'])
    with db(banco) as c:
        return [dict(x) for x in c.execute(f"""
            SELECT o.id, o.numero_os, o.status, o.descricao, o.data_abertura,
                   o.cliente_id, cl.nome AS cliente,
                   r.prestador_id AS responsavel_id,
                   p.nome AS responsavel,
                   (SELECT GROUP_CONCAT(nome, ', ') FROM (
                       SELECT DISTINCT p2.nome AS nome FROM os_prestadores op2
                       JOIN prestadores p2 ON p2.id=op2.prestador_id
                       WHERE op2.os_id=o.id AND op2.ativo=1 ORDER BY p2.nome
                   )) AS participantes
            FROM ordens_servico o
            JOIN clientes cl ON cl.id=o.cliente_id
            LEFT JOIN os_responsaveis r ON r.os_id=o.id
            LEFT JOIN prestadores p ON p.id=r.prestador_id
            LEFT JOIN os_leituras l ON l.os_id=o.id AND l.prestador_id=?
            WHERE o.status IN ('Aberta','Iniciada','Pendente')
              AND COALESCE(o.arquivada,0)=0
            ORDER BY {clausula}
        """, (int(pid or 0),)).fetchall()]

def responsavel_atual(c, os_id):
    x = c.execute('SELECT prestador_id FROM os_responsaveis WHERE os_id=?', (os_id,)).fetchone()
    return x['prestador_id'] if x else None

def pode_assumir(c,os_id,pid):
    """Somente OS ativa sem responsável pode ser assumida por outro prestador."""
    o=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
    p=c.execute('SELECT 1 FROM prestadores WHERE id=? AND ativo=1',(pid,)).fetchone()
    if not o or not p: return False
    return o['status'] in ATIVAS and responsavel_atual(c,os_id) is None

def atribuir(banco,os_id,prestador_id,ator='Administrador'):
    """Atribuição administrativa define responsável; preserva participantes históricos."""
    with db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        o=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
        p=c.execute('SELECT nome FROM prestadores WHERE id=? AND ativo=1',(prestador_id,)).fetchone()
        if not o or not p: raise ValueError('OS ou prestador ativo não encontrado.')
        if o['status'] not in ATIVAS: raise ValueError('Só é possível atribuir OS ativa.')
        anterior=responsavel_atual(c,os_id)
        if anterior==prestador_id: return False
        c.execute('INSERT INTO os_prestadores(os_id,prestador_id,atribuido_em,ativo) VALUES(?,?,?,1) '
                  'ON CONFLICT(os_id,prestador_id) DO UPDATE SET ativo=1', (os_id,prestador_id,agora()))
        c.execute('INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) VALUES(?,?,?) '
                  'ON CONFLICT(os_id) DO UPDATE SET prestador_id=excluded.prestador_id, assumido_em=excluded.assumido_em',
                  (os_id,prestador_id,agora()))
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='produtividade_deslocamentos'").fetchone():
            c.execute('DELETE FROM produtividade_deslocamentos WHERE os_id=?',(os_id,))
        evento(c,os_id,'Atribuição' if anterior is None else 'Transferência administrativa',
               f'Responsável atual: {p["nome"]}. Responsável anterior (ID): {anterior or "nenhum"}.',prestador_id,ator)
        return True

def assumir(banco,os_id,pid):
    """Assunção atômica de OS ativa desatribuída, sem iniciar execução."""
    with db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        p=c.execute('SELECT nome FROM prestadores WHERE id=? AND ativo=1',(pid,)).fetchone()
        o=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
        if not p or not o: raise PermissionError('Prestador ou OS inválida.')
        anterior=responsavel_atual(c,os_id)
        if anterior==pid:
            return False
        tem_admin=bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                 "AND name='v9_admin_prestadores'").fetchone())
        admin=bool(c.execute('SELECT 1 FROM v9_admin_prestadores WHERE prestador_id=?',
                             (pid,)).fetchone()) if tem_admin else False
        if not admin and not pode_assumir(c,os_id,pid):
            raise PermissionError('OS em atendimento por outro prestador. Aguarde ficar pendente ou solicite transferência.')
        c.execute('INSERT INTO os_prestadores(os_id,prestador_id,atribuido_em,ativo) VALUES(?,?,?,1) '
                  'ON CONFLICT(os_id,prestador_id) DO UPDATE SET ativo=1', (os_id,pid,agora()))
        c.execute('INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) VALUES(?,?,?) '
                  'ON CONFLICT(os_id) DO UPDATE SET prestador_id=excluded.prestador_id, assumido_em=excluded.assumido_em',
                  (os_id,pid,agora()))
        # Assumir é diferente de iniciar; a OS pendente permanece pendente.
        evento(c,os_id,'Retomada' if anterior is not None else 'Assunção',
               f'{p["nome"]} assumiu a OS. Responsável anterior (ID): {anterior or "nenhum"}.',pid,p['nome'])
        return True

def arquivar_os(banco,os_id,pid,ator=None,motivo=''):
    """Arquiva uma OS ativa sem apagar dados; admin only, com evento."""
    with db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        if pid is None or not c.execute('SELECT 1 FROM v9_admin_prestadores WHERE prestador_id=?',(pid,)).fetchone():
            raise PermissionError('Somente administradores podem arquivar OS.')
        o=c.execute('SELECT numero_os,status,arquivada FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
        if not o:raise ValueError('OS não encontrada.')
        if o['arquivada']:return False
        motivo=str(motivo or '').strip()[:500]
        descricao='OS arquivada pelo administrador; histórico preservado.'
        if motivo:descricao+=' Motivo: '+motivo
        c.execute('UPDATE ordens_servico SET arquivada=1,atualizado_em=? WHERE id=?',(agora(),os_id))
        evento(c,os_id,'OS arquivada',descricao,pid,ator or 'Administrador')
        return True


def acesso(c,os_id,pid):
    """Legado: acesso operacional (mutação) apenas ao responsável atual."""
    return responsavel_atual(c,os_id)==pid

def registrar(banco,os_id,pid,acao,descricao):
    descricao=descricao.strip()
    if not descricao or len(descricao)>5000: raise ValueError('Informe descrição de até 5000 caracteres.')
    if acao not in ('Atividade','Pendência','Conclusão informada'): raise ValueError('Ação inválida.')
    with db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        o=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
        p=c.execute('SELECT nome FROM prestadores WHERE id=? AND ativo=1',(pid,)).fetchone()
        if not o or not p or not acesso(c,os_id,pid): raise PermissionError('Assuma a OS para registrar atividades.')
        if o['status'] not in ATIVAS: raise ValueError('OS não está ativa.')
        if acao=='Pendência': c.execute("UPDATE ordens_servico SET status='Pendente' WHERE id=?",(os_id,))
        if acao=='Conclusão informada':
            c.execute('INSERT INTO os_conclusoes(os_id,prestador_id,relato,informado_em,aprovado_em) VALUES(?,?,?,?,NULL) ON CONFLICT(os_id) DO UPDATE SET prestador_id=excluded.prestador_id,relato=excluded.relato,informado_em=excluded.informado_em,aprovado_em=NULL',(os_id,pid,descricao,agora()))
            c.execute("UPDATE ordens_servico SET status='Pendente' WHERE id=?",(os_id,))
        evento(c,os_id,acao,descricao,pid,p['nome'])

def validar_imagem(conteudo):
    """Validação antes de alterar o banco; evita fotos malformadas no PDF."""
    if not isinstance(conteudo,bytes) or not conteudo:
        raise ValueError('Selecione uma imagem válida.')
    if len(conteudo)>8*1024*1024:
        raise ValueError('Limite de 8 MB por imagem.')
    from PIL import Image
    import io
    try:
        with Image.open(io.BytesIO(conteudo)) as original:
            original.verify()
        with Image.open(io.BytesIO(conteudo)) as original:
            formato=original.format
            largura,altura=original.size
    except Exception as erro:
        raise ValueError('Não foi possível validar a imagem. Use JPG, PNG ou WEBP.') from erro
    if formato not in ('JPEG','PNG','WEBP') or largura*altura>25000000:
        raise ValueError('Use JPG, PNG ou WEBP de até 25 megapixels.')
    return formato, {'JPEG':'.jpg','PNG':'.png','WEBP':'.webp'}[formato]


def girar_imagem(banco, os_id, anexo_id, pid=None, ator='Prestador'):
    """Gira uma foto existente em 90° no sentido horário, sem duplicá-la."""
    from PIL import Image, ImageOps
    with db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        o=c.execute('SELECT status,arquivada FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
        if not o:raise ValueError('OS não existe.')
        if o['status'] not in ATIVAS:
            raise ValueError('OS encerrada: não é permitido girar fotos.')
        if 'arquivada' in o.keys() and o['arquivada']:
            raise ValueError('OS arquivada: edição bloqueada.')
        if pid is not None:
            p=c.execute('SELECT nome FROM prestadores WHERE id=? AND ativo=1',(pid,)).fetchone()
            if not p:raise PermissionError('Prestador inativo.')
        a=c.execute('SELECT caminho,nome_original FROM os_anexos WHERE id=? AND os_id=?',
                    (anexo_id,os_id)).fetchone()
        if not a:raise ValueError('Foto não encontrada.')
        caminho=Path(a['caminho'])
        if not caminho.is_file():raise ValueError('Arquivo da foto não encontrado.')
        temporario=caminho.with_name(caminho.name+'.girando')
        try:
            with Image.open(caminho) as original:
                formato=original.format or 'JPEG'
                imagem=ImageOps.exif_transpose(original)
                imagem=imagem.rotate(-90,expand=True)
                if formato=='JPEG':
                    imagem=imagem.convert('RGB')
                imagem.save(temporario,format=formato)
            os.replace(temporario,caminho)
        except Exception as erro:
            temporario.unlink(missing_ok=True)
            raise ValueError('Não foi possível girar a foto.') from erro
        digest=hashlib.sha256(caminho.read_bytes()).hexdigest()
        c.execute('UPDATE os_anexos SET sha256=? WHERE id=?',(digest,anexo_id))
        nome_ator=ator
        if pid is not None:
            p=c.execute('SELECT nome FROM prestadores WHERE id=?',(pid,)).fetchone()
            if p:nome_ator=p['nome']
        evento(c,os_id,'Foto girada',Path(a['nome_original']).name[:150],pid,nome_ator)
        return str(caminho)


def mover_anexo(banco, os_id, anexo_id, direcao, pid=None, ator='Prestador'):
    """Move uma foto uma posição para cima/baixo dentro da mesma OS."""
    direcao=str(direcao or '').strip().lower()
    if direcao not in ('up','down'):
        raise ValueError('Direção de ordenação inválida.')
    with db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        o=c.execute('SELECT status,arquivada FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
        if not o:raise ValueError('OS não existe.')
        if o['status'] not in ATIVAS:
            raise ValueError('OS encerrada: não é permitido reordenar fotos.')
        if 'arquivada' in o.keys() and o['arquivada']:
            raise ValueError('OS arquivada: edição bloqueada.')
        admin=bool(c.execute('SELECT 1 FROM v9_admin_prestadores WHERE prestador_id=?',(pid,)).fetchone()) if pid is not None else False
        if pid is not None and responsavel_atual(c,os_id)!=pid and not admin:
            raise PermissionError('Somente o responsável ou administrador edita fotos.')
        atual=c.execute('SELECT id,ordem,nome_original FROM os_anexos WHERE id=? AND os_id=?',
                        (anexo_id,os_id)).fetchone()
        if not atual:raise ValueError('Foto não encontrada.')
        if direcao=='up':
            vizinho=c.execute('''SELECT id,ordem FROM os_anexos WHERE os_id=?
                AND (ordem<? OR (ordem=? AND id<?)) ORDER BY ordem DESC,id DESC LIMIT 1''',
                (os_id,atual['ordem'],atual['ordem'],atual['id'])).fetchone()
        else:
            vizinho=c.execute('''SELECT id,ordem FROM os_anexos WHERE os_id=?
                AND (ordem>? OR (ordem=? AND id>?)) ORDER BY ordem,id LIMIT 1''',
                (os_id,atual['ordem'],atual['ordem'],atual['id'])).fetchone()
        if not vizinho:
            return False
        c.execute('UPDATE os_anexos SET ordem=? WHERE id=?',(vizinho['ordem'],atual['id']))
        c.execute('UPDATE os_anexos SET ordem=? WHERE id=?',(atual['ordem'],vizinho['id']))
        nome_ator=ator
        if pid is not None:
            p=c.execute('SELECT nome FROM prestadores WHERE id=?',(pid,)).fetchone()
            if p:nome_ator=p['nome']
        evento(c,os_id,'Foto reordenada',
               f'{Path(atual["nome_original"]).name[:150]} movida para {"cima" if direcao=="up" else "baixo"}.',
               pid,nome_ator)
        return True


def thumb_imagem(caminho):
    """Gera/retorna um JPEG pequeno para a listagem do portal."""
    from PIL import Image, ImageOps
    p=Path(caminho)
    if not p.is_file():
        raise ValueError('Arquivo da foto não encontrado.')
    chave=hashlib.sha256(f'{p.resolve()}:{p.stat().st_mtime_ns}:{p.stat().st_size}'.encode()).hexdigest()[:24]
    pasta=ANEXOS/'.thumbs'
    pasta.mkdir(parents=True,exist_ok=True)
    destino=pasta/f'{chave}.jpg'
    if not destino.is_file():
        with Image.open(p) as original:
            imagem=ImageOps.exif_transpose(original)
            imagem.thumbnail((560,560))
            imagem.convert('RGB').save(destino,'JPEG',quality=78,optimize=True)
    return destino.read_bytes()


def _legenda_normalizada(texto):
    return str(texto or '').strip()[:160]


def definir_legenda_anexo_c(c, os_id, anexo_id, legenda, visivel=1, ator='Prestador'):
    """Atualiza a legenda/visibilidade de uma foto existente na própria transação."""
    a=c.execute('SELECT os_id FROM os_anexos WHERE id=? AND os_id=?',(anexo_id,os_id)).fetchone()
    if not a:
        raise ValueError('Foto não pertence a esta OS.')
    c.execute('''INSERT INTO v9_anexos_visiveis(anexo_id,visivel,legenda,autorizado_em)
                 VALUES(?,?,?,?) ON CONFLICT(anexo_id) DO UPDATE SET
                 visivel=excluded.visivel,legenda=excluded.legenda,autorizado_em=excluded.autorizado_em''',
              (int(anexo_id),1 if visivel else 0,_legenda_normalizada(legenda),agora()))
    return True


def atualizar_legenda_anexo(banco, os_id, anexo_id, legenda, visivel=1, ator='Prestador'):
    with db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        return definir_legenda_anexo_c(c, os_id, anexo_id, legenda, visivel, ator)


def registrar_imagem_transacao(c,os_id,pid,nome,conteudo,permitir_colaboracao=False,
                               chave=None,legenda='',visivel=1):
    """Anexa ou atualiza uma foto sem duplicar; a legenda fica ligada à chave/hash."""
    formato,extensao=validar_imagem(conteudo)
    if pid is not None:
        prestador_ativo=c.execute('SELECT 1 FROM prestadores WHERE id=? AND ativo=1',(pid,)).fetchone()
        if not prestador_ativo: raise PermissionError('Prestador inativo.')
        if not permitir_colaboracao and not acesso(c,os_id,pid):
            raise PermissionError('Assuma a OS para anexar imagens.')
    o=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
    if not o:raise ValueError('OS não existe.')
    if pid is not None and o['status'] not in ATIVAS:
        raise ValueError('OS encerrada: não é permitido anexar novas fotos.')
    import hashlib
    digest=hashlib.sha256(conteudo).hexdigest()
    chave=str(chave or '').strip()[:80] or None
    existente=None
    if chave:
        existente=c.execute('SELECT id,caminho FROM os_anexos WHERE os_id=? AND chave=?',(os_id,chave)).fetchone()
    if not existente:
        existente=c.execute('SELECT id,caminho FROM os_anexos WHERE os_id=? AND sha256=? ORDER BY id LIMIT 1',
                            (os_id,digest)).fetchone()
    if existente:
        # Reenvio do mesmo arquivo: atualiza legenda e metadados, preservando o arquivo.
        c.execute('UPDATE os_anexos SET chave=COALESCE(chave,?),sha256=?,nome_original=? WHERE id=?',
                  (chave,digest,Path(nome).name[:150],existente['id']))
        definir_legenda_anexo_c(c,os_id,existente['id'],legenda,visivel)
        if chave:
            evento(c,os_id,'Legenda de foto atualizada',_legenda_normalizada(legenda) or 'Sem legenda',pid,
                   (c.execute('SELECT nome FROM prestadores WHERE id=?',(pid,)).fetchone()['nome'] if pid else 'Administrador'))
        return str(existente['caminho'])
    ANEXOS.mkdir(parents=True,exist_ok=True)
    destino=ANEXOS/(secrets.token_hex(16)+extensao)
    destino.write_bytes(conteudo)
    try:
        ordem=c.execute('SELECT COALESCE(MAX(ordem),0)+1 FROM os_anexos WHERE os_id=?',
                        (os_id,)).fetchone()[0]
        cur=c.execute('''INSERT INTO os_anexos(os_id,prestador_id,nome_original,caminho,tipo,criado_em,chave,sha256,ordem)
                         VALUES(?,?,?,?,?,?,?,?,?)''',
                  (os_id,pid,Path(nome).name[:150],str(destino),formato,agora(),chave,digest,ordem))
        definir_legenda_anexo_c(c,os_id,cur.lastrowid,legenda,visivel)
        ator='Administrador'
        if pid is not None:
            ator=c.execute('SELECT nome FROM prestadores WHERE id=?',(pid,)).fetchone()['nome']
        evento(c,os_id,'Imagem anexada',Path(nome).name[:150],pid,ator)
    except Exception:
        destino.unlink(missing_ok=True);raise
    return str(destino)


def salvar_imagem(banco,os_id,pid,nome,conteudo,permitir_colaboracao=False,
                  chave=None,legenda='',visivel=1):
    with db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        return registrar_imagem_transacao(c,os_id,pid,nome,conteudo,permitir_colaboracao,
                                          chave=chave,legenda=legenda,visivel=visivel)

def gerar_pdf(banco,os_id):
    from pdf_cliente_v9 import gerar
    return gerar(banco,os_id)

    try:
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image as RLImage,KeepTogether
        from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.utils import ImageReader
        from reportlab.lib.pagesizes import A4
    except ImportError as e:
        raise RuntimeError('ReportLab indisponível no Python ativo. Inicie pelo INICIAR_AUTOSEG.command após executar o instalador; verifique: .venv/bin/python -m pip install reportlab pillow') from e
    from xml.sax.saxutils import escape
    with db(banco) as c:
        o=c.execute('SELECT o.*,c.nome cliente_nome,c.email cliente_email FROM ordens_servico o JOIN clientes c ON c.id=o.cliente_id WHERE o.id=?',(os_id,)).fetchone()
        if not o: raise ValueError('OS não encontrada.')
        responsavel=c.execute('SELECT p.nome FROM os_responsaveis r JOIN prestadores p ON p.id=r.prestador_id WHERE r.os_id=?',(os_id,)).fetchone()
        participantes=c.execute('SELECT p.nome FROM os_prestadores op JOIN prestadores p ON p.id=op.prestador_id WHERE op.os_id=? ORDER BY p.nome',(os_id,)).fetchall()
        eventos=c.execute('SELECT criado_em,ator,acao,descricao FROM os_eventos WHERE os_id=? ORDER BY id',(os_id,)).fetchall()
        anexos=c.execute('SELECT caminho,nome_original FROM os_anexos WHERE os_id=? ORDER BY ordem,id',(os_id,)).fetchall()
        materiais=c.execute('SELECT item,quantidade,unidade,valor_total FROM materiais_os WHERE os_id=? ORDER BY id',(os_id,)).fetchall()
        financeiro=c.execute('SELECT status,valor FROM financeiro WHERE os_id=? ORDER BY id DESC LIMIT 1',(os_id,)).fetchone()
        tem_encerramento=c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='os_encerramentos'").fetchone()
        enc=c.execute('SELECT situacao,motivo,relatorio,encerrado_em FROM os_encerramentos WHERE os_id=?',(os_id,)).fetchone() if tem_encerramento else None
        sol=c.execute('SELECT descricao_original,criado_em FROM os_solicitacoes WHERE os_id=?',(os_id,)).fetchone() if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='os_solicitacoes'").fetchone() else None
        andamento=c.execute('SELECT iniciado_em,ator_inicio FROM os_atendimentos WHERE os_id=?',(os_id,)).fetchone() if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='os_atendimentos'").fetchone() else None
    nome=f'OS_{re.sub(r"[^a-zA-Z0-9_-]","_",str(o["numero_os"]))}_{os_id}.pdf'
    caminho=RELATORIOS/nome
    estilos=getSampleStyleSheet(); estilos.add(ParagraphStyle(name='AUTOTitulo',parent=estilos['Title'],textColor=colors.HexColor('#222222'),spaceAfter=15))
    estilos.add(ParagraphStyle(name='AUTOCorpo',parent=estilos['BodyText'],leading=15,spaceAfter=7))
    estilos.add(ParagraphStyle(name='AUTOSecao',parent=estilos['Heading2'],
        textColor=colors.HexColor('#997500'),fontSize=11,spaceBefore=15,spaceAfter=6))
    P=lambda x: Paragraph(escape(str(x or '')).replace('\n','<br/>'),estilos['AUTOCorpo'])
    H=lambda x: Paragraph(escape(str(x or '')),estilos['AUTOSecao'])
    brl=lambda v: 'R$ '+f'{float(v or 0):,.2f}'.replace(',','@').replace('.',',').replace('@','.')
    partes=[Paragraph('RELATÓRIO TÉCNICO DE SERVIÇO',estilos['AUTOTitulo']),P(f'OS: {o["numero_os"]} | Situação: {o["status"]}'),P(f'Cliente: {o["cliente_nome"]}'),P(f'Abertura: {o["data_abertura"]} | Conclusão: {o["data_conclusao"] or "Não informada"}'),P('Descrição: '+str(o['descricao'] or '')),P('Atendido por (cliente no local): '+str(o['tecnico'] or 'Não informado')),P('Observações: '+str(o['observacoes'] or '')),
        H('VALORES E PAGAMENTO'),P('Mão de obra: '+brl(o['valor_mao_obra'])),
        P('Materiais: '+brl(o['valor_materiais'])),
        P('Total: '+brl(o['valor_total'])),
        P('Forma de pagamento: '+str(o['forma_pagamento'] or 'Não informada')),
        P('Situação financeira: '+(financeiro['status'] if financeiro else 'Sem lançamento')),
        P('Responsável atual: '+(responsavel['nome'] if responsavel else 'Não atribuído')),P('Prestadores envolvidos: '+(', '.join(x['nome'] for x in participantes) or 'Nenhum prestador atribuído')),Spacer(1,12)]
    if sol:
        partes.extend([H('SOLICITAÇÃO ORIGINAL DO CLIENTE — NÃO EDITÁVEL'),P(sol['descricao_original']),P('Registrada em: '+str(sol['criado_em']))])
    if andamento and andamento['iniciado_em']:
        partes.append(P('Atendimento iniciado em: '+str(andamento['iniciado_em'])+' | Por: '+str(andamento['ator_inicio'])))
    if enc:
        partes.extend([H('ENCERRAMENTO'),P('Situação: '+enc['situacao']),
            P('Registrado em: '+str(enc['encerrado_em'])),
            P('Relatório técnico: '+str(enc['relatorio']))])
        if enc['motivo']: partes.append(P('Motivo do encerramento: '+enc['motivo']))
    partes.append(H('MATERIAIS UTILIZADOS'))
    for m in materiais:
        qtd=m['quantidade']; unidade=str(m['unidade'] or '').strip()
        quantidade=('—' + (' '+unidade if unidade else '')) if qtd is None else (
            f'{float(qtd):g}' + (' '+unidade if unidade else ' un.'))
        partes.append(P(f'{m["item"]}: {quantidade} | {brl(m["valor_total"])}'))
    partes.extend([Spacer(1,10),H('HISTÓRICO DE ATIVIDADES')])
    for ev in eventos: partes.append(P(f'{ev["criado_em"]} | {ev["ator"]} | {ev["acao"]}: {ev["descricao"]}'))
    partes.extend([Spacer(1,10),H('IMAGENS ANEXADAS')])
    for an in anexos:
        try:
            from PIL import Image as PILImage
            with PILImage.open(an['caminho']) as im: w,h=im.size
            scale=min(460/w,340/h,1)
            partes.append(KeepTogether([P(an['nome_original']),RLImage(an['caminho'],width=w*scale,height=h*scale),Spacer(1,8)]))
        except Exception: partes.append(P('Imagem indisponível: '+an['nome_original']))
    faixa=Table([[Paragraph('<font color="#FFFFFF"><b>AUTO</b></font><font color="#FFD400"><b>SEG</b></font>',
                   ParagraphStyle('LOGO_AUTO',fontName='Helvetica-Bold',fontSize=17,leading=20)),
                Paragraph('<font color="#FFD400">AUTOMAÇÃO E SEGURANÇA</font>',
                   ParagraphStyle('TAG_AUTO',fontName='Helvetica-Bold',fontSize=9,alignment=2))]],
               colWidths=[225,286])
    faixa.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#111111')),
        ('TOPPADDING',(0,0),(-1,-1),13),('BOTTOMPADDING',(0,0),(-1,-1),13),
        ('LEFTPADDING',(0,0),(0,0),15),('RIGHTPADDING',(-1,0),(-1,0),15)]))
    partes.insert(0,faixa)
    partes.insert(1,Spacer(1,18))
    def rodape(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#d4ad00'))
        canvas.line(38,34,A4[0]-38,34)
        canvas.setFont('Helvetica',8)
        canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(38,22,'AUTOSEG - Relatório técnico de ordem de serviço')
        canvas.drawRightString(A4[0]-38,22,f'Página {doc.page}')
    SimpleDocTemplate(str(caminho),pagesize=A4,rightMargin=38,leftMargin=38,topMargin=42,bottomMargin=48,
        title=f'Relatório OS {o["numero_os"]}').build(partes,onFirstPage=rodape,onLaterPages=rodape)
    return str(caminho)

CAMPOS_CONFIG = ('provedor_email','email_remetente','credencial_env','banco_nome',
                 'banco_titular','banco_agencia','banco_conta','chave_pix','dados_bancarios_texto')


def obter_config_prestador(banco,pid):
    """Configuração única do prestador, compartilhada pelo portal, GTK e e-mails.

    O portal antigo gravava os dados bancários em ``produtividade_bancos``.
    Se esse registro for mais recente que o de ``prestadores_config``, ele é
    migrado uma única vez para o campo oficial ``dados_bancarios_texto``.
    """
    with db(banco) as c:
        r=c.execute('SELECT * FROM prestadores_config WHERE prestador_id=?',(pid,)).fetchone()
        dados=dict(r) if r else {k:'' for k in CAMPOS_CONFIG}
        legado=None
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='produtividade_bancos'").fetchone():
            legado=c.execute('SELECT dados_texto,atualizado_em FROM produtividade_bancos WHERE prestador_id=?',
                             (pid,)).fetchone()
        if not legado:
            return dados
        texto_site=str(legado['dados_texto'] or '').strip()
        if not texto_site:
            return dados
        texto_config=str(dados.get('dados_bancarios_texto') or '').strip()
        if texto_config and str(legado['atualizado_em'] or '') <= str(dados.get('atualizado_em') or ''):
            return dados
        # O portal era a edição mais recente: promove o texto para o campo oficial.
        momento=agora()
        c.execute('''INSERT INTO prestadores_config(prestador_id,dados_bancarios_texto,atualizado_em)
                     VALUES(?,?,?) ON CONFLICT(prestador_id) DO UPDATE SET
                     dados_bancarios_texto=excluded.dados_bancarios_texto,
                     atualizado_em=excluded.atualizado_em''',
                  (pid,texto_site,momento))
        dados['dados_bancarios_texto']=texto_site
        dados['atualizado_em']=momento
        return dados


def salvar_config_prestador(banco,pid,dados):
    import re
    vals={k:str(dados.get(k,'') or '').strip() for k in CAMPOS_CONFIG}
    if any(len(v)>160 for k,v in vals.items() if k!='dados_bancarios_texto'):
        raise ValueError('Campo de configuração muito longo.')
    if len(vals['dados_bancarios_texto'])>4000:
        raise ValueError('O texto bancário não pode exceder 4.000 caracteres.')
    if vals['provedor_email'] not in ('','SMTP','Microsoft Graph','Gmail API','Outro'):
        raise ValueError('Provedor de e-mail inválido.')
    if vals['email_remetente'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',vals['email_remetente']):
        raise ValueError('E-mail remetente inválido.')
    if vals['credencial_env'] and not re.fullmatch(r'[A-Z_][A-Z0-9_]{2,100}',vals['credencial_env']):
        raise ValueError('Informe apenas o NOME de uma variável de ambiente para a credencial.')
    with db(banco) as c:
        if not c.execute('SELECT 1 FROM prestadores WHERE id=?',(pid,)).fetchone():
            raise ValueError('Prestador não encontrado.')
        c.execute('''INSERT INTO prestadores_config (
          prestador_id,provedor_email,email_remetente,credencial_env,banco_nome,
          banco_titular,banco_agencia,banco_conta,chave_pix,dados_bancarios_texto,atualizado_em)
          VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(prestador_id) DO UPDATE SET
          provedor_email=excluded.provedor_email,email_remetente=excluded.email_remetente,
          credencial_env=excluded.credencial_env,banco_nome=excluded.banco_nome,
          banco_titular=excluded.banco_titular,banco_agencia=excluded.banco_agencia,
          banco_conta=excluded.banco_conta,chave_pix=excluded.chave_pix,
          dados_bancarios_texto=excluded.dados_bancarios_texto,atualizado_em=excluded.atualizado_em''',
          (pid,*[vals[k] for k in CAMPOS_CONFIG],agora()))
    return True


def criar_email_rascunho(banco,os_id,pdf,prestador_id=None):
    with db(banco) as c:
        r=c.execute('SELECT o.numero_os,c.email,c.nome FROM ordens_servico o JOIN clientes c ON c.id=o.cliente_id WHERE o.id=?',(os_id,)).fetchone()
        if prestador_id is None:
            prestador_id=responsavel_atual(c,os_id)
    if not r: raise ValueError('OS inválida.')
    if not r['email']: raise ValueError('Cadastre o e-mail do cliente antes de preparar a mensagem.')
    config={}
    if prestador_id is not None:
        config=obter_config_prestador(banco,prestador_id)
    msg=EmailMessage();msg['To']=r['email'];msg['Subject']=f'AUTOSEG | Relatório de serviço {r["numero_os"]}'
    if config.get('email_remetente'):msg['From']=config['email_remetente']
    pagamento=[]
    for titulo,chave in (('Titular','banco_titular'),('Banco','banco_nome'),
                         ('Agência','banco_agencia'),('Conta','banco_conta'),('Pix','chave_pix')):
        if config.get(chave):pagamento.append(titulo+': '+config[chave])
    texto_bancario=str(config.get('dados_bancarios_texto') or '').strip()
    if texto_bancario:
        pagamento.append('Dados bancários e cadastrais:\n'+texto_bancario)
    corpo=f'Olá, {r["nome"]}.\n\nSegue em anexo o relatório da ordem de serviço {r["numero_os"]}.'
    if pagamento:corpo+='\n\nDados para pagamento (confira antes de enviar):\n'+'\n'.join(pagamento)
    corpo+='\n\nAtenciosamente,\n'+(config.get('banco_titular') or 'AUTOSEG')
    nota=ultima_nota_fiscal(banco,os_id)
    caminho_nf=None
    if nota:
        # Nota fiscal associada deve ser anexada; falha de leitura é erro real.
        _,caminho_nf=obter_nota_fiscal(banco,os_id,nota['id'])
        corpo+='\n\nA nota fiscal segue anexa a esta mensagem.'
    else:
        corpo+='\n\nNenhuma nota fiscal foi anexada a esta OS.'
    msg.set_content(corpo)
    msg.add_attachment(Path(pdf).read_bytes(),maintype='application',subtype='pdf',filename=Path(pdf).name)
    if caminho_nf:
        msg.add_attachment(Path(caminho_nf).read_bytes(),maintype='application',subtype='pdf',
                           filename=Path(nota['nome_original']).name if nota else Path(caminho_nf).name)
    nome_os=re.sub(r'[^A-Za-z0-9_-]','_',str(r['numero_os'] or f'OS-{os_id}')).strip('_')
    path=RASCUNHOS/f'email_{nome_os}_p{prestador_id if prestador_id is not None else 0}_{secrets.token_hex(4)}.eml';path.write_bytes(msg.as_bytes(policy=SMTP));return str(path)

def criar_rascunho_fiscal(banco,os_id):
    with db(banco) as c:
        r=c.execute('SELECT o.*,c.nome cliente_nome,c.documento cliente_documento,c.email cliente_email FROM ordens_servico o JOIN clientes c ON o.cliente_id=c.id WHERE o.id=?',(os_id,)).fetchone()
    if not r: raise ValueError('OS inválida')
    if r['status']!='Concluída':
        raise ValueError('Rascunho fiscal disponível somente para OS concluída. Cancelamentos e serviços não realizados não devem emitir nota automaticamente.')
    payload={'status':'RASCUNHO_NAO_EMITIDO','ordem_servico_id':os_id,'numero_os':r['numero_os'],'tomador':{'nome':r['cliente_nome'],'documento':r['cliente_documento'],'email':r['cliente_email']},'descricao':r['descricao'],'valor_servico':r['valor_total'],'moeda':'BRL','integracao_api':None,'observacao':'Não é nota fiscal válida. Requer dados do emitente, município, tributos, autorização e API oficial.'}
    nome_os=re.sub(r'[^A-Za-z0-9_-]','_',str(r['numero_os'] or f'OS-{os_id}')).strip('_')
    path=RASCUNHOS/f'nota_fiscal_rascunho_{nome_os}.json';path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8');return str(path)

def desatribuir(banco, os_id, ator='Administrador'):
    """Remove apenas o responsável atual. Histórico e participantes são preservados."""
    with db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        o = c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
        if not o or o['status'] not in ATIVAS:
            raise ValueError('Selecione uma OS ativa.')
        anterior = responsavel_atual(c, os_id)
        if anterior is None: return False
        c.execute('DELETE FROM os_responsaveis WHERE os_id=?',(os_id,))
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='produtividade_deslocamentos'").fetchone():
            c.execute('DELETE FROM produtividade_deslocamentos WHERE os_id=?',(os_id,))
        evento(c,os_id,'Desatribuição',f'OS disponível para nova atribuição. Responsável anterior (ID): {anterior}.',ator=ator)
        return True


def em_rota_atual(c, os_id):
    r = c.execute("SELECT id FROM os_deslocamentos WHERE os_id=? AND finalizado_em IS NULL ORDER BY id DESC LIMIT 1", (os_id,)).fetchone()
    return r is not None


def marcar_em_rota(banco, os_id, pid, ator=None):
    with db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        p = c.execute('SELECT nome FROM prestadores WHERE id=? AND ativo=1', (pid,)).fetchone()
        o = c.execute('SELECT status FROM ordens_servico WHERE id=?', (os_id,)).fetchone()
        if not p or not o:
            raise PermissionError('Prestador ou OS inválida.')
        if o['status'] not in ATIVAS:
            raise ValueError('Apenas OS ativas permitem marcar em rota.')
        if responsavel_atual(c, os_id) != pid:
            raise PermissionError('Somente o prestador responsável pode marcar em rota.')
        if em_rota_atual(c, os_id):
            return False
        ator_nome = ator or p['nome']
        c.execute('INSERT INTO os_deslocamentos(os_id, prestador_id, em_rota_em, ator) VALUES(?,?,?,?)',
                  (os_id, pid, agora(), ator_nome))
        evento(c, os_id, 'Em rota', f'{ator_nome} iniciou deslocamento para o local.', pid, ator_nome)
        return True


def finalizar_em_rota(c, os_id):
    c.execute("UPDATE os_deslocamentos SET finalizado_em=? WHERE os_id=? AND finalizado_em IS NULL",
              (agora(), os_id))


def salvar_rascunho_web(banco, os_id, pid, dados):
    import json
    limpos = {}
    for chave, valor in dados.items():
        # Arquivos não entram no JSON; são gravados em os_anexos com legenda própria.
        if chave.startswith('imagens_') or isinstance(valor, (bytes, tuple)):
            continue
        limpos[chave] = valor
    with db(banco) as c:
        c.execute('''INSERT INTO os_rascunhos_web(os_id, prestador_id, dados_json, atualizado_em)
                     VALUES(?,?,?,?) ON CONFLICT(os_id, prestador_id) DO UPDATE SET
                     dados_json=excluded.dados_json, atualizado_em=excluded.atualizado_em''',
                  (os_id, pid, json.dumps(limpos, ensure_ascii=False), agora()))
    return True


def obter_rascunho_web(banco, os_id, pid=None):
    import json
    with db(banco) as c:
        if pid is not None:
            r = c.execute('SELECT dados_json, atualizado_em FROM os_rascunhos_web WHERE os_id=? AND prestador_id=?',
                          (os_id, pid)).fetchone()
        else:
            r = c.execute('SELECT dados_json, atualizado_em FROM os_rascunhos_web WHERE os_id=? ORDER BY atualizado_em DESC LIMIT 1',
                          (os_id,)).fetchone()
        if not r:
            return None
        try:
            dados = json.loads(r['dados_json'])
        except Exception:
            dados = {}
        dados['_rascunho_atualizado_em'] = r['atualizado_em']
        return dados


def cancelar_em_rota(banco, os_id, pid, ator=None):
    with db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        p = c.execute('SELECT nome FROM prestadores WHERE id=? AND ativo=1', (pid,)).fetchone()
        if not p:
            raise PermissionError('Prestador inválido.')
        if responsavel_atual(c, os_id) != pid:
            raise PermissionError('Somente o prestador responsável pode cancelar o deslocamento.')
        if not em_rota_atual(c, os_id):
            return False
        finalizar_em_rota(c, os_id)
        ator_nome = ator or p['nome']
        evento(c, os_id, 'Em rota cancelado', f'{ator_nome} cancelou o deslocamento.', pid, ator_nome)
        return True


def salvar_nota_fiscal(banco, os_id, pid, nome, conteudo):
    """Anexa um PDF de nota fiscal à OS, com deduplicação por SHA-256."""
    if not isinstance(conteudo, bytes) or not conteudo.startswith(b'%PDF-'):
        raise ValueError('A nota fiscal deve ser um arquivo PDF válido.')
    if len(conteudo) > 20 * 1024 * 1024:
        raise ValueError('A nota fiscal deve ter no máximo 20 MB.')
    import hashlib
    digest = hashlib.sha256(conteudo).hexdigest()
    with db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        o = c.execute('SELECT status FROM ordens_servico WHERE id=?', (os_id,)).fetchone()
        if not o:
            raise ValueError('OS não encontrada.')
        if pid is not None:
            p = c.execute('SELECT nome FROM prestadores WHERE id=? AND ativo=1', (pid,)).fetchone()
            if not p:
                raise PermissionError('Prestador inativo.')
            if responsavel_atual(c, os_id) != pid:
                raise PermissionError('Somente o responsável pela OS pode anexar nota fiscal.')
        existente = c.execute('SELECT id FROM os_notas_fiscais WHERE os_id=? AND sha256=?',
                              (os_id, digest)).fetchone()
        if existente:
            return int(existente['id'])
        NOTAS.mkdir(parents=True, exist_ok=True)
        destino = NOTAS / (secrets.token_hex(16) + '.pdf')
        destino.write_bytes(conteudo)
        try:
            cur = c.execute('''INSERT INTO os_notas_fiscais
                (os_id,prestador_id,nome_original,caminho,sha256,criado_em)
                VALUES(?,?,?,?,?,?)''',
                (os_id, pid, Path(nome).name[:150], str(destino), digest, agora()))
            ator = 'Administrador'
            if pid is not None:
                ator = c.execute('SELECT nome FROM prestadores WHERE id=?', (pid,)).fetchone()['nome']
            evento(c, os_id, 'Nota fiscal anexada', Path(nome).name[:150], pid, ator)
            return int(cur.lastrowid)
        except Exception:
            destino.unlink(missing_ok=True)
            raise


def listar_notas_fiscais(banco, os_id):
    with db(banco) as c:
        return [dict(x) for x in c.execute(
            'SELECT id,os_id,nome_original,sha256,criado_em FROM os_notas_fiscais WHERE os_id=? ORDER BY id',
            (os_id,)).fetchall()]


def obter_nota_fiscal(banco, os_id, nota_id):
    with db(banco) as c:
        r = c.execute('SELECT * FROM os_notas_fiscais WHERE id=? AND os_id=?',
                      (nota_id, os_id)).fetchone()
    if not r:
        raise ValueError('Nota fiscal não encontrada.')
    caminho = Path(r['caminho']).resolve()
    raiz = NOTAS.resolve()
    if not caminho.is_relative_to(raiz) or not caminho.is_file():
        raise ValueError('Arquivo da nota fiscal indisponível no servidor.')
    if caminho.read_bytes()[:5] != b'%PDF-':
        raise ValueError('Arquivo da nota fiscal não é um PDF válido.')
    return dict(r), str(caminho)


def remover_nota_fiscal(banco, os_id, nota_id, pid=None, ator=None):
    """Remove o PDF anexado e preserva o histórico da OS.

    A permissão (responsável ou administrador) é conferida pela camada web.
    """
    with db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        o=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
        if not o:
            raise ValueError('OS não encontrada.')
        if o['status'] not in ATIVAS:
            raise ValueError('A nota fiscal só pode ser removida enquanto a OS está ativa.')
        r=c.execute('SELECT nome_original,caminho FROM os_notas_fiscais WHERE id=? AND os_id=?',
                    (nota_id,os_id)).fetchone()
        if not r:
            raise ValueError('Nota fiscal não encontrada.')
        c.execute('DELETE FROM os_notas_fiscais WHERE id=? AND os_id=?',(nota_id,os_id))
        evento(c,os_id,'Nota fiscal removida',Path(r['nome_original']).name[:150],pid,ator or 'Prestador')
    try:
        caminho=Path(r['caminho']).resolve()
        if caminho.is_relative_to(NOTAS.resolve()) and caminho.is_file():
            caminho.unlink()
    except OSError:
        pass
    return True


def ultima_nota_fiscal(banco, os_id):
    with db(banco) as c:
        r = c.execute('SELECT * FROM os_notas_fiscais WHERE os_id=? ORDER BY id DESC LIMIT 1',
                      (os_id,)).fetchone()
    return dict(r) if r else None


def obter_nota_fiscal_por_id(banco, nota_id):
    with db(banco) as c:
        r = c.execute('SELECT * FROM os_notas_fiscais WHERE id=?', (nota_id,)).fetchone()
    if not r:
        raise ValueError('Nota fiscal não encontrada.')
    caminho = Path(r['caminho']).resolve()
    raiz = NOTAS.resolve()
    if not caminho.is_relative_to(raiz) or not caminho.is_file():
        raise ValueError('Arquivo da nota fiscal indisponível no servidor.')
    if caminho.read_bytes()[:5] != b'%PDF-':
        raise ValueError('Arquivo da nota fiscal não é um PDF válido.')
    return dict(r), str(caminho)
