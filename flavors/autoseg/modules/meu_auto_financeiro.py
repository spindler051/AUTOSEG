"""Meu Auto Financeiro - módulo financeiro pessoal/familiar do Portal do Prestador AUTOSEG.

Mantém dados próprios em SQLite. Lê o financeiro da AUTOSEG SOMENTE para conciliar
recebimentos efetivamente confirmados e repasses. Não edita ordens nem lançamentos AUTOSEG.
"""
from __future__ import annotations

import calendar
import hashlib
import hmac
import html
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, urlparse, quote

from officina.core import runtime_config

BASE = Path(os.environ.get('AUTOSEG_BASE') or runtime_config.base_dir())
DB = Path(os.environ.get('MEU_AUTO_FINANCEIRO_DB') or BASE / 'meu_auto_financeiro.db')
DOCS = DB.parent / 'meu_auto_financeiro_comprovantes'
SESSOES = {}
TENTATIVAS = {}
LOCK = threading.RLock()
COOKIE = 'maf_session'
TTL = 8 * 3600
MAX_COMPROVANTE = 4 * 1024 * 1024


def esc(value):
    return html.escape(str(value if value is not None else ''), quote=True)


def centavos(value):
    """Aceita 1234.56 ou 1.234,56; sem ponto flutuante para cálculos."""
    raw = str(value if value is not None else '').strip().replace('R$', '').replace(' ', '')
    if ',' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    try:
        num = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError('Valor monetário inválido.')
    if not num.is_finite():
        raise ValueError('Valor monetário inválido.')
    val = int((num * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    if abs(val) > 100_000_000_000:
        raise ValueError('Valor fora dos limites.')
    return val


def reais(value):
    n = int(value or 0)
    inteiro, frac = divmod(abs(n), 100)
    x = f'{inteiro:,}'.replace(',', '.') + f',{frac:02d}'
    return ('−' if n < 0 else '') + 'R$ ' + x


def agora():
    return datetime.now().isoformat(timespec='seconds')


@contextmanager
def conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB), timeout=20)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=20000')
    try:
        with c:
            yield c
    finally:
        c.close()


def instalar():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY, nome TEXT NOT NULL, email TEXT UNIQUE COLLATE NOCASE,
            senha_hash TEXT, autoseg_pid INTEGER UNIQUE, familia_id INTEGER,
            criado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS familias (
            id INTEGER PRIMARY KEY, nome TEXT NOT NULL, admin_id INTEGER NOT NULL,
            criado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS convites (
            codigo TEXT PRIMARY KEY, familia_id INTEGER NOT NULL,
            expira_em TEXT NOT NULL, usado_por INTEGER);
        CREATE TABLE IF NOT EXISTS movimentos (
            id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
            valor_centavos INTEGER NOT NULL, descricao TEXT NOT NULL, tipo TEXT NOT NULL,
            origem_chave TEXT, criado_em TEXT NOT NULL,
            UNIQUE(usuario_id,origem_chave));
        CREATE TABLE IF NOT EXISTS sync_autoseg (
            usuario_id INTEGER NOT NULL, chave TEXT NOT NULL,
            valor_centavos INTEGER NOT NULL, atualizado_em TEXT NOT NULL,
            PRIMARY KEY(usuario_id,chave));
        CREATE TABLE IF NOT EXISTS salarios (
            id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL, descricao TEXT NOT NULL,
            valor_centavos INTEGER NOT NULL, dia INTEGER NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1, criado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS salarios_recebidos (
            salario_id INTEGER NOT NULL, periodo TEXT NOT NULL,
            confirmado_em TEXT NOT NULL, PRIMARY KEY(salario_id,periodo));
        CREATE TABLE IF NOT EXISTS contas (
            id INTEGER PRIMARY KEY, responsavel_id INTEGER NOT NULL, familia_id INTEGER,
            descricao TEXT NOT NULL, total_centavos INTEGER NOT NULL,
            vencimento TEXT NOT NULL, fornecedor_pago_em TEXT,
            comprovante_fornecedor TEXT, cancelada_em TEXT, motivo_cancelamento TEXT,
            criada_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cotas (
            conta_id INTEGER NOT NULL, usuario_id INTEGER NOT NULL,
            valor_centavos INTEGER NOT NULL, comprovante TEXT,
            enviado_em TEXT, confirmado_em TEXT,
            PRIMARY KEY(conta_id,usuario_id));
        CREATE TABLE IF NOT EXISTS emprestimos (
            id INTEGER PRIMARY KEY, credor_id INTEGER NOT NULL, devedor_id INTEGER NOT NULL,
            valor_centavos INTEGER NOT NULL, comprovante_envio TEXT,
            confirmado_envio_em TEXT, vencimento TEXT, criado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS devolucoes (
            id INTEGER PRIMARY KEY, emprestimo_id INTEGER NOT NULL,
            valor_centavos INTEGER NOT NULL, comprovante TEXT NOT NULL,
            enviado_em TEXT NOT NULL, confirmado_em TEXT);
        CREATE TABLE IF NOT EXISTS transferencias_admin (
            id INTEGER PRIMARY KEY, familia_id INTEGER NOT NULL,
            de_id INTEGER NOT NULL, para_id INTEGER NOT NULL,
            solicitado_em TEXT NOT NULL, aceito_em TEXT,
            estado TEXT NOT NULL DEFAULT 'pendente');
        CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY, usuario_id INTEGER, acao TEXT NOT NULL,
            detalhe TEXT NOT NULL, criado_em TEXT NOT NULL);
        ''')
    if os.name == 'posix':
        try: os.chmod(DB, 0o600)
        except OSError: pass


def auditoria(c, uid, acao, detalhe=''):
    c.execute('INSERT INTO auditoria(usuario_id,acao,detalhe,criado_em) VALUES(?,?,?,?)',
              (uid, acao, str(detalhe)[:500], agora()))


def senha_hash(senha):
    if len(senha) < 10 or len(senha) > 200:
        raise ValueError('A senha deve ter entre 10 e 200 caracteres.')
    sal = secrets.token_bytes(16)
    it = 450_000
    h = hashlib.pbkdf2_hmac('sha256', senha.encode(), sal, it)
    return f'pbkdf2_sha256${it}${sal.hex()}${h.hex()}'


def verificar_senha(senha, gravado):
    try:
        alg, rounds, sal, valor = gravado.split('$')
        if alg != 'pbkdf2_sha256': return False
        res = hashlib.pbkdf2_hmac('sha256', senha.encode(), bytes.fromhex(sal), int(rounds))
        return hmac.compare_digest(res, bytes.fromhex(valor))
    except (ValueError, AttributeError, TypeError):
        return False


def usuario_prestador(pid, nome):
    with conn() as c:
        c.execute('''INSERT INTO usuarios(nome,autoseg_pid,criado_em) VALUES(?,?,?)
             ON CONFLICT(autoseg_pid) DO UPDATE SET nome=excluded.nome''', (nome, pid, agora()))
        row = c.execute('SELECT * FROM usuarios WHERE autoseg_pid=?', (pid,)).fetchone()
        return dict(row)


def usuario_por_id(uid):
    with conn() as c:
        x = c.execute('SELECT * FROM usuarios WHERE id=?', (uid,)).fetchone()
        return dict(x) if x else None


def saldo(c, uid):
    return c.execute('SELECT COALESCE(SUM(valor_centavos),0) FROM movimentos WHERE usuario_id=?',(uid,)).fetchone()[0]


def movimento(c, uid, cents, descricao, tipo, chave=None):
    c.execute('''INSERT OR IGNORE INTO movimentos
        (usuario_id,valor_centavos,descricao,tipo,origem_chave,criado_em)
        VALUES(?,?,?,?,?,?)''',(uid,int(cents),descricao,tipo,chave,agora()))


def fonte_autoseg(banco, pid):
    """Espelha exatamente as parcelas de Recebido que o portal exibe por prestador.

    Um lançamento encerrado no AUTOSEG não entra enquanto não estiver Recebido.
    Repasses entram somente no valor já registrado como pago ao técnico secundário.
    """
    from officina.core.prestadores_ext import db as autoseg_db
    saida = {}
    with autoseg_db(banco) as c:
        primarios = c.execute('''
            SELECT f.id, f.os_id, o.numero_os, f.valor, f.status,
                   COALESCE((SELECT SUM(r.valor_centavos)
                       FROM produtividade_rateios r WHERE r.os_id=f.os_id),0) rateio
            FROM financeiro f
            JOIN os_encerramentos e ON e.os_id=f.os_id
            JOIN ordens_servico o ON o.id=f.os_id
            WHERE e.prestador_id=?''',(pid,)).fetchall()
        for f in primarios:
            valor = centavos(f['valor']) - int(f['rateio']) if f['status']=='Recebido' else 0
            if valor < 0:
                raise ValueError(f'Rateio maior que recebido na OS {f["os_id"]}.')
            saida[f'os:{f["id"]}'] = (valor, f'OS {f["numero_os"]} · parcela recebida AUTOSEG')
        secundarios = c.execute('''
            SELECT r.os_id, o.numero_os, COALESCE(p.pago_centavos,0) pago
            FROM produtividade_rateios r
            JOIN ordens_servico o ON o.id=r.os_id
            LEFT JOIN produtividade_repasses p ON p.os_id=r.os_id AND p.tecnico_id=r.tecnico_id
            WHERE r.tecnico_id=?''',(pid,)).fetchall()
        for item in secundarios:
            saida[f'repasse:{item["os_id"]}'] = (int(item['pago']),f'OS {item["numero_os"]} · repasse AUTOSEG')
    return saida


def reconciliar_autoseg(banco, usuario):
    pid = usuario.get('autoseg_pid')
    if pid is None: return 0
    novos = fonte_autoseg(banco, int(pid))
    alteracoes = 0
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        anteriores = {r['chave']:r['valor_centavos'] for r in c.execute(
            'SELECT chave,valor_centavos FROM sync_autoseg WHERE usuario_id=?',(usuario['id'],))}
        for chave in sorted(set(novos)|set(anteriores)):
            atual, descricao = novos.get(chave, (0,'AUTOSEG · ajuste de recebimento'))
            anterior = anteriores.get(chave,0)
            if atual == anterior:continue
            delta = atual - anterior
            movimento(c,usuario['id'],delta,
                descricao if delta >= 0 else f'Ajuste: {descricao}',
                'autoseg' if delta >= 0 else 'ajuste_autoseg',
                None) # serializado pelo checkpoint sync_autoseg na mesma transação
            c.execute('''INSERT INTO sync_autoseg(usuario_id,chave,valor_centavos,atualizado_em)
                   VALUES(?,?,?,?) ON CONFLICT(usuario_id,chave) DO UPDATE SET
                   valor_centavos=excluded.valor_centavos,atualizado_em=excluded.atualizado_em''',
                (usuario['id'],chave,atual,agora()))
            alteracoes += 1
    return alteracoes


def sincronizar_prestador(banco, pid):
    """Atualiza prestadores que já ativaram Meu Auto Financeiro; não cria contas de terceiros."""
    with conn() as c:
        x=c.execute('SELECT * FROM usuarios WHERE autoseg_pid=?',(pid,)).fetchone()
    if not x:return 0
    return reconciliar_autoseg(banco,dict(x))


def sincronizar_todos(banco):
    """Reconciliação periódica: cobre recebimentos via GTK e mudanças externas."""
    with conn() as c:
        usuarios=[dict(x) for x in c.execute('SELECT * FROM usuarios WHERE autoseg_pid IS NOT NULL')]
    erros=0
    for usuario in usuarios:
        try:reconciliar_autoseg(banco,usuario)
        except (sqlite3.Error,ValueError):erros+=1
    return erros


def resumo_autoseg(banco,pid):
    """A receber é informativo; Recebido vem da fonte oficial, não do saldo pessoal."""
    from officina.core.produtividade_os import financeiro_pessoal
    pessoal = financeiro_pessoal(banco,pid)
    recebido = pendente = 0
    for p in pessoal['brutos_proprios']:
        valor = centavos(p['valor']) - int(p['partes_centavos'])
        if p['status']=='Recebido': recebido += valor
        elif p['status']=='Aguardando pagamento':pendente += valor
    for p in pessoal['receber_de_colegas']:
        recebido += int(p['pago_centavos'])
        pendente += int(p['valor_centavos'])-int(p['pago_centavos'])
    return recebido, pendente


def documento_upload(data, nome):
    if not isinstance(data,(tuple,list)) or len(data)!=2:
        raise ValueError('Anexe o comprovante de pagamento (PDF, PNG ou JPEG).')
    filename, content = data
    if not isinstance(content, bytes) or not content or len(content)>MAX_COMPROVANTE:
        raise ValueError('Comprovante inválido ou maior que 4 MB.')
    if content.startswith(b'%PDF-') and filename.lower().endswith('.pdf'): ext = '.pdf'
    elif content.startswith(b'\x89PNG\r\n\x1a\n') and filename.lower().endswith('.png'): ext = '.png'
    elif content.startswith(b'\xff\xd8\xff') and filename.lower().endswith(('.jpg','.jpeg')): ext = '.jpg'
    else: raise ValueError('Aceitos somente arquivos PDF, PNG ou JPEG válidos.')
    DOCS.mkdir(mode=0o700,parents=True,exist_ok=True)
    if os.name=='posix':os.chmod(DOCS,0o700)
    nome_arquivo = secrets.token_hex(20)+ext
    p = DOCS / nome_arquivo
    with p.open('xb') as f: f.write(content)
    if os.name=='posix':os.chmod(p,0o600)
    return nome_arquivo


def _html_campo(nome,rotulo,tipo='text',valor='',required=True,extra=''):
    return (f'<label>{esc(rotulo)}<input name="{esc(nome)}" type="{esc(tipo)}" '
            f'value="{esc(valor)}" {"required" if required else ""} {extra}></label>')


def _form(rota, csrf, conteudo, rotulo='Salvar', multipart=False):
    enc = ' enctype="multipart/form-data"' if multipart else ''
    return (f'<form method="post" action="/auto-financeiro/{esc(rota)}"{enc}>'
           f'<input type="hidden" name="csrf" value="{esc(csrf)}">'
           +conteudo+f'<button type="submit">{esc(rotulo)}</button></form>')


def _botao(rota,csrf,label,extra=''):
    return _form(rota,csrf,extra,label)


def _link(path,texto):
    return f'<a class="botao" href="/auto-financeiro/{esc(path)}">{esc(texto)}</a>'


def _pagina(titulo,conteudo,usuario=None,flash=None):
    menus = ['','extrato','contas','salarios','familia','emprestimos','bussola']
    labels = ['Início','Extrato','Contas a pagar','Salários','Família','Empréstimos','Bússola']
    nav = ' '.join(_link(k,v) for k,v in zip(menus,labels)) if usuario else ''
    sair = _link('sair','Sair da conta familiar') if usuario and usuario.get('autoseg_pid') is None else '<a class="botao" href="/">Portal do Prestador</a>' if usuario else ''
    aviso = f'<p class="aviso">{esc(flash)}</p>' if flash else ''
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(titulo)} · Meu Auto Financeiro</title><style>
:root{{--amarelo:#ffd400;--muted:#bdbdbd}}*{{box-sizing:border-box}}body{{background:#090909;color:#f5f5f5;font:16px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.5;margin:0}}header{{background:#1b1b1b;border-bottom:3px solid #ffd400;padding:16px max(16px,calc((100vw - 1100px)/2))}}a{{color:#ffd400}}header strong{{font-size:23px}}nav{{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}}.botao,button{{background:#ffd400;color:#111;border:0;border-radius:8px;display:inline-block;font-weight:700;padding:10px 13px;text-decoration:none;cursor:pointer;margin:3px}}main{{max-width:1100px;margin:auto;padding:16px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}section{{border:1px solid #555;border-radius:12px;background:#1d1d1d;padding:17px;margin:13px 0;min-width:0}}section h2{{margin:0 0 10px;font-size:19px}}.numero{{font-size:26px;font-weight:800}}.muted,small{{color:var(--muted)}}label{{display:block;margin:8px 0}}input,select,textarea{{width:100%;background:#080808;color:white;border:1px solid #999;padding:10px;border-radius:6px;font:inherit}}input[type=checkbox]{{width:auto}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;border-bottom:1px solid #555;padding:8px;overflow-wrap:anywhere}}.tabela{{overflow-x:auto}}.aviso{{border-left:4px solid #ffd400;padding:12px;background:#29261a}}.ok{{color:#7dedb3}}.alerta{{color:#ffbe7d}}.linha{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}}form.inline{{display:inline-block}}button{{font-size:14px}}@media(max-width:600px){{.numero{{font-size:22px}}td,th{{font-size:13px}}}}
</style></head><body><header><strong>Meu Auto Financeiro</strong> <span class="muted">· integrado ao AUTOSEG</span><nav>{nav}{sair}</nav></header><main><h1>{esc(titulo)}</h1>{aviso}{conteudo}</main></body></html>'''


def _row(cells):return '<tr>'+''.join(f'<td>{c}</td>' for c in cells)+'</tr>'


def _table(head,rows):
    return '<div class="tabela"><table><thead>'+_row([f'<b>{esc(x)}</b>' for x in head])+'</thead><tbody>'+''.join(rows)+'</tbody></table></div>'


def _sessao_familiar(handler):
    try:
        ck=SimpleCookie();ck.load(handler.headers.get('Cookie',''))
        token=ck[COOKIE].value
    except (KeyError,ValueError):return None
    with LOCK:
        session=SESSOES.get(token)
        if not session or session['exp']<time.time():
            SESSOES.pop(token,None)
            return None
    user=usuario_por_id(session['uid'])
    return (user,session['csrf']) if user and user['autoseg_pid'] is None else None


def _cookie(handler,tok,erase=False):
    secure=(handler.headers.get('X-Forwarded-Proto','').lower()=='https'
            or handler.headers.get('CF-Ray') or os.environ.get('PRESTADOR_HTTPS')=='1')
    return f'{COOKIE}={tok}; Path=/auto-financeiro; HttpOnly; SameSite=Strict; '+('Secure; ' if secure else '')+f'Max-Age={0 if erase else TTL}'


def _principal(handler,prestador):
    if prestador:
        return usuario_prestador(prestador['pid'],prestador['nome']),prestador['csrf']
    return _sessao_familiar(handler) or (None,None)


def _render(handler,titulo,corpo,user=None,info=None,status=200,cookie=None):
    return handler.responder(_pagina(titulo,corpo,user,info),status=status,cookie=cookie)


def _fail(handler,mensagem,user=None,status=400):
    return _render(handler,'Ação não concluída',f'<section>{esc(mensagem)}</section>'+_link('','Voltar'),user,status=status)


def _query_user_family(c,uid):
    row=c.execute('SELECT familia_id FROM usuarios WHERE id=?',(uid,)).fetchone()
    return row['familia_id'] if row else None


def _familia(c,u):
    if not u['familia_id']:return None
    f=c.execute('SELECT * FROM familias WHERE id=?',(u['familia_id'],)).fetchone()
    return dict(f) if f else None


def _pendencias_familia(c,uid,fid):
    # Somente obrigações financeiras efetivas/pendentes, não meros cadastros.
    cotas = c.execute('''SELECT COUNT(*) FROM cotas t JOIN contas x ON x.id=t.conta_id
       WHERE x.familia_id=? AND x.fornecedor_pago_em IS NOT NULL
       AND t.usuario_id=? AND x.responsavel_id!=t.usuario_id
       AND t.confirmado_em IS NULL''',(fid,uid)).fetchone()[0]
    a_receber = c.execute('''SELECT COUNT(*) FROM contas x JOIN cotas t ON t.conta_id=x.id
       WHERE x.familia_id=? AND x.responsavel_id=? AND x.fornecedor_pago_em IS NOT NULL
       AND t.usuario_id!=x.responsavel_id AND t.confirmado_em IS NULL''',(fid,uid)).fetchone()[0]
    emprestimos = c.execute('''SELECT e.id,e.valor_centavos,
        COALESCE((SELECT SUM(d.valor_centavos) FROM devolucoes d
        WHERE d.emprestimo_id=e.id AND d.confirmado_em IS NOT NULL),0) quitado
        FROM emprestimos e WHERE e.confirmado_envio_em IS NOT NULL
        AND (e.credor_id=? OR e.devedor_id=?)''',(uid,uid)).fetchall()
    falta_emprestimos=sum(1 for e in emprestimos if e['valor_centavos']>e['quitado'])
    return cotas+a_receber+falta_emprestimos


def _familia_membros(c,fid):
    return [dict(row) for row in c.execute('SELECT * FROM usuarios WHERE familia_id=? ORDER BY id',(fid,))]


def _dia_salario(periodo,dia):
    ano,mes=map(int,periodo.split('-'))
    return date(ano,mes,min(dia,calendar.monthrange(ano,mes)[1])).isoformat()


def _saldo_painel(c,usuario):
    return saldo(c,usuario['id'])


def _lista_movimentos(c,uid,limit=100):
    return c.execute('SELECT * FROM movimentos WHERE usuario_id=? ORDER BY id DESC LIMIT ?', (uid,limit)).fetchall()


def _selecao_familia(c,usuario):
    f=_familia(c,usuario)
    if not f:return None, []
    return f, _familia_membros(c,f['id'])


def _card(titulo,conteudo):
    return f'<section><h2>{esc(titulo)}</h2>{conteudo}</section>'


def _resumo_conta(c,conta_id):
    return c.execute('SELECT * FROM contas WHERE id=?',(conta_id,)).fetchone()


def _permissao_conta(c,conta,uid,admin=False):
    if conta['responsavel_id']==uid:return True
    if admin and conta['familia_id']:return c.execute('''SELECT 1 FROM familias WHERE id=? AND admin_id=?''',(conta['familia_id'],uid)).fetchone() is not None
    return False


def _link_doc(uid,kind,doc_id):
    return f'<a href="/auto-financeiro/comprovante/{esc(kind)}/{int(doc_id)}">Comprovante</a>'


def GET(handler,path,prestador,banco):
    user,csrf=_principal(handler,prestador)
    if path=='/auto-financeiro/sair':
        try:
            ck=SimpleCookie();ck.load(handler.headers.get('Cookie',''))
            tok=ck[COOKIE].value
            with LOCK:SESSOES.pop(tok,None)
        except (KeyError,ValueError):pass
        return _render(handler,'Sessão encerrada',_link('entrar','Entrar novamente'),cookie=_cookie(handler,'',True))
    if not user:
        if path=='/auto-financeiro/cadastro':
            codigo=parse_qs(urlparse(handler.path).query).get('convite',[''])[0]
            if not codigo:return _fail(handler,'É necessário um convite válido.',status=403)
            with conn() as c:
                r=c.execute('SELECT * FROM convites WHERE codigo=? AND usado_por IS NULL',(codigo,)).fetchone()
            if not r or r['expira_em']<agora():return _fail(handler,'Convite inválido ou expirado.',status=403)
            conteudo=_form('cadastro', '', _html_campo('codigo','Código do convite',valor=codigo)
                            +_html_campo('nome','Seu nome')+_html_campo('email','E-mail',tipo='email')
                            +_html_campo('senha','Senha (mínimo 10 caracteres)',tipo='password'), 'Criar meu acesso')
            return _render(handler,'Entrar na família',_card('Cadastro por convite',conteudo))
        conteudo=_form('entrar','',_html_campo('email','E-mail',tipo='email')
                       +_html_campo('senha','Senha',tipo='password'),'Entrar')
        return _render(handler,'Acesso da família',_card('Login individual',conteudo)
                       +'<p class="muted">Prestadores entram pelo login AUTOSEG. Familiares usam login próprio e convite.</p>'
                       +'<a href="/login">Login do prestador AUTOSEG</a>')
    # Conciliar apenas a origem individual do prestador; falha de AUTOSEG não apaga histórico.
    erro_sync=None
    if user['autoseg_pid'] is not None:
        try:reconciliar_autoseg(banco,user)
        except (sqlite3.Error,ValueError) as exc:erro_sync=str(exc)
    with conn() as c:
        user=dict(c.execute('SELECT * FROM usuarios WHERE id=?',(user['id'],)).fetchone())
        f,membros=_selecao_familia(c,user)
        is_admin=bool(f and f['admin_id']==user['id'])
        total=saldo(c,user['id'])
        cab=f'<p class="muted">{esc(user["nome"])} · Saldo individual: <strong>{reais(total)}</strong></p>'
        if erro_sync:cab+=f'<p class="aviso">Não foi possível atualizar os recebimentos AUTOSEG: {esc(erro_sync)}.</p>'
        if path=='/auto-financeiro' or path=='/auto-financeiro/':
            recebido=pendente=0
            if user['autoseg_pid'] is not None:
                try:recebido,pendente=resumo_autoseg(banco,user['autoseg_pid'])
                except (sqlite3.Error,ValueError):pass
            resumo='<div class="grid">'+_card('Saldo pessoal disponível',f'<div class="numero">{reais(total)}</div>')
            if user['autoseg_pid'] is not None:
                resumo+=_card('Recebido AUTOSEG',f'<div class="numero">{reais(recebido)}</div><small>Espelho do Financeiro do Prestador, sem descontos pessoais</small>')
                resumo+=_card('A receber AUTOSEG',f'<div class="numero">{reais(pendente)}</div><small>Não entra no saldo até a confirmação</small>')
            if f:
                geral=sum(saldo(c,u['id']) for u in membros)
                resumo+=_card('Saldo geral da família',f'<div class="numero">{reais(geral)}</div><small>{len(membros)} integrantes</small>')
            resumo+='</div>'
            movs=_lista_movimentos(c,user['id'],12)
            linhas=[_row([esc(x['criado_em'][:16].replace('T',' ')),esc(x['descricao']),esc(x['tipo']),reais(x['valor_centavos'])]) for x in movs]
            corpo=cab+resumo+_card('Registrar receita recebida ou despesa',_form('movimento',csrf,
                 _html_campo('descricao','Descrição')+_html_campo('valor','Valor (R$)',valor='0,00')+
                 '<label>Tipo<select name="tipo"><option value="despesa">Despesa paga</option><option value="receita">Receita já recebida</option></select></label>',
                 'Registrar'))+_card('Últimas movimentações',_table(['Data','Descrição','Origem','Valor'],linhas))
            return _render(handler,'Painel individual',corpo,user)
        if path=='/auto-financeiro/extrato':
            linhas=[]
            for x in _lista_movimentos(c,user['id'],200):
                action=''
                if x['tipo'] in ('receita','despesa'):
                    ja=c.execute('SELECT 1 FROM movimentos WHERE usuario_id=? AND origem_chave=?',
                        (user['id'],f'estorno:{x["id"]}')).fetchone()
                    action='Estornado' if ja else _botao('movimento/estornar',csrf,'Estornar',
                        f'<input type="hidden" name="id" value="{x["id"]}">')
                linhas.append(_row([esc(x['criado_em'].replace('T',' ')),esc(x['descricao']),esc(x['tipo']),reais(x['valor_centavos']),action]))
            return _render(handler,'Extrato',cab+_card('Histórico individual',
                '<p class="muted">Para corrigir um lançamento manual: estorne-o e depois registre o valor correto. Os dois eventos permanecem no histórico.</p>'
                +_table(['Data','Descrição','Tipo','Valor','Correção'],linhas)),user)
        if path=='/auto-financeiro/salarios':
            periodo=date.today().strftime('%Y-%m')
            salarios=c.execute('SELECT * FROM salarios WHERE usuario_id=? AND ativo=1',(user['id'],)).fetchall()
            linhas=[]
            for s in salarios:
                pago=c.execute('SELECT confirmado_em FROM salarios_recebidos WHERE salario_id=? AND periodo=?',(s['id'],periodo)).fetchone()
                bot='Recebido em '+esc(pago['confirmado_em'][:10]) if pago else _botao('salario/confirmar',csrf,'Confirmar recebimento',f'<input type="hidden" name="id" value="{s["id"]}">')
                linhas.append(_row([esc(s['descricao']),reais(s['valor_centavos']),esc(_dia_salario(periodo,s['dia'])),bot]))
            novo=_form('salario/novo',csrf,_html_campo('descricao','Descrição',valor='Salário')
                        +_html_campo('valor','Valor mensal (R$)')+_html_campo('dia','Dia previsto (1 a 31)',tipo='number',valor='5',extra='min="1" max="31"'),'Cadastrar salário')
            return _render(handler,'Salários recorrentes',cab+_card('Mês '+periodo,_table(['Salário','Valor','Data prevista','Confirmação'],linhas)) +_card('Novo salário',novo),user)
        if path=='/auto-financeiro/familia':
            if not f:
                return _render(handler,'Família',cab+_card('Criar sua família',_form('familia/criar',csrf,_html_campo('nome','Nome da família'),'Criar família'))
                               +'<p>Se outro membro já criou a família, peça o convite para participar.</p>',user)
            geral=sum(saldo(c,u['id']) for u in membros)
            despesa_mes=0
            inicio=date.today().strftime('%Y-%m')
            for member in membros:
                despesa_mes+=sum(-r['valor_centavos'] for r in c.execute(
                    '''SELECT valor_centavos FROM movimentos WHERE usuario_id=? AND valor_centavos<0
                       AND tipo IN ('despesa','conta_fornecedor') AND criado_em LIKE ?''',
                    (member['id'],inicio+'%')))
            linhas=[_row([esc(m['nome']),reais(saldo(c,m['id'])),'Administrador' if f['admin_id']==m['id'] else 'Integrante']) for m in membros]
            corpo=cab+'<div class="grid">'+_card('Saldo familiar',f'<div class="numero">{reais(geral)}</div>')+_card('Despesas gerais do mês',f'<div class="numero">{reais(despesa_mes)}</div>')+'</div>'
            corpo+=_card('Saldos individuais de todos os integrantes',_table(['Integrante','Saldo','Função'],linhas))
            if is_admin:
                corpo+=_card('Convidar familiar',_form('familia/convidar',csrf,'<p>Gere um código de convite válido por 24 horas.</p>','Gerar convite'))
                conv=c.execute('SELECT codigo,expira_em FROM convites WHERE familia_id=? AND usado_por IS NULL ORDER BY expira_em DESC LIMIT 3',(f['id'],)).fetchall()
                corpo+=_card('Convites ativos',''.join(f'<p>Código: <code>{esc(x["codigo"])}</code> · Expira: {esc(x["expira_em"])} · <a href="/auto-financeiro/cadastro?convite={quote(x["codigo"])}">link para cadastro</a></p>' for x in conv) or '<p>Sem convites ativos.</p>')
                outros=[m for m in membros if m['id']!=user['id']]
                if outros:
                    seletor='<label>Novo administrador<select name="uid">'+''.join(f'<option value="{m["id"]}">{esc(m["nome"])}</option>' for m in outros)+'</select></label>'
                    corpo+=_card('Transferir administração com aceite',_form('familia/transferir',csrf,seletor,'Solicitar transferência'))
                    linhas_remover=[]
                    for m in outros:
                        excluir=_form('familia/remover',csrf,
                            f'<input type="hidden" name="uid" value="{m["id"]}">'
                            +_html_campo('motivo',f'Motivo para remover {m["nome"]}'),
                            'Confirmar remoção')
                        linhas_remover.append(_card('Remover '+m['nome'],excluir))
                    corpo+=_card('Remoção administrativa', '<p class="muted">Preserva dívidas e comprovantes, e revoga o acesso à família.</p>'+''.join(linhas_remover))
            pend=c.execute('''SELECT * FROM transferencias_admin
                    WHERE familia_id=? AND para_id=? AND estado='pendente' ORDER BY id DESC''',(f['id'],user['id'])).fetchall()
            for pedido in pend:
                corpo+=_card('Convite para administrar a família',_form('familia/aceitar-admin',csrf,
                    f'<input type="hidden" name="pedido_id" value="{pedido["id"]}">',
                    'Aceitar administração'))
            if f['admin_id']!=user['id']:
                corpo+=_card('Sair da família',_form('familia/sair',csrf,
                  '<p>Saída voluntária disponível somente quando não houver contas ou empréstimos pendentes.</p>',
                  'Solicitar saída'))
            return _render(handler,'Família · '+f['nome'],corpo,user)
        if path=='/auto-financeiro/contas':
            individuais=c.execute('''SELECT * FROM contas
                    WHERE responsavel_id=? AND familia_id IS NULL
                    ORDER BY id DESC LIMIT 150''',(user['id'],)).fetchall()
            compartilhadas=c.execute('''SELECT * FROM contas
                    WHERE familia_id IS NOT NULL AND (familia_id=?
                    OR id IN (SELECT conta_id FROM cotas WHERE usuario_id=?))
                    ORDER BY id DESC LIMIT 150''',
                    (user['familia_id'] or -1,user['id'])).fetchall()

            def _linha_conta(conta, com_contribuicoes):
                cid=conta['id']
                parcelas=c.execute('SELECT * FROM cotas WHERE conta_id=? ORDER BY usuario_id',(cid,)).fetchall()
                devidos=sum(p['valor_centavos'] for p in parcelas
                            if p['usuario_id']!=conta['responsavel_id'] and not p['confirmado_em'])
                status=('Cancelada' if conta['cancelada_em'] else
                        'Fornecedor pago' if conta['fornecedor_pago_em'] else 'A pagar')
                dados=[_link('conta/'+str(cid),conta['descricao']),
                       reais(conta['total_centavos']),esc(conta['vencimento']),esc(status)]
                if com_contribuicoes:
                    dados.append(reais(devidos))
                return _row(dados)

            linhas_ind=[_linha_conta(x,False) for x in individuais]
            linhas_comp=[_linha_conta(x,True) for x in compartilhadas]
            corpo=cab
            corpo+=_card('Contas a pagar individuais',
                _table(['Conta','Total','Vencimento','Fornecedor'],linhas_ind)
                if linhas_ind else '<p class="muted">Nenhuma conta individual cadastrada.</p>')
            corpo+=_card('Contas compartilhadas',
                _table(['Conta','Total','Vencimento','Fornecedor','Contribuições pendentes'],linhas_comp)
                if linhas_comp else '<p class="muted">Nenhuma conta compartilhada cadastrada.</p>')
            campos=(_html_campo('descricao','Descrição')
                    +_html_campo('valor','Valor da conta (R$)')
                    +_html_campo('vencimento','Vencimento',tipo='date',valor=date.today().isoformat()))
            corpo+=_card('Nova conta a pagar individual',
                _form('conta/criar',csrf,
                      campos+'<input type="hidden" name="tipo" value="individual">',
                      'Cadastrar conta individual'))
            if f and len(membros)>1:
                participantes=(''.join(
                    f'<label><input type="checkbox" name="participantes[]" '
                    f'value="{m["id"]}">{esc(m["nome"])}</label>'
                    for m in membros if m['id']!=user['id']))
                compartilhada=(campos
                    +'<input type="hidden" name="tipo" value="compartilhada">'
                    +'<p>Quem participa? (o responsável sempre está incluído)</p>'
                    +participantes
                    +'<label>Divisão<select name="divisao">'
                    '<option value="igual">Igualitária</option>'
                    '<option value="percentual">Percentual</option>'
                    '<option value="manual">Valor manual</option></select></label>'
                    +'<label>Para percentual/manual, informe linhas como ID=valor ou ID=percentual '
                    '(inclua responsável).<textarea name="parcelas" rows="3" '
                    'placeholder="1=50\n2=50"></textarea></label>'
                    +'<small>IDs: '+', '.join(f'{m["nome"]}={m["id"]}' for m in membros)+'</small>')
                corpo+=_card('Nova conta compartilhada',
                    _form('conta/criar',csrf,compartilhada,'Cadastrar conta compartilhada'))
            elif f:
                corpo+=_card('Conta compartilhada',
                    '<p class="muted">Convide pelo menos mais um integrante para criar '
                    'contas compartilhadas.</p>'+_link('familia','Gerenciar família'))
            else:
                corpo+=_card('Conta compartilhada',
                    '<p class="muted">Crie ou participe de uma família para compartilhar '
                    'contas.</p>'+_link('familia','Gerenciar família'))
            return _render(handler,'Contas a pagar',corpo,user)
        if path.startswith('/auto-financeiro/conta/') and path.rsplit('/',1)[-1].isdigit():
            conta=_resumo_conta(c,int(path.rsplit('/',1)[-1]))
            if not conta or not (conta['responsavel_id']==user['id'] or
                 _permissao_conta(c,conta,user['id'],is_admin) or
                 c.execute('SELECT 1 FROM cotas WHERE conta_id=? AND usuario_id=?',(conta['id'],user['id'])).fetchone()):
                return _fail(handler,'Conta não encontrada.',user,404)
            dono=_permissao_conta(c,conta,user['id'],is_admin)
            cotas=c.execute('SELECT t.*,u.nome FROM cotas t JOIN usuarios u ON u.id=t.usuario_id WHERE conta_id=?',(conta['id'],)).fetchall()
            blocos=[]
            for p in cotas:
                comprovante=_link_doc(user['id'],'cota',f'{conta["id"]}-{p["usuario_id"]}') if p['comprovante'] else ''
                if p['usuario_id']==conta['responsavel_id']:
                    estado='Parte do responsável'
                elif p['confirmado_em']:estado='Pix confirmado'
                elif p['enviado_em']:estado='Aguardando confirmação'
                else:estado='Pendente'
                acao=''
                if not conta['cancelada_em'] or conta['fornecedor_pago_em']:
                    if p['usuario_id']==user['id'] and p['usuario_id']!=conta['responsavel_id'] and not p['enviado_em'] and not p['confirmado_em']:
                        acao=_form(f'conta/{conta["id"]}/enviar',csrf,
                             _html_campo('comprovante','Comprovante do Pix ao responsável',tipo='file',extra='accept="image/png,image/jpeg,application/pdf"'),
                             'Enviar comprovante',multipart=True)
                    if conta['responsavel_id']==user['id'] and p['enviado_em'] and not p['confirmado_em']:
                        acao=_botao(f'conta/{conta["id"]}/confirmar',csrf,'Confirmar Pix recebido',f'<input type="hidden" name="uid" value="{p["usuario_id"]}">')
                blocos.append(_row([esc(p['nome']),reais(p['valor_centavos']),esc(estado),comprovante+acao]))
            resumo=f'<p>Total: <strong>{reais(conta["total_centavos"])}</strong> · Vencimento: {esc(conta["vencimento"])}</p>'
            if conta['familia_id'] is None:
                corpo=_card(conta['descricao'],resumo+
                    '<p class="muted">Conta individual — sem divisão familiar.</p>')
            else:
                corpo=_card(conta['descricao'],resumo+
                    _table(['Integrante','Parte','Situação','Comprovante/Ação'],blocos))
            if user['id']==conta['responsavel_id'] and not conta['fornecedor_pago_em'] and not conta['cancelada_em']:
                corpo+=_card('Pagamento ao fornecedor',_form(f'conta/{conta["id"]}/pagar',csrf,
                    _html_campo('comprovante','Comprovante do pagamento total ao fornecedor',tipo='file',extra='accept="image/png,image/jpeg,application/pdf"'),
                    'Confirmar pagamento ao fornecedor',multipart=True))
            if conta['comprovante_fornecedor']:
                corpo+=_card('Fornecedor',f'Pago em {esc(conta["fornecedor_pago_em"])} · '+_link_doc(user['id'],'fornecedor',conta['id']))
            if dono and not conta['cancelada_em']:
                corpo+=_card('Editar dados da conta',_form(f'conta/{conta["id"]}/editar',csrf,
                    _html_campo('descricao','Descrição',valor=conta['descricao'])
                    +_html_campo('vencimento','Vencimento',tipo='date',valor=conta['vencimento']),
                    'Salvar descrição e vencimento'))
                corpo+=_card('Cancelar conta',_form(f'conta/{conta["id"]}/cancelar',csrf,
                       _html_campo('motivo','Justificativa do cancelamento'),'Cancelar e preservar histórico'))
            if conta['cancelada_em']:
                corpo+=_card('Histórico de cancelamento','Cancelada em '+esc(conta['cancelada_em'])+' · '+esc(conta['motivo_cancelamento']))
            return _render(handler,'Detalhes da conta',cab+corpo,user)
        if path=='/auto-financeiro/emprestimos':
            emprestimos=c.execute('SELECT * FROM emprestimos WHERE credor_id=? OR devedor_id=? ORDER BY id DESC',(user['id'],user['id'])).fetchall()
            linhas=[]
            for e in emprestimos:
                pago=c.execute('SELECT COALESCE(SUM(valor_centavos),0) FROM devolucoes WHERE emprestimo_id=? AND confirmado_em IS NOT NULL',(e['id'],)).fetchone()[0]
                saldo_devedor=e['valor_centavos']-pago
                estado='Não enviado' if not e['confirmado_envio_em'] else 'Quitado' if saldo_devedor==0 else 'Atrasado' if e['vencimento']<date.today().isoformat() else 'Em aberto'
                linhas.append(_row([_link('emprestimo/'+str(e['id']),f'Empréstimo #{e["id"]}'),reais(e['valor_centavos']),reais(saldo_devedor),esc(e['vencimento'] or '-'),esc(estado)]))
            with conn() as other:
                usuarios = _familia_membros(other,f['id']) if f else []
            opcoes=''.join(f'<option value="{x["id"]}">{esc(x["nome"])}</option>' for x in usuarios if x['id']!=user['id'])
            form=_form('emprestimo/criar',csrf,'<label>Tomador do empréstimo<select name="devedor">'+opcoes+'</select></label>'
               +_html_campo('valor','Valor (R$)'),'Registrar empréstimo') if opcoes else '<p>Adicione outro integrante para registrar empréstimos.</p>'
            return _render(handler,'Empréstimos',cab+_card('Seus empréstimos',_table(['Registro','Valor','Restante','Vencimento','Estado'],linhas))+_card('Novo empréstimo sem juros',form),user)
        if path.startswith('/auto-financeiro/emprestimo/') and path.rsplit('/',1)[-1].isdigit():
            e=c.execute('SELECT * FROM emprestimos WHERE id=?',(int(path.rsplit('/',1)[-1]),)).fetchone()
            if not e or user['id'] not in (e['credor_id'],e['devedor_id']):return _fail(handler,'Empréstimo não encontrado.',user,404)
            pago=c.execute('SELECT COALESCE(SUM(valor_centavos),0) FROM devolucoes WHERE emprestimo_id=? AND confirmado_em IS NOT NULL',(e['id'],)).fetchone()[0]
            restante=e['valor_centavos']-pago
            corpo=_card('Situação',f'<p>Principal: {reais(e["valor_centavos"])} · Restante: {reais(restante)} · Vencimento: {esc(e["vencimento"] or "Aguardando envio")}</p>'
                +('Comprovante do envio: '+_link_doc(user['id'],'envio',e['id']) if e['comprovante_envio'] else ''))
            if e['credor_id']==user['id'] and not e['confirmado_envio_em']:
                corpo+=_card('Confirmar que emprestou',_form(f'emprestimo/{e["id"]}/enviar',csrf,
                    _html_campo('comprovante','Comprovante do Pix enviado',tipo='file',extra='accept="image/png,image/jpeg,application/pdf"'),
                    'Confirmar envio',multipart=True))
            if e['devedor_id']==user['id'] and e['confirmado_envio_em'] and restante>0:
                corpo+=_card('Registrar devolução parcial ou total',_form(f'emprestimo/{e["id"]}/devolver',csrf,
                    _html_campo('valor','Valor devolvido (R$)')
                    +_html_campo('comprovante','Comprovante de devolução',tipo='file',extra='accept="image/png,image/jpeg,application/pdf"'),
                    'Enviar comprovante',multipart=True))
            devs=c.execute('SELECT * FROM devolucoes WHERE emprestimo_id=? ORDER BY id DESC',(e['id'],)).fetchall()
            linhas=[]
            for d in devs:
                acao=_link_doc(user['id'],'devolucao',d['id'])
                if user['id']==e['credor_id'] and not d['confirmado_em']:
                    acao+=_botao(f'emprestimo/{e["id"]}/confirmar',csrf,'Confirmar recebimento',f'<input type="hidden" name="devolucao" value="{d["id"]}">')
                linhas.append(_row([reais(d['valor_centavos']),esc(d['enviado_em']),('Confirmado' if d['confirmado_em'] else 'Pendente'),acao]))
            corpo+=_card('Histórico de devoluções',_table(['Valor','Envio','Situação','Comprovante'],linhas))
            return _render(handler,'Empréstimo #'+str(e['id']),cab+corpo,user)
        if path=='/auto-financeiro/bussola':
            periodo=date.today().strftime('%Y-%m')
            r=c.execute('''SELECT tipo,COALESCE(SUM(valor_centavos),0) valor FROM movimentos
                  WHERE usuario_id=? AND criado_em LIKE ? GROUP BY tipo''',(user['id'],periodo+'%')).fetchall()
            linhas=[_row([esc(x['tipo']),reais(x['valor'])]) for x in r]
            return _render(handler,'Bússola · resumo mensal',cab+_card('Movimentações do mês '+periodo,
                  _table(['Categoria','Valor'],linhas)) +'<p class="muted">Sem prometer previsões até ter registros históricos suficientes.</p>',user)
        if path.startswith('/auto-financeiro/comprovante/'):
            partes=path.split('/')
            if len(partes)!=5:return _fail(handler,'Comprovante inválido.',user,404)
            # formato /auto-financeiro/comprovante/<tipo>/<id>
            tipo,ident=partes[3],partes[4]
            nome=None
            if tipo=='fornecedor' and ident.isdigit():
                conta=_resumo_conta(c,int(ident))
                if conta and (conta['responsavel_id']==user['id'] or
                    c.execute('SELECT 1 FROM cotas WHERE conta_id=? AND usuario_id=?',(conta['id'],user['id'])).fetchone()):
                    nome=conta['comprovante_fornecedor']
            if tipo=='cota' and '-' in ident:
                try: cid,uid=map(int,ident.split('-',1))
                except ValueError:cid=uid=0
                conta=_resumo_conta(c,cid)
                if conta and (conta['responsavel_id']==user['id'] or uid==user['id']):
                    row=c.execute('SELECT comprovante FROM cotas WHERE conta_id=? AND usuario_id=?',(cid,uid)).fetchone()
                    nome=row['comprovante'] if row else None
            if tipo=='devolucao' and ident.isdigit():
                row=c.execute('''SELECT d.comprovante,e.credor_id,e.devedor_id FROM devolucoes d
                        JOIN emprestimos e ON e.id=d.emprestimo_id WHERE d.id=?''',(int(ident),)).fetchone()
                if row and user['id'] in (row['credor_id'],row['devedor_id']):nome=row['comprovante']
            if tipo=='envio' and ident.isdigit():
                row=c.execute('SELECT * FROM emprestimos WHERE id=?',(int(ident),)).fetchone()
                if row and user['id'] in (row['credor_id'],row['devedor_id']):
                    nome=row['comprovante_envio']
            if nome and Path(nome).name==nome and (DOCS/nome).is_file():
                mime={'.png':'image/png','.jpg':'image/jpeg','.pdf':'application/pdf'}.get(Path(nome).suffix,'application/octet-stream')
                return handler.send_bytes((DOCS/nome).read_bytes(),mime,filename='comprovante'+Path(nome).suffix)
            return _fail(handler,'Comprovante não encontrado ou acesso negado.',user,404)
        return _fail(handler,'Página não encontrada.',user,404)


def _post_login(handler,path,d):
    if path=='/auto-financeiro/entrar':
        ip=handler.client_address[0]
        with LOCK:
            agora_ts=time.time()
            t=[x for x in TENTATIVAS.get(ip,[]) if agora_ts-x<600]
            if len(t)>=8:return _fail(handler,'Muitas tentativas. Tente novamente mais tarde.',status=429)
        with conn() as c:
            u=c.execute('SELECT * FROM usuarios WHERE email=? AND autoseg_pid IS NULL',(str(d.get('email','')).strip(),)).fetchone()
        if not u or not verificar_senha(str(d.get('senha','')),u['senha_hash']):
            with LOCK:TENTATIVAS[ip]=t+[agora_ts]
            return _fail(handler,'Login ou senha inválidos.',status=401)
        tok=secrets.token_urlsafe(40)
        with LOCK:
            TENTATIVAS.pop(ip,None)
            SESSOES[tok]={'uid':u['id'],'csrf':secrets.token_urlsafe(32),'exp':time.time()+TTL}
        return handler.redir('/auto-financeiro',_cookie(handler,tok))
    if path=='/auto-financeiro/cadastro':
        codigo=str(d.get('codigo','')).strip()
        nome=str(d.get('nome','')).strip()
        email=str(d.get('email','')).strip().lower()
        senha=str(d.get('senha',''))
        if not 2<=len(nome)<=100 or not (5<=len(email)<=200 and '@' in email):
            raise ValueError('Informe nome e e-mail válidos.')
        hash_ = senha_hash(senha)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            invite=c.execute('SELECT * FROM convites WHERE codigo=? AND usado_por IS NULL',(codigo,)).fetchone()
            if not invite or invite['expira_em']<agora():raise ValueError('Convite expirado ou inválido.')
            cur=c.execute('INSERT INTO usuarios(nome,email,senha_hash,familia_id,criado_em) VALUES(?,?,?,?,?)',
                (nome,email,hash_,invite['familia_id'],agora()))
            c.execute('UPDATE convites SET usado_por=? WHERE codigo=? AND usado_por IS NULL',(cur.lastrowid,codigo))
            auditoria(c,cur.lastrowid,'Ingresso na família',str(invite['familia_id']))
        return handler.redir('/auto-financeiro/entrar')
    return None


def _dinheiro_positivo(d,chave='valor'):
    cents=centavos(d.get(chave,''))
    if cents<=0:raise ValueError('O valor precisa ser maior que zero.')
    return cents


def _autorizar_conta(c,cid,uid,admin=False):
    ct=_resumo_conta(c,cid)
    if not ct:raise ValueError('Conta não encontrada.')
    if not _permissao_conta(c,ct,uid,admin):raise PermissionError('Ação restrita ao responsável ou administrador.')
    return ct


def _dividir(total,ids,resp,modo,raw):
    ids=sorted(set(ids)|{resp})
    if not ids:raise ValueError('Selecione os integrantes.')
    if modo=='igual':
        v,r=divmod(total,len(ids))
        return {k:v+(r if k==resp else 0) for k in ids}
    if modo not in ('manual','percentual'):raise ValueError('Modo de divisão inválido.')
    pares={}
    for linha in str(raw).splitlines():
        if not linha.strip():continue
        try:k,val=linha.split('=',1); k=int(k.strip())
        except (ValueError,TypeError):raise ValueError('Formato da divisão: ID=valor, uma linha por pessoa.')
        if k not in ids or k in pares:raise ValueError('IDs inválidos ou repetidos na divisão.')
        pares[k]=centavos(val) if modo=='manual' else Decimal(val.replace(',','.'))
    if set(pares)!=set(ids):raise ValueError('Informe a parcela de todos os integrantes, incluindo o responsável.')
    if modo=='percentual':
        if sum(pares.values())!=100:raise ValueError('Percentuais devem somar exatamente 100%.')
        vals={i:int((Decimal(total)*v/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) for i,v in pares.items()}
        vals[resp]+=total-sum(vals.values())
    else:vals=pares
    if any(v<0 for v in vals.values()) or sum(vals.values())!=total:
        raise ValueError('Partes não podem ser negativas e devem somar o valor total.')
    return vals


def POST(handler,path,prestador,banco,d):
    if path in ('/auto-financeiro/entrar','/auto-financeiro/cadastro'):
        return _post_login(handler,path,d)
    user,csrf=_principal(handler,prestador)
    if not user:raise PermissionError('Faça login antes de registrar movimentações.')
    if not secrets.compare_digest(str(d.get('csrf','')),str(csrf)):
        raise PermissionError('Sessão inválida ou formulário expirado.')
    uid=user['id']
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        f=_familia(c,user)
        admin=bool(f and f['admin_id']==uid)
        if path=='/auto-financeiro/movimento':
            txt=str(d.get('descricao','')).strip()[:200]
            valor=_dinheiro_positivo(d)
            tipo=d.get('tipo')
            if not txt or tipo not in ('receita','despesa'):raise ValueError('Descrição e tipo são obrigatórios.')
            movimento(c,uid,valor if tipo=='receita' else -valor,txt,tipo)
            auditoria(c,uid,'Movimento manual',tipo)
        elif path=='/auto-financeiro/movimento/estornar':
            mid=int(d.get('id','0'))
            old=c.execute('SELECT * FROM movimentos WHERE id=? AND usuario_id=?',(mid,uid)).fetchone()
            if not old or old['tipo'] not in ('receita','despesa'):
                raise PermissionError('Somente lançamentos manuais próprios podem ser estornados.')
            orig=f'estorno:{mid}'
            if c.execute('SELECT 1 FROM movimentos WHERE usuario_id=? AND origem_chave=?',(uid,orig)).fetchone():
                raise ValueError('Este lançamento já foi estornado.')
            movimento(c,uid,-old['valor_centavos'],f'Estorno: {old["descricao"]}', 'estorno', orig)
            auditoria(c,uid,'Estorno manual',str(mid))
        elif path=='/auto-financeiro/salario/novo':
            txt=str(d.get('descricao','')).strip()[:100]; val=_dinheiro_positivo(d)
            dia=int(d.get('dia','0'))
            if not txt or not 1<=dia<=31:raise ValueError('Descrição e dia devem ser válidos.')
            c.execute('INSERT INTO salarios(usuario_id,descricao,valor_centavos,dia,criado_em) VALUES(?,?,?,?,?)',
                (uid,txt,val,dia,agora()))
            auditoria(c,uid,'Salário cadastrado',txt)
        elif path=='/auto-financeiro/salario/confirmar':
            sid=int(d.get('id','0'));periodo=date.today().strftime('%Y-%m')
            s=c.execute('SELECT * FROM salarios WHERE id=? AND usuario_id=? AND ativo=1',(sid,uid)).fetchone()
            if not s:raise PermissionError('Salário não encontrado.')
            cur=c.execute('INSERT OR IGNORE INTO salarios_recebidos(salario_id,periodo,confirmado_em) VALUES(?,?,?)',(sid,periodo,agora()))
            if cur.rowcount:
                movimento(c,uid,s['valor_centavos'],s['descricao']+' · '+periodo,'salario',f'salario:{sid}:{periodo}')
                auditoria(c,uid,'Recebimento de salário confirmado',periodo)
        elif path=='/auto-financeiro/familia/criar':
            if f:raise ValueError('Você já participa de uma família.')
            nome=str(d.get('nome','')).strip()[:100]
            if len(nome)<2:raise ValueError('Informe um nome para a família.')
            cur=c.execute('INSERT INTO familias(nome,admin_id,criado_em) VALUES(?,?,?)',(nome,uid,agora()))
            c.execute('UPDATE usuarios SET familia_id=? WHERE id=?',(cur.lastrowid,uid))
            auditoria(c,uid,'Família criada',nome)
        elif path=='/auto-financeiro/familia/convidar':
            if not admin:raise PermissionError('Apenas o administrador cria convites.')
            codigo=secrets.token_urlsafe(18)
            c.execute('INSERT INTO convites(codigo,familia_id,expira_em) VALUES(?,?,?)',
                (codigo,f['id'],(datetime.now()+timedelta(days=1)).isoformat(timespec='seconds')))
            auditoria(c,uid,'Convite gerado')
        elif path=='/auto-financeiro/familia/transferir':
            if not admin:raise PermissionError('Somente o administrador pode transferir.')
            novo=int(d.get('uid','0'))
            if novo==uid or not c.execute('SELECT 1 FROM usuarios WHERE id=? AND familia_id=?',(novo,f['id'])).fetchone():
                raise ValueError('Novo administrador precisa ser outro integrante ativo.')
            c.execute("UPDATE transferencias_admin SET estado='cancelada' WHERE familia_id=? AND estado='pendente'",(f['id'],))
            c.execute('INSERT INTO transferencias_admin(familia_id,de_id,para_id,solicitado_em) VALUES(?,?,?,?)',
                (f['id'],uid,novo,agora()))
            auditoria(c,uid,'Administração oferecida',str(novo))
        elif path=='/auto-financeiro/familia/aceitar-admin':
            if not f:raise PermissionError('Sem família ativa.')
            pedido=c.execute('''SELECT * FROM transferencias_admin WHERE id=? AND familia_id=?
                      AND para_id=? AND estado='pendente' ''',(int(d.get('pedido_id','0')),f['id'],uid)).fetchone()
            if not pedido or f['admin_id']!=pedido['de_id']:
                raise ValueError('Transferência não autorizada ou já concluída.')
            c.execute('UPDATE familias SET admin_id=? WHERE id=?',(uid,f['id']))
            c.execute("UPDATE transferencias_admin SET estado='aceita',aceito_em=? WHERE id=?",(agora(),pedido['id']))
            c.execute("UPDATE transferencias_admin SET estado='cancelada' WHERE familia_id=? AND estado='pendente'",(f['id'],))
            auditoria(c,uid,'Administração aceita',str(pedido['de_id']))
        elif path=='/auto-financeiro/familia/sair':
            if not f:raise ValueError('Você não participa de uma família.')
            if admin:raise PermissionError('Transfira a administração antes de sair.')
            if _pendencias_familia(c,uid,f['id']):
                raise ValueError('Não é possível sair com contas ou empréstimos pendentes.')
            c.execute('UPDATE usuarios SET familia_id=NULL WHERE id=?',(uid,))
            auditoria(c,uid,'Saída voluntária da família',str(f['id']))
        elif path=='/auto-financeiro/familia/remover':
            if not admin:raise PermissionError('Somente o administrador remove membros.')
            outro=int(d.get('uid','0'))
            motivo=str(d.get('motivo','')).strip()
            if outro==uid or not c.execute('SELECT 1 FROM usuarios WHERE id=? AND familia_id=?',(outro,f['id'])).fetchone():
                raise ValueError('Integrante inválido.')
            if not 3<=len(motivo)<=500:raise ValueError('Motivo obrigatório para remover (3 a 500 caracteres).')
            c.execute('UPDATE usuarios SET familia_id=NULL WHERE id=?',(outro,))
            c.execute("UPDATE transferencias_admin SET estado='cancelada' WHERE familia_id=? AND estado='pendente'",(f['id'],))
            auditoria(c,uid,'Remoção administrativa',f'usuario={outro}; motivo={motivo}')
        elif path=='/auto-financeiro/conta/criar':
            titulo=str(d.get('descricao','')).strip()[:150]
            total=_dinheiro_positivo(d)
            vencimento=date.fromisoformat(str(d.get('vencimento',''))).isoformat()
            if not titulo:raise ValueError('Descrição da conta é obrigatória.')
            selecionados=d.get('participantes[]',[])
            if isinstance(selecionados,str):selecionados=[selecionados]
            ids=[int(x) for x in selecionados]
            tipo=str(d.get('tipo','') or '').strip().lower()
            if tipo not in ('individual','compartilhada'):
                tipo='compartilhada' if (f and ids) else 'individual'
            if tipo=='compartilhada':
                if not f:
                    raise PermissionError('Crie ou participe de uma família para compartilhar contas.')
                members={x['id'] for x in _familia_membros(c,f['id'])}
                if any(x not in members for x in ids):
                    raise PermissionError('Integrante não pertence à família.')
                ids=[x for x in ids if x!=uid]
                if not ids:
                    raise ValueError('Selecione ao menos um participante para a conta compartilhada.')
                familia_id=f['id']
            else:
                ids=[]
                familia_id=None
            parcelas=_dividir(total,ids,uid,str(d.get('divisao','igual')),d.get('parcelas',''))
            cur=c.execute('INSERT INTO contas(responsavel_id,familia_id,descricao,total_centavos,vencimento,criada_em) VALUES(?,?,?,?,?,?)',
                (uid,familia_id,titulo,total,vencimento,agora()))
            for mid,cents in parcelas.items():
                c.execute('INSERT INTO cotas(conta_id,usuario_id,valor_centavos) VALUES(?,?,?)',
                    (cur.lastrowid,mid,cents))
            auditoria(c,uid,'Conta cadastrada',f'{cur.lastrowid}: {titulo}')
        elif path.startswith('/auto-financeiro/conta/'):
            parts=path.split('/')
            if len(parts)!=5:raise ValueError('Ação inválida.')
            cid=int(parts[3]);action=parts[4]
            conta=_resumo_conta(c,cid)
            if not conta:raise ValueError('Conta não encontrada.')
            dono=_permissao_conta(c,conta,uid,admin)
            if action=='pagar':
                if uid != conta['responsavel_id']:raise PermissionError('Somente o responsável confirma o pagamento ao fornecedor.')
                if conta['fornecedor_pago_em'] or conta['cancelada_em']:raise ValueError('Conta já paga ou cancelada.')
                comprovante=documento_upload(d.get('comprovante'),'comprovante')
                c.execute('UPDATE contas SET fornecedor_pago_em=?,comprovante_fornecedor=? WHERE id=?',
                    (agora(),comprovante,cid))
                # O débito é do responsável financeiro, independentemente de quem administra a família.
                movimento(c,conta['responsavel_id'],-conta['total_centavos'],
                    f'Conta {conta["descricao"]} · fornecedor','conta_fornecedor',f'conta:{cid}:fornecedor')
                auditoria(c,uid,'Pagamento ao fornecedor',str(cid))
            elif action=='enviar':
                if uid==conta['responsavel_id']:raise PermissionError('O responsável não envia Pix a si mesmo.')
                part=c.execute('SELECT * FROM cotas WHERE conta_id=? AND usuario_id=?',(cid,uid)).fetchone()
                if not part or part['enviado_em'] or part['confirmado_em'] or conta['cancelada_em'] and not conta['fornecedor_pago_em']:
                    raise ValueError('Contribuição indisponível ou já registrada.')
                comprob=documento_upload(d.get('comprovante'),'comprovante')
                c.execute('UPDATE cotas SET comprovante=?,enviado_em=? WHERE conta_id=? AND usuario_id=?',
                    (comprob,agora(),cid,uid))
                auditoria(c,uid,'Comprovante de Pix enviado',str(cid))
            elif action=='confirmar':
                if uid!=conta['responsavel_id']:raise PermissionError('Somente o responsável confirma o Pix.')
                mid=int(d.get('uid','0'))
                p=c.execute('SELECT * FROM cotas WHERE conta_id=? AND usuario_id=?',(cid,mid)).fetchone()
                if not p or not p['enviado_em'] or p['confirmado_em']:raise ValueError('Comprovante ausente ou contribuição já confirmada.')
                c.execute('UPDATE cotas SET confirmado_em=? WHERE conta_id=? AND usuario_id=?',(agora(),cid,mid))
                movimento(c,mid,-p['valor_centavos'],f'Pix para {user["nome"]} · {conta["descricao"]}',
                          'transferencia_familiar',f'conta:{cid}:cota:{mid}:saida')
                movimento(c,uid,p['valor_centavos'],f'Contribuição recebida · {conta["descricao"]}',
                          'transferencia_familiar',f'conta:{cid}:cota:{mid}:entrada')
                auditoria(c,uid,'Pix familiar confirmado',f'{cid}/{mid}')
            elif action=='editar':
                if not dono:raise PermissionError('Somente o criador ou administrador pode editar a conta.')
                if conta['cancelada_em']:raise ValueError('Conta cancelada não pode ser editada.')
                desc=str(d.get('descricao','')).strip()[:150]
                venc=date.fromisoformat(str(d.get('vencimento',''))).isoformat()
                if not desc:raise ValueError('Descrição é obrigatória.')
                c.execute('UPDATE contas SET descricao=?,vencimento=? WHERE id=?',(desc,venc,cid))
                auditoria(c,uid,'Dados de conta editados',str(cid))
            elif action=='cancelar':
                if not dono:raise PermissionError('Somente criador ou administrador cancela.')
                if conta['cancelada_em']:raise ValueError('Conta já cancelada.')
                motivo=str(d.get('motivo','')).strip()
                if len(motivo)<3 or len(motivo)>500:raise ValueError('Motivo obrigatório (3 a 500 caracteres).')
                c.execute('UPDATE contas SET cancelada_em=?,motivo_cancelamento=? WHERE id=?',(agora(),motivo,cid))
                auditoria(c,uid,'Cancelamento inteligente',f'conta {cid}: {motivo}')
            else:raise ValueError('Ação de conta desconhecida.')
        elif path=='/auto-financeiro/emprestimo/criar':
            other=int(d.get('devedor','0'));valor=_dinheiro_positivo(d)
            if not f or other==uid or not c.execute('SELECT 1 FROM usuarios WHERE id=? AND familia_id=?',(other,f['id'])).fetchone():
                raise PermissionError('Empréstimo permitido apenas entre usuários cadastrados da família.')
            cur=c.execute('INSERT INTO emprestimos(credor_id,devedor_id,valor_centavos,criado_em) VALUES(?,?,?,?)',
                (uid,other,valor,agora()))
            auditoria(c,uid,'Empréstimo criado',str(cur.lastrowid))
        elif path.startswith('/auto-financeiro/emprestimo/'):
            partes=path.split('/')
            if len(partes)!=5:raise ValueError('Ação inválida.')
            lid=int(partes[3]);acao=partes[4]
            e=c.execute('SELECT * FROM emprestimos WHERE id=?',(lid,)).fetchone()
            if not e:raise ValueError('Empréstimo não encontrado.')
            ja_pago=c.execute('SELECT COALESCE(SUM(valor_centavos),0) FROM devolucoes WHERE emprestimo_id=? AND confirmado_em IS NOT NULL',(lid,)).fetchone()[0]
            a_confirmar=c.execute('SELECT COALESCE(SUM(valor_centavos),0) FROM devolucoes WHERE emprestimo_id=? AND confirmado_em IS NULL',(lid,)).fetchone()[0]
            if acao=='enviar':
                if uid!=e['credor_id'] or e['confirmado_envio_em']:raise PermissionError('Envio já confirmado ou usuário não autorizado.')
                nome=documento_upload(d.get('comprovante'),'comprovante')
                momento=agora();venc=(date.today()+timedelta(days=30)).isoformat()
                c.execute('UPDATE emprestimos SET confirmado_envio_em=?,comprovante_envio=?,vencimento=? WHERE id=?',(momento,nome,venc,lid))
                movimento(c,e['credor_id'],-e['valor_centavos'],f'Empréstimo #{lid} enviado','emprestimo',f'emprestimo:{lid}:credor')
                movimento(c,e['devedor_id'],e['valor_centavos'],f'Empréstimo #{lid} recebido','emprestimo',f'emprestimo:{lid}:devedor')
                auditoria(c,uid,'Envio de empréstimo confirmado',str(lid))
            elif acao=='devolver':
                if uid!=e['devedor_id'] or not e['confirmado_envio_em']:raise PermissionError('Devolução não permitida.')
                valor=_dinheiro_positivo(d)
                if valor>e['valor_centavos']-ja_pago-a_confirmar:raise ValueError('Devolução excede o saldo pendente.')
                nome=documento_upload(d.get('comprovante'),'comprovante')
                c.execute('INSERT INTO devolucoes(emprestimo_id,valor_centavos,comprovante,enviado_em) VALUES(?,?,?,?)',(lid,valor,nome,agora()))
                auditoria(c,uid,'Comprovante de devolução enviado',str(lid))
            elif acao=='confirmar':
                if uid!=e['credor_id']:raise PermissionError('Somente o credor confirma recebimento.')
                did=int(d.get('devolucao','0'))
                dev=c.execute('SELECT * FROM devolucoes WHERE id=? AND emprestimo_id=?',(did,lid)).fetchone()
                if not dev or dev['confirmado_em']:raise ValueError('Devolução não encontrada ou já confirmada.')
                c.execute('UPDATE devolucoes SET confirmado_em=? WHERE id=?',(agora(),did))
                movimento(c,e['devedor_id'],-dev['valor_centavos'],f'Devolução empréstimo #{lid}','devolucao',f'devolucao:{did}:devedor')
                movimento(c,e['credor_id'],dev['valor_centavos'],f'Recebimento empréstimo #{lid}','devolucao',f'devolucao:{did}:credor')
                auditoria(c,uid,'Devolução confirmada',str(did))
            else:raise ValueError('Ação de empréstimo inválida.')
        else:raise ValueError('Rota desconhecida.')
    if path.startswith('/auto-financeiro/conta/') and path.rsplit('/',1)[-1] in ('pagar','enviar','confirmar','cancelar','editar'):
        destino=f'/auto-financeiro/conta/{cid}'
    elif path.startswith('/auto-financeiro/emprestimo/') and path.rsplit('/',1)[-1] in ('enviar','devolver','confirmar'):
        destino=f'/auto-financeiro/emprestimo/{lid}'
    elif path.startswith('/auto-financeiro/salario/'):
        destino='/auto-financeiro/salarios'
    elif path.startswith('/auto-financeiro/movimento/'):
        destino='/auto-financeiro/extrato'
    elif path.startswith('/auto-financeiro/familia/'):
        destino='/auto-financeiro/familia'
    elif path=='/auto-financeiro/conta/criar':
        destino='/auto-financeiro/contas'
    elif path=='/auto-financeiro/emprestimo/criar':
        destino='/auto-financeiro/emprestimos'
    else:
        destino='/auto-financeiro'
    return handler.redir(destino)
