"""AUTOSEG — Portal web completo de prestadores (v4).

Mesmas funções de negócios do desktop: clientes, OS, materiais, imagens, PDF,
financeiro, e-mail (rascunho) e NFS-e (rascunho). Cadastro de prestadores
exclusivo do desktop. Por padrão, escuta APENAS em 127.0.0.1.
"""
import html
import json
import logging
from logging.handlers import RotatingFileHandler
import mimetypes
import os
import secrets
import threading
import time
from decimal import Decimal
from email.parser import BytesParser
from email.policy import default
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, quote, urlencode as urllib_parse_urlencode
import prestadores_ext as ext
import portal_negocios as neg
import fluxo_os as fluxo
import atendimento_os as aten
import cadastros_v9 as cad9
import portal_v9 as v9
import links_publicos as links9
import socket

LOG = logging.getLogger('autosseg.portal')
VERSAO_PORTAL = '9.6.0'
SESSOES = {}
TENTATIVAS = {}
LOCK_DOCS = threading.Lock()
LOCK_LOGIN = threading.Lock()
MAX_POST = 90 * 1024 * 1024


def esc(s):
    return html.escape(str(s if s is not None else ''), quote=True)


def dinheiro(v):
    return neg.dinheiro(v)


def campos_escuros(caption, name, value='', required=False, kind='text', placeholder='', readonly=False):
    return (f'<label for="c_{esc(name)}">{esc(caption)}</label>'
            f'<input id="c_{esc(name)}" type="{esc(kind)}" name="{esc(name)}" value="{esc(value)}" '
            f'placeholder="{esc(placeholder)}" {"required" if required else ""} {"readonly" if readonly else ""}>')


def textarea(caption,name,value='',rows=4,required=False):
    return f'<label for="c_{esc(name)}">{esc(caption)}</label><textarea id="c_{esc(name)}" name="{esc(name)}" rows="{int(rows)}" {"required" if required else ""}>{esc(value)}</textarea>'


def select(caption,name,items,value='',required=False):
    opts=''.join(f'<option value="{esc(k)}" {"selected" if str(value)==str(k) else ""}>{esc(v)}</option>' for k,v in items)
    return f'<label for="c_{esc(name)}">{esc(caption)}</label><select id="c_{esc(name)}" name="{esc(name)}" {"required" if required else ""}>{opts}</select>'


def botao(txt,href,kind=''):
    return f'<a class="btn {esc(kind)}" href="{esc(href)}">{esc(txt)}</a>'


def card(titulo,conteudo):
    return f'<section class="card"><h2>{esc(titulo)}</h2>{conteudo}</section>'


def tabela(headers, rows):
    if not rows:
        return '<p class="muted">Nenhum registro encontrado.</p>'
    return '<div class="table-scroll"><table><thead><tr>'+''.join(f'<th>{esc(h)}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{x}</td>' for x in cells)+'</tr>' for cells in rows)+'</tbody></table></div>'


def layout(titulo,corpo,usuario=None,nonce=None):
    menus=[('/','Início'),('/clientes','Clientes'),('/os','Ordens de serviço'),('/financeiro','Financeiro'),('/notas','Notas fiscais'),('/emails','E-mails'),('/historico','Histórico e relatórios')]
    nav=(''.join(f'<a href="{url}">{esc(nome)}</a>' for url,nome in menus[:3])
         +'<details class="nav-more"><summary>Mais opções</summary>'
         +''.join(f'<a href="{url}">{esc(nome)}</a>' for url,nome in menus[3:])+'</details>') if usuario else ''
    us=f'<span class="usuario">{esc(usuario["nome"])} · Prestador</span>' if usuario else ''
    footer='''<footer>Relatórios PDF disponíveis para download. E-mail e NFS-e: rascunhos; sem transmissão por API.</footer>'''
    logout=(f'<form method="post" action="/sair" class="logout"><input type="hidden" name="csrf" value="{esc(usuario["csrf"])}">'
            '<button class="subtle">Sair</button></form>') if usuario else ''
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(titulo)} · AUTOSEG</title><style>
:root{{--yellow:#ffd400;--bg:#080808;--card:#191919;--border:#424242;--muted:#bababa;--green:#52edb2;--red:#ff7d7d}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:#fff;font:16px -apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;line-height:1.45}}
a{{color:var(--yellow)}}header{{background:#171717;border-bottom:3px solid var(--yellow)}}.top{{max-width:1240px;margin:auto;display:flex;gap:14px;align-items:center;flex-wrap:wrap;padding:12px 18px}}
.brand{{color:var(--yellow);font-size:26px;font-weight:900;letter-spacing:.3px;text-decoration:none}}.tagline{{color:#ddd;font-size:13px}}
.nav{{display:flex;gap:6px;flex-wrap:wrap;max-width:1240px;margin:auto;padding:0 18px 13px}}.nav a{{color:#fff;text-decoration:none;border:1px solid #414141;padding:10px 13px;border-radius:8px;font-weight:650}}.nav a:hover{{background:var(--yellow);color:#101010}}.nav-more{{position:relative;z-index:2;border:1px solid #414141;border-radius:8px;padding:9px 13px}}.nav-more summary{{cursor:pointer;font-weight:650}}.nav-more[open]{{background:#232323}}.nav-more a{{display:block;margin:8px 0}}
main{{max-width:1240px;margin:20px auto;padding:0 18px 50px}}h1{{font-size:clamp(22px,4vw,32px);margin:14px 0}}h2{{font-size:21px;margin:0 0 15px}}h3{{font-size:17px;margin:10px 0}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin:15px 0}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:13px}}.grid .card{{margin:0}}
label{{display:block;margin:13px 0 5px;font-weight:650}}input,textarea,select{{width:100%;font:inherit;color:#fff;background:#090909;border:1.5px solid #989898;border-radius:7px;padding:10px;max-width:100%}}
input:focus,textarea:focus,select:focus{{outline:2px solid var(--yellow)}}input[type=file]{{padding:12px}}input[type=checkbox]{{width:auto}}
button,.btn{{display:inline-block;border-radius:8px;font:bold 15px Arial;padding:13px 16px;cursor:pointer;color:#161616;background:var(--yellow);border:1px solid var(--yellow);text-decoration:none;margin:4px 5px 4px 0;min-height:44px}}
button.secondary,.btn.secondary{{background:#262626;border-color:#9b9b9b;color:#fff}}button.danger,.btn.danger{{background:#451b1b;color:#fff;border-color:#b75151}}button.subtle{{background:transparent;color:#fff;border:1px solid #777}}
.usuario{{color:#ddd;font-size:13px}}.logout{{margin:0 0 0 auto}}.muted,small{{color:var(--muted)}}.good{{color:var(--green)}}.warn{{color:#ffce79}}.bad{{color:var(--red)}}.tag{{background:#4a400c;color:#ffe678;border-radius:6px;padding:4px 9px;font-size:13px;white-space:nowrap}}
.table-scroll{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;min-width:640px}}th,td{{border-bottom:1px solid #414141;padding:12px 10px;text-align:left;vertical-align:top}}th{{color:var(--yellow);background:#222}}.col2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:15px}}.actions{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}}.kpi{{background:#171717;border:1px solid #444;padding:17px;border-radius:10px}}.kpi strong{{display:block;font-size:26px;color:var(--yellow)}}.kpi span{{font-size:13px;color:var(--muted)}}
fieldset{{border:1px solid #444;border-radius:10px;padding:14px;margin:14px 0}}legend{{color:var(--yellow);font-weight:800;padding:0 9px}}.material-row{{display:grid;grid-template-columns:minmax(130px,3fr) minmax(85px,1fr) minmax(110px,1fr) auto;gap:8px;align-items:end;margin:7px 0}}.material-row label{{font-size:12px;margin:0}}.material-row input{{width:100%}}
.flash{{background:#163c29;border:1px solid #67e2a8;padding:13px;border-radius:8px}}.notice{{background:#3e320e;border:1px solid #937d2f;border-radius:9px;padding:13px}}.stack{{display:flex;gap:8px;flex-wrap:wrap}}.stack form{{display:inline}}.pic{{display:inline-block;padding:8px 12px;border:1px solid #555;border-radius:6px;margin:4px}}footer{{color:#999;padding:20px;text-align:center;border-top:1px solid #292929;font-size:13px}}
@media(max-width:620px){{.material-row{{grid-template-columns:1fr 1fr}}.material-row>div:first-child{{grid-column:1/-1}}.nav a{{font-size:13px;padding:9px}}.top{{padding:12px}}main{{padding:0 12px}}}}
</style><script src="/static/portal.js" defer></script></head><body><header><div class="top"><a class="brand" href="/">AUTOSEG</a><span class="tagline">AUTOMAÇÃO E SEGURANÇA · Portal de Serviços</span>{us}{logout}</div><nav class="nav">{nav}</nav></header><main><h1>{esc(titulo)}</h1>{corpo}</main>{footer}</body></html>'''


class PortalPrestador:
    def __init__(self,banco,host=None,porta=8766):
        self.banco=banco
        self.host=host or os.environ.get('PRESTADOR_BIND','127.0.0.1')
        self.porta=int(os.environ.get('PRESTADOR_PORT',porta))
        self.servidor=None
        self.thread=None

    def iniciar(self):
        banco=self.banco
        # Mantém erros consultáveis mesmo quando o app é iniciado por um .command.
        if not any(isinstance(h,RotatingFileHandler) for h in LOG.handlers):
            try:
                pasta=Path(__file__).resolve().parent/'logs'
                pasta.mkdir(parents=True,exist_ok=True)
                arquivo=pasta/'portal_prestador.log'
                arq_log=RotatingFileHandler(arquivo,maxBytes=2_000_000,backupCount=3,
                                            encoding='utf-8')
                arq_log.setLevel(logging.WARNING)
                arq_log.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
                LOG.setLevel(logging.WARNING)
                LOG.addHandler(arq_log)
                if os.name=='posix':os.chmod(arquivo,0o600)
            except OSError as exc:
                LOG.warning('Não foi possível iniciar log de arquivo: %s',exc)
        usar_https=os.environ.get('PRESTADOR_HTTPS')=='1' 
        ext.instalar(banco)
        fluxo.instalar(banco)
        aten.instalar(banco)
        cad9.instalar(banco)
        try:
            importados=fluxo.recuperar_relatorios_antigos(banco)
            if importados:
                LOG.warning('PDFs históricos recuperados: %s',len(importados))
        except Exception:
            LOG.exception('Falha ao recuperar PDFs históricos; a operação web continuará.')
        with ext.db(banco) as c: neg.criar_auditoria(c)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self,formato,*args):
                LOG.info('%s %s',self.address_string(),formato%args)

            def send_bytes(self,data,mime='text/html; charset=utf-8',filename=None,status=200,cookie=None):
                self.send_response(status)
                self.send_header('Content-Type',mime)
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store, max-age=0')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('X-Frame-Options','DENY')
                self.send_header('Referrer-Policy','no-referrer')
                self.send_header('X-AUTOSEG-Portal',VERSAO_PORTAL)
                self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; img-src 'self'")
                if filename:
                    fname=Path(filename).name
                    # RFC5987 evita injeção no cabeçalho; usa somente nome limpo.
                    self.send_header('Content-Disposition',f"attachment; filename*=UTF-8''{quote(fname)}")
                if cookie:self.send_header('Set-Cookie',cookie)
                self.end_headers();self.wfile.write(data)

            def responder(self,html_text,status=200,cookie=None):
                return self.send_bytes(html_text.encode('utf-8'),status=status,cookie=cookie)

            def pagina(self,titulo,conteudo,s=None,status=200):
                pagina=layout(titulo,conteudo,s)
                if titulo=='Ordens de serviço abertas e pendentes':
                    pagina=pagina.replace('</head>','<meta http-equiv="refresh" content="20"></head>')
                return self.responder(pagina,status)

            def cookie(self,tok,delete=False):
                attrs='Path=/; HttpOnly; SameSite=Strict; '
                if usar_https or self.headers.get('CF-Ray') or self.headers.get('X-Forwarded-Proto','').lower()=='https':attrs+='Secure; '
                return f'autosseg_session={tok}; {attrs}Max-Age={0 if delete else 28800}'

            def redir(self,path,cookie=None):
                if not path.startswith('/') or path.startswith('//'): path='/'
                self.send_response(303)
                self.send_header('Location',path)
                self.send_header('Cache-Control','no-store')
                if cookie: self.send_header('Set-Cookie',cookie)
                self.end_headers()

            def sessao(self):
                try:
                    cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
                    tok=cookie['autosseg_session'].value
                except (ValueError,KeyError):return None
                s=SESSOES.get(tok)
                if not s or s['exp']<time.time():
                    SESSOES.pop(tok,None);return None
                with ext.db(banco) as c:
                    p=c.execute('SELECT nome FROM prestadores WHERE id=? AND ativo=1',(s['pid'],)).fetchone()
                if not p:
                    SESSOES.pop(tok,None);return None
                s['admin']=cad9.prestador_admin(banco,s['pid'])
                return s

            def csrf(self,s,d):
                if not s or not secrets.compare_digest(s['csrf'],str(d.get('csrf',''))):
                    raise PermissionError('Formulário expirado ou sessão inválida.')

            def hidden(self,s):
                return f'<input type="hidden" name="csrf" value="{esc(s["csrf"])}">'

            def form(self):
                try:t=int(self.headers.get('Content-Length','0'))
                except ValueError: raise ValueError('Tamanho inválido.')
                if not (0<t<=MAX_POST): raise ValueError('O envio deve ter no máximo 90 MB no total.')
                ct=self.headers.get('Content-Type','')
                raw=self.rfile.read(t)
                if ct.startswith('multipart/form-data'):
                    msg=BytesParser(policy=default).parsebytes(
                        ('Content-Type: '+ct+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
                    d={}
                    for part in msg.iter_parts():
                        nome=part.get_param('name',header='Content-Disposition')
                        if not nome:continue
                        valor=(part.get_filename(),part.get_payload(decode=True)) if part.get_filename() else part.get_payload(decode=True).decode('utf-8')
                        if nome.endswith('[]'):d.setdefault(nome,[]).append(valor)
                        else:d[nome]=valor
                    return d
                if ct.startswith('application/x-www-form-urlencoded'):
                    parsed=parse_qs(raw.decode('utf-8'),keep_blank_values=True,max_num_fields=400)
                    return {k:(v if k.endswith('[]') else v[0]) for k,v in parsed.items()}
                raise ValueError('Formato de formulário não suportado.')

            def erro(self,msg,status=400,s=None):
                return self.pagina('Operação não concluída',card('Aviso',f'<p class="bad">{esc(msg)}</p><p><a href="/">Voltar ao início</a></p>'),s,status)

            def login(self):
                return self.pagina('Acesso do prestador',card('Entrar',
                    '<form method="post" action="/login">'
                    +campos_escuros('E-mail','email',kind='email',required=True)
                    +campos_escuros('Senha','senha',kind='password',required=True)
                    +'<button type="submit">Entrar</button></form>'
                    '<p class="muted">O cadastro de prestadores é realizado somente pelo aplicativo desktop.</p>')+v9.barra_links('prestador'))

            def os_lista(self,s,concluidas=False):
                if concluidas:
                    with ext.db(banco) as c:
                        lista=c.execute('''SELECT o.id,o.numero_os,o.status,o.descricao,o.data_abertura,
                            o.valor_total,cl.nome cliente,MAX(d.versao) versao
                            FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id
                            LEFT JOIN os_documentos d ON d.os_id=o.id AND d.tipo='relatorio_pdf'
                            WHERE o.status NOT IN ('Aberta','Pendente')
                            GROUP BY o.id ORDER BY o.id DESC LIMIT 500''').fetchall()
                    rows=[]
                    for x in lista:
                        link_pdf=(botao('Baixar PDF',f'/os/{x["id"]}/pdf') if x['versao'] else
                            '<span class="warn">Não publicado</span> '+botao('Abrir para republicar',f'/os/{x["id"]}','secondary'))
                        rows.append((f'<a href="/os/{x["id"]}">{esc(x["numero_os"])}</a>',esc(x['cliente']),
                            f'<span class="tag">{esc(x["status"])}</span>',dinheiro(x['valor_total']),
                            str(x['versao'] or '—'),link_pdf))
                    resumo=f'<p class="muted">Ordens encerradas, relatórios publicados e PDFs centralizados. Anexos só durante o encerramento da OS.</p>'
                    return self.pagina('Histórico e relatórios',resumo+card('Histórico e documentos',
                        tabela(['OS','Cliente','Situação','Valor','Versão PDF','Documento'],rows)),s)
                lista=ext.listar_os_compartilhadas(banco)
                rows=[]
                for x in lista:
                    rows.append((f'<a href="/os/{x["id"]}">{esc(x["numero_os"])}</a>',esc(x['cliente']),
                        f'<span class="tag">{esc(x["status"])}</span>',esc(x.get('responsavel') or 'Não atribuído'),
                        esc(x.get('participantes') or 'Nenhum')))
                return self.pagina('Ordens de serviço abertas e pendentes',
                    '<p class="muted">Todos os prestadores veem as OS abertas e pendentes, mesmo quando atribuídas a outros.</p>'
                    +f'<p>{botao("+ Nova OS","/os/nova")} {botao("Chamados aguardando análise","/chamados","secondary")}</p>'
                    +card('Ordens de serviço',tabela(['OS','Cliente','Status','Responsável','Participantes'],rows)),s)

            def inicio(self,s):
                with ext.db(banco) as c:
                    o=c.execute('''SELECT COUNT(*) total,
                        SUM(CASE WHEN status='Aberta' THEN 1 ELSE 0 END) abertas,
                        SUM(CASE WHEN status='Pendente' THEN 1 ELSE 0 END) pendentes,
                        SUM(CASE WHEN status='Concluída' THEN 1 ELSE 0 END) concluidas FROM ordens_servico''').fetchone()
                    f=c.execute('''SELECT SUM(CASE WHEN status='Recebido' THEN valor ELSE 0 END) recebido,
                        SUM(CASE WHEN status='Aguardando pagamento' THEN valor ELSE 0 END) pendente FROM financeiro''').fetchone()
                    cl=c.execute("SELECT COUNT(*) total FROM clientes WHERE status!='Inativo'").fetchone()
                indic=[('OS abertas',o['abertas'] or 0),('OS pendentes',o['pendentes'] or 0),('OS concluídas',o['concluidas'] or 0),
                       ('A receber',dinheiro(f['pendente'])),('Recebido',dinheiro(f['recebido'])),('Clientes ativos',cl['total'])]
                k='<div class="kpis">'+''.join(f'<div class="kpi"><span>{esc(n)}</span><strong>{esc(v)}</strong></div>' for n,v in indic)+'</div>'
                corpo=f'<p>Olá, <b>{esc(s["nome"])}</b>. Acesso completo às funcionalidades operacionais, com auditoria.</p>{k}'
                atalhos=[('Clientes','/clientes'),('Ordens de serviço','/os'),('Financeiro','/financeiro'),('Notas fiscais','/notas'),('E-mails','/emails'),('Histórico e relatórios','/historico')]
                corpo+=card('Acesso rápido',''.join(botao(t,url) for t,url in atalhos))
                corpo+=v9.barra_links('prestador')
                corpo+='<div class="notice">As alterações são registradas com o prestador autenticado. E-mails e notas fiscais ainda dependem das APIs externas.</div>'
                return self.pagina('Painel principal',corpo,s)

            def clientes_lista(self,s):
                """Busca e paginação: evita lista imensa após a importação Asaas."""
                qs=parse_qs(urlparse(self.path).query)
                busca=str(qs.get('q',[''])[0]).strip()[:110]
                try:pagina=max(1,min(10000,int(qs.get('pagina',['1'])[0])))
                except (ValueError,TypeError):pagina=1
                limite=40;offset=(pagina-1)*limite
                filtro=" WHERE nome LIKE ? ESCAPE '!' OR documento LIKE ? ESCAPE '!' OR cidade LIKE ? ESCAPE '!' OR email LIKE ? ESCAPE '!'" if busca else ''
                params=[]
                if busca:
                    termo='%'+busca.replace('!','!!').replace('%','!%').replace('_','!_')+'%'
                    params=[termo]*4
                with ext.db(banco) as c:
                    total=c.execute('SELECT COUNT(*) FROM clientes'+filtro,params).fetchone()[0]
                    rows=c.execute('SELECT id,nome,documento,cidade,telefone,email,status FROM clientes'+filtro+' ORDER BY nome LIMIT ? OFFSET ?',params+[limite,offset]).fetchall()
                linhas=[]
                for r in rows:
                    linhas.append((f'<a href="/clientes/{r["id"]}">{esc(r["nome"])}</a>',esc(r['documento']),esc(r['cidade']),
                        esc(r['telefone']),esc(r['email']),esc(r['status'])))
                pesquisa='<form method="get" action="/clientes">'+campos_escuros('Buscar por nome, CPF/CNPJ, cidade ou e-mail','q',busca)+'<button>Buscar cliente</button></form>'
                navegacao=f'<p class="muted">{total} cliente(s) encontrado(s). Página {pagina}.</p>'
                if pagina>1:navegacao+=botao('Anterior','/clientes?'+urllib_parse_urlencode({'q':busca,'pagina':pagina-1}),'secondary')
                if offset+len(rows)<total:navegacao+=botao('Próximos clientes','/clientes?'+urllib_parse_urlencode({'q':busca,'pagina':pagina+1}),'secondary')
                return self.pagina('Clientes',botao('+ Novo cliente','/clientes/novo')+botao('Condomínios, empresas e vínculos','/organizacoes','secondary')
                    +card('Pesquisar clientes',pesquisa)
                    +card('Clientes cadastrados',navegacao+tabela(['Nome','Documento','Cidade','Telefone','E-mail','Status'],linhas)),s)

            def cliente_form(self,s,cid=None):
                with ext.db(banco) as c:
                    x=c.execute('SELECT * FROM clientes WHERE id=?',(cid,)).fetchone() if cid else None
                if cid and not x: return self.erro('Cliente não encontrado.',404,s)
                d=dict(x) if x else {}
                fields=[]
                campos=[('nome','Nome / Razão social'),('documento','CPF / CNPJ'),('nome_fantasia','Nome fantasia'),
                    ('endereco','Logradouro'),('numero','Número'),('complemento','Complemento'),('bairro','Bairro'),
                    ('cep','CEP'),('cidade','Cidade'),('uf','UF'),('telefone','Telefone'),('email','E-mail'),
                    ('sindico_nome','Síndico / responsável'),('sindico_telefone','Telefone do síndico'),('sindico_email','E-mail do síndico'),
                    ('administradora','Administradora / imobiliária'),('administradora_telefone','Telefone da administradora'),
                    ('administradora_email','E-mail da imobiliária / administradora')]
                for k,t in campos:
                    fields.append(campos_escuros(t,k,d.get(k,'') or '',required=k=='nome',kind='email' if k.endswith('email') or k=='email' else 'text'))
                corpo=(f'<p>{botao("← Clientes","/clientes","secondary")}</p>'
                    f'<form method="post" action="/clientes/{cid if cid else "novo"}/salvar">{self.hidden(s)}'
                    '<div class="col2">'
                    +select('Tipo de pessoa','tipo_pessoa',[(z,z) for z in ('Jurídica','Física')],d.get('tipo_pessoa') or 'Jurídica')
                    +select('Situação','status',[(z,z) for z in ('Ativo','Inativo','Prospect')],d.get('status') or 'Ativo')
                    +'</div><div class="col2">'+''.join(f'<div>{f}</div>' for f in fields)+'</div>'
                    +textarea('Observações','observacoes',d.get('observacoes') or '')
                    +'<details class="ajuda"><summary>Acesso histórico (opcional, não usado no login CPF)</summary><p>Use somente quando houver necessidade de acesso legado por ID. Senhas de contas pessoais são criadas pelo próprio usuário.</p>'
                    +campos_escuros('Senha do cliente (opcional)','senha_cliente',kind='password')
                    +campos_escuros('Confirmar senha','confirmar_senha_cliente',kind='password')+'</details>'
                    +'<button type="submit">Salvar cliente</button></form>')
                if cid:
                    corpo+=f'<form method="post" action="/clientes/{cid}/desativar">{self.hidden(s)}<button class="secondary">Desativar (preservar histórico)</button></form>'
                    corpo+=f'<form method="post" action="/clientes/{cid}/excluir" data-confirm="Confirma a exclusão deste cliente sem ordens de serviço?">{self.hidden(s)}<button class="danger" type="submit">Excluir cliente sem OS vinculadas</button></form>'
                return self.pagina('Novo cliente' if cid is None else 'Editar cliente',card('Dados cadastrais',corpo),s)

            def os_form(self,s,oid=None):
                with ext.db(banco) as c:
                    cl=c.execute("SELECT id,nome FROM clientes WHERE status!='Inativo' ORDER BY nome").fetchall()
                    o=c.execute('SELECT * FROM ordens_servico WHERE id=?',(oid,)).fetchone() if oid else None
                    mat=c.execute('SELECT * FROM materiais_os WHERE os_id=? ORDER BY id',(oid,)).fetchall() if oid else []
                    eventos=c.execute('SELECT * FROM os_eventos WHERE os_id=? ORDER BY id DESC LIMIT 150',(oid,)).fetchall() if oid else []
                    anexos=c.execute('SELECT id,nome_original,criado_em FROM os_anexos WHERE os_id=? ORDER BY id DESC',(oid,)).fetchall() if oid else []
                    responsavel=ext.responsavel_atual(c,oid) if oid else None
                    prestadores=c.execute('SELECT id,nome,email FROM prestadores WHERE ativo=1 ORDER BY nome').fetchall()
                    detalhes=c.execute('SELECT * FROM v9_detalhes_os WHERE os_id=?',(oid,)).fetchone() if oid else None
                    imagens_v9={r['anexo_id']:dict(r) for r in c.execute('SELECT * FROM v9_anexos_visiveis')} if oid else {}
                    solicitacao=c.execute('SELECT * FROM os_solicitacoes WHERE os_id=?',(oid,)).fetchone() if oid else None
                    andamento=c.execute('SELECT * FROM os_atendimentos WHERE os_id=?',(oid,)).fetchone() if oid else None
                    particip=c.execute('''SELECT p.nome FROM os_prestadores op JOIN prestadores p ON p.id=op.prestador_id
                        WHERE op.os_id=? ORDER BY p.nome''',(oid,)).fetchall() if oid else []
                if oid and not o: return self.erro('OS não encontrada.',404,s)
                d=dict(o) if o else {}
                token=self.hidden(s)
                titulo=f'OS {d["numero_os"]}' if oid else 'Nova ordem de serviço'
                action=f'/os/{oid}/salvar' if oid else '/os/nova/salvar'
                corpo=botao('← Ordens de serviço','/os','secondary')
                if oid:
                    nome_resp=next((p['nome'] for p in prestadores if p['id']==responsavel),'Não atribuído')
                    corpo+=f'<p><span class="tag">{esc(d["status"])}</span> · Responsável: <b>{esc(nome_resp)}</b> · Participantes: {esc(", ".join(p["nome"] for p in particip) or "Nenhum")}</p>'
                    if d['status'] in ext.ATIVAS:
                        pode_iniciar = (responsavel in (None,s['pid']) or d['status']=='Pendente')
                        if pode_iniciar and (d['status']=='Pendente' or not (andamento and andamento['iniciado_em'])):
                            corpo+=f'<form method="post" action="/os/{oid}/iniciar">{token}<button type="submit" class="iniciar-atendimento">▶ INICIAR OS — ASSUMIR AUTOMATICAMENTE</button></form>'
                            corpo+='<p class="muted">Registra a responsabilidade e o início no local em uma única ação. Se estiver pendente, registra a retomada.</p>'
                        elif not pode_iniciar:
                            corpo+='<p class="notice">OS em atendimento por outro prestador. Todos podem visualizar; para assumir, aguarde pendência ou peça transferência.</p>'
                if not cl:
                    corpo+='<p class="notice">Cadastre primeiro um cliente.</p>'
                    return self.pagina(titulo,corpo,s)
                dados_cliente=[(x['id'],f'{x["nome"]} — ID {x["id"]}') for x in cl]
                corpo+=f'<form method="post" action="{action}" id="form-os" enctype="multipart/form-data">{token}'
                if oid:
                    corpo+=f'<input type="hidden" name="_versao_os" value="{esc(d.get("atualizado_em") or "") }">'
                corpo+='<fieldset><legend>Identificação e serviço</legend><div class="col2"><div>'
                if solicitacao:
                    corpo+=f'<p class="notice"><strong>Solicitação original — somente leitura</strong><br>Cliente ID {solicitacao["cliente_id"]} · {esc(solicitacao["criado_em"])}<br>{esc(solicitacao["descricao_original"])}</p>'
                    corpo+=f'<input type="hidden" name="cliente_id" value="{int(solicitacao["cliente_id"])}">'
                else:
                    corpo+=select('Cliente','cliente_id',dados_cliente,d.get('cliente_id',cl[0]['id']),required=True)
                corpo+=campos_escuros('Atendido por (cliente no local)','tecnico',d.get('tecnico','') or '')
                corpo+='</div><div>'+select('Forma de pagamento','forma_pagamento',[(z,z) for z in neg.OS_FORMAS],d.get('forma_pagamento') or 'PIX')
                corpo+=campos_escuros('Valor de mão de obra (R$)','valor_mao_obra',d.get('valor_mao_obra') or '0',required=True)+'</div></div>'
                corpo+='<div class="col2"><div>'+campos_escuros('Valor de materiais sem itens detalhados (R$)','valor_materiais_manual',d.get('valor_materiais') or '0')+'</div>'
                corpo+='<div>'+campos_escuros('Total negociado (R$), opcional — substitui a soma','valor_total_override',
                  (d.get('valor_total') if d and abs(float(d.get('valor_total') or 0)-float(d.get('valor_mao_obra') or 0)-float(d.get('valor_materiais') or 0))>0.009 else ''))+'</div></div>'
                if solicitacao:
                    corpo+=f'<input type="hidden" name="descricao" value="{esc(solicitacao["descricao_original"])}">'
                else:
                    corpo+=textarea('Descrição do serviço','descricao',d.get('descricao') or '',required=True)
                if solicitacao and d.get('origem')=='Portal':
                    corpo+=f'<p class="muted">Observações originais: {esc(solicitacao["observacoes_originais"])}</p>'
                    corpo+=f'<input type="hidden" name="observacoes" value="{esc(d.get("observacoes") or "") }">'
                else:
                    corpo+=textarea('Observações gerais','observacoes',d.get('observacoes') or '')
                corpo+='</fieldset>'
                corpo+='<fieldset><legend>Materiais utilizados</legend><p class="muted">O total é calculado por mão de obra + materiais; o total negociado, quando informado, prevalece. Materiais detalhados prevalecem sobre o campo de materiais sem itens.</p>'
                linhas=list(mat)+[{} for _ in range(max(1,4-len(mat)))]
                corpo+='<div id="lista-materiais">'
                for i,m in enumerate(linhas):
                    corpo+='<div class="material-row">'
                    corpo+=f'<div>{campos_escuros("Material", "material_item[]", m['item'] if 'item' in m.keys() else '',placeholder="Cabo, câmera, fonte...")}</div>'
                    corpo+=f'<div>{campos_escuros("Quantidade", "material_qtd[]", m['quantidade'] if 'quantidade' in m.keys() else '',placeholder="1")}</div>'
                    corpo+=f'<div>{campos_escuros("Valor unitário (R$)", "material_unit[]", m['valor_unitario'] if 'valor_unitario' in m.keys() else '',placeholder="0,00")}</div>'
                    corpo+='<button type="button" class="secondary remover-material" title="Remover material">Remover</button></div>'
                corpo+='</div><button id="adicionar-material" class="secondary" type="button">+ Adicionar material</button>'
                corpo+='<p><strong>Total previsto: <span id="total-previsto">—</span></strong></p></fieldset>'
                corpo+='<fieldset><legend>Situação e relatório técnico</legend>'
                corpo+=textarea('Diagnóstico','v9_diagnostico',(detalhes['diagnostico'] if detalhes else '') or '',rows=3)
                corpo+=textarea('Serviço executado','v9_execucao',(detalhes['execucao'] if detalhes else '') or '',rows=4)
                corpo+=textarea('Resultado e testes','v9_resultado',(detalhes['resultado'] if detalhes else '') or '',rows=3)
                corpo+=textarea('Relato técnico complementar (histórico interno)','relatorio_tecnico',(andamento['rascunho'] if andamento else '') or '',rows=4)
                if oid and d['status'] in ext.ATIVAS:
                    if andamento and andamento['iniciado_em']:
                        corpo+=f'<p class="good">Atendimento iniciado em {esc(andamento["iniciado_em"])} por {esc(andamento["ator_inicio"])}</p>'
                    else:
                        corpo+='<p class="warn">OS ainda não iniciada. Assumir uma OS não inicia o atendimento automaticamente.</p>'
                corpo+=textarea('Motivo — obrigatório para serviço cancelado','motivo_encerramento','',rows=3)
                if oid and d['status'] in ext.ATIVAS:
                    corpo+='<p class="notice">Selecione a situação e confirme uma única vez. OS pendente permanece ativa; concluída/cancelada publica PDF para o cliente.</p>'
                    corpo+=select('Situação do atendimento','acao_status',
                        [('Concluída','Concluído'),('Pendente','Pendente'),('Cancelada','Cancelado')],
                        'Concluída',required=True)
                    corpo+='<div id="anexo-encerramento"><label>Fotos do relatório (até 10 imagens, 8 MB por foto)</label>'
                    corpo+='<input type="file" name="imagens_encerramento[]" multiple accept="image/jpeg,image/png,image/webp">'
                    corpo+='<p class="muted">Selecione até 10 imagens de uma só vez (JPG/PNG/WEBP, máximo de 8 MB por imagem). As imagens entram no PDF após a conclusão.</p></div>'
                corpo+='</fieldset><div class="actions">'
                if not oid:
                    corpo+='<button class="secondary" name="modo_envio" value="salvar" type="submit">Criar OS</button>'
                else:
                    corpo+='<span class="notice">OS encerrada: edição bloqueada. Documentos publicados ficam no histórico.</span>'
                if oid and d['status'] in ext.ATIVAS:
                    corpo+='<button type="submit" id="confirmar-situacao" name="modo_envio" value="encerrar" data-encerrar="1">Confirmar situação da OS</button>'
                corpo+='</div></form>'
                if not oid:
                    corpo+='<p class="muted">Depois de salvar a OS, você poderá atribuir um prestador e, no encerramento, anexar imagens e publicar PDF.</p>'
                    return self.pagina(titulo,card('Dados da OS',corpo),s)
                atrib_opt=[(p['id'],f'{p["nome"]} — {p["email"]}') for p in prestadores]
                if d['status'] in ext.ATIVAS:
                    atr=f'<form method="post" action="/os/{oid}/atribuir">{token}'
                    atr+=select('Atribuir ou transferir para','prestador_id',atrib_opt,responsavel,required=True) if atrib_opt else '<p>Cadastre prestadores pelo desktop.</p>'
                    if atrib_opt: atr+='<button type="submit">Salvar atribuição</button>'
                    atr+='</form>'
                    if responsavel:
                        atr+=f'<form method="post" action="/os/{oid}/liberar">{token}<button class="secondary">Deixar OS sem responsável</button></form>'
                    # Assumir foi integrado ao primeiro botão INICIAR OS.
                    corpo+=card('Prestadores e atribuição',atr)
                if anexos:
                    itens=[]
                    for a in anexos:
                        vis=imagens_v9.get(a['id'],{})
                        form=(f'<form method="post" action="/os/{oid}/anexo/{a["id"]}/publico">{token}'
                              +campos_escuros('Legenda para o PDF','legenda',vis.get('legenda',''))
                              +select('Incluir no PDF','visivel',[('1','Sim — incluir foto (padrão)'),('0','Não — ocultar por privacidade')],str(vis.get('visivel',1)))
                              +'<button type="submit" class="secondary">Salvar visibilidade</button></form>')
                        itens.append('<div class="card"><b>'+esc(a['nome_original'])+'</b>'+form+'</div>')
                    corpo+=card('Fotos da OS','<p>As fotos anexadas entram automaticamente no PDF. Se houver informação particular, selecione Ocultar por privacidade. Após alterar uma OS encerrada, publique outra versão do relatório.</p>'+''.join(itens))
                publicado=fluxo.ultimo_documento(banco,oid) if oid else None
                if publicado:
                    corpo+=card('Documento liberado ao cliente',
                        '<p class="good">PDF publicado, disponível para baixar no portal do cliente. Versão '+esc(publicado['versao'])+'.</p>'
                        +f'<form method="post" action="/os/{oid}/publicar">{token}<button class="secondary" type="submit">Publicar nova versão do relatório</button></form>')
                elif d['status'] in fluxo.FIM:
                    corpo+=card('Documento pendente de publicação',
                        f'<p class="warn">A OS está encerrada, mas o PDF ainda não foi publicado.</p><form method="post" action="/os/{oid}/publicar">{token}<button>Gerar e publicar PDF</button></form>')
                if publicado:
                    docs=(botao('Baixar PDF publicado',f'/os/{oid}/pdf')
                        +botao('Preparar e-mail + PDF (.eml)',f'/os/{oid}/email'))
                    if d['status']=='Concluída':
                        docs+=botao('Preparar nota fiscal (.json)',f'/os/{oid}/nota')
                else:
                    docs='<p class="muted">O PDF e o rascunho de e-mail serão liberados após a conclusão/cancelamento e publicação do relatório.</p>'
                corpo+=card('Documentos e relatórios',docs+'<p class="muted">E-mail não é enviado e nota fiscal não é emitida enquanto as APIs não estiverem conectadas.</p>')
                corpo+=card('Histórico permanente', ''.join(f'<div class="card"><small>{esc(e["criado_em"])} · {esc(e["ator"])}</small><p><b>{esc(e["acao"])}</b> — {esc(e["descricao"])}</p></div>' for e in eventos) or '<p>Nenhum evento.</p>')
                return self.pagina(titulo,card('Dados e execução da OS',corpo),s)

            def financeiro(self,s):
                with ext.db(banco) as c:
                    reg=c.execute('''SELECT f.*,o.numero_os,cl.nome cliente FROM financeiro f
                        JOIN ordens_servico o ON o.id=f.os_id JOIN clientes cl ON cl.id=f.cliente_id
                        ORDER BY f.id DESC''').fetchall()
                linhas=[]
                for x in reg:
                    acao=(f'<form method="post" action="/financeiro/{x["id"]}/receber" data-confirm="Confirma que o valor foi realmente recebido?">{self.hidden(s)}'
                          '<button type="submit">Confirmar recebimento</button></form>') if x['status']!='Recebido' else '<span class="good">Recebido</span>'
                    linhas.append((f'<a href="/os/{x["os_id"]}">{esc(x["numero_os"])}</a>',esc(x['cliente']),dinheiro(x['valor']),
                        esc(x['forma_pagamento']),esc(x['status']),esc(x['vencimento'] or ''),acao))
                recebidos=sum(float(x['valor'] or 0) for x in reg if x['status']=='Recebido')
                pendentes=sum(float(x['valor'] or 0) for x in reg if x['status']=='Aguardando pagamento')
                return self.pagina('Financeiro',f'<div class="kpis"><div class="kpi"><span>A receber</span><strong>{dinheiro(pendentes)}</strong></div>'
                    f'<div class="kpi"><span>Recebido</span><strong>{dinheiro(recebidos)}</strong></div></div>'
                    +'<p class="notice">A forma de pagamento PIX não comprova recebimento. Use “Confirmar recebimento” apenas após verificar o pagamento.</p>'
                    +card('Lançamentos financeiros',tabela(['OS','Cliente','Valor','Forma','Status','Vencimento','Ação'],linhas)),s)

            def relatorios(self,s,tipo='relatorios'):
                with ext.db(banco) as c:
                    oses=c.execute('''SELECT o.id,o.numero_os,o.status,o.valor_total,o.data_abertura,c.nome cliente
                        FROM ordens_servico o JOIN clientes c ON c.id=o.cliente_id ORDER BY o.id DESC LIMIT 500''').fetchall()
                if tipo=='emails':
                    title='E-mails para clientes'; explanation='Gere um rascunho .eml com o PDF anexado. Nenhum e-mail será enviado automaticamente.'
                    acao=lambda o:botao('Preparar .eml',f'/os/{o["id"]}/email')
                elif tipo=='notas':
                    title='Notas fiscais'; explanation='Rascunho JSON para futura integração NFS-e. Este arquivo NÃO é documento fiscal válido.'
                    acao=lambda o:botao('Preparar rascunho JSON',f'/os/{o["id"]}/nota')
                else:
                    title='Relatórios gerais e PDFs'; explanation='Histórico das OS e relatórios individuais com materiais, atividades e anexos.'
                    acao=lambda o:botao('Baixar PDF',f'/os/{o["id"]}/pdf')
                rows=[(f'<a href="/os/{r["id"]}">{esc(r["numero_os"])}</a>',esc(r['cliente']),esc(r['status']),dinheiro(r['valor_total']),acao(r)) for r in oses]
                resumo=(f'<div class="kpis"><div class="kpi"><span>Ordens de serviço</span><strong>{len(oses)}</strong></div>'
                        f'<div class="kpi"><span>Total exibido</span><strong>{dinheiro(sum(float(x["valor_total"] or 0) for x in oses))}</strong></div></div>') if tipo=='relatorios' else ''
                return self.pagina(title,f'<p class="muted">{esc(explanation)}</p>{resumo}'+card('Ordens disponíveis',tabela(['OS','Cliente','Status','Valor','Ação'],rows)),s)

            def portal_cliente(self,s):
                url_cliente='http://127.0.0.1:8765/'
                info=botao('Abrir Portal do Cliente (8765)',url_cliente)
                info+=('<p class="muted">O Portal do Cliente é um site separado, na porta 8765. '
                       'O login dele é por CPF e senha e não se mistura com o login do prestador. '
                       'As solicitações registradas lá aparecem nesta lista e no desktop.</p>')
                with ext.db(banco) as c:
                    web=c.execute("SELECT id,numero_os,status,data_abertura FROM ordens_servico WHERE origem='Portal' ORDER BY id DESC LIMIT 100").fetchall()
                registros=[(f'<a href="/os/{o["id"]}">{esc(o["numero_os"])}</a>',esc(o['status']),esc(o['data_abertura'])) for o in web]
                return self.pagina('Portal do cliente',info+card('Solicitações recebidas pelo portal',tabela(['OS','Situação','Abertura'],registros)),s)

            def documentos(self,s,oid,kind):
                with ext.db(banco) as c:
                    o=c.execute('SELECT numero_os,status FROM ordens_servico WHERE id=?',(oid,)).fetchone()
                    if not o: return self.erro('OS inexistente.',404,s)
                with LOCK_DOCS:
                    if kind in ('pdf','email'):
                        if o['status'] not in fluxo.FIM:
                            return self.erro('PDF disponível somente após o encerramento da OS.',409,s)
                        publicado=fluxo.ultimo_documento(banco,oid)
                        if not publicado:
                            return self.erro('PDF ainda não publicado. Abra esta OS e use Republicar PDF.',409,s)
                        pdf=fluxo.validar_pdf_publicado(publicado)
                    if kind=='pdf':
                        arq=pdf;mime='application/pdf'
                    elif kind=='email':
                        arq=ext.criar_email_rascunho(banco,oid,pdf);mime='message/rfc822'
                    elif kind=='nota':
                        arq=ext.criar_rascunho_fiscal(banco,oid);mime='application/json; charset=utf-8'
                    else:return self.erro('Arquivo inválido.',404,s)
                    with ext.db(banco) as c:
                        neg.audit(c,s['pid'],'Documento gerado',oid,kind)
                    return self.send_bytes(Path(arq).read_bytes(),mime,filename=Path(arq).name)

            def anexo(self,s,aid):
                with ext.db(banco) as c:
                    x=c.execute('SELECT nome_original,caminho FROM os_anexos WHERE id=?',(aid,)).fetchone()
                if not x:return self.erro('Anexo não encontrado.',404,s)
                arq=Path(x['caminho']).resolve()
                if not arq.is_relative_to(ext.ANEXOS.resolve()):
                    return self.erro('Anexo fora do diretório autorizado.',403,s)
                if not arq.is_file():return self.erro('Arquivo de imagem não encontrado.',404,s)
                mime=mimetypes.guess_type(arq.name)[0] or 'application/octet-stream'
                return self.send_bytes(arq.read_bytes(),mime,filename=x['nome_original'])

            def do_GET(self):
                path=urlparse(self.path).path.rstrip('/') or '/'
                try:
                    if path=='/api/versao':
                        dados=json.dumps({'app':'Gestão de Serviços — AUTOSEG','versao':VERSAO_PORTAL,
                                          'site':'portal do prestador',
                                          'porta':getattr(self.server,'server_port',None),
                                          'login_prestador':'e-mail e senha',
                                          'cadastro_prestadores':'bloqueado no portal web'}).encode('utf-8')
                        return self.send_bytes(dados,'application/json; charset=utf-8')
                    if path=='/prestadores' or path.startswith('/prestadores/'):
                        return self.erro('O cadastro de prestadores é feito somente no aplicativo desktop.',403,self.sessao())
                    if path in ('/cliente','/pj') or path.startswith('/cliente/') or path.startswith('/pj/'):
                        return self.erro('O Portal do Cliente fica em http://127.0.0.1:8765/ (porta 8765). '
                                         'Este endereço é o Portal do Prestador.',404,self.sessao())
                    s=self.sessao()
                    if not s:return self.login()
                    if path=='/static/portal.js':
                        return self.send_bytes((Path(__file__).parent/'portal.js').read_bytes(),'application/javascript; charset=utf-8')
                    if path in ('/chamados','/organizacoes'):
                        return v9.get(self,path,banco,s)
                    if path=='/':return self.inicio(s)
                    if path=='/os':return self.os_lista(s)
                    if path=='/historico':return self.os_lista(s,True)
                    if path=='/os/nova':return self.os_form(s)
                    if path=='/clientes':return self.clientes_lista(s)
                    if path=='/clientes/novo':return self.cliente_form(s)
                    if path=='/financeiro':return self.financeiro(s)
                    if path=='/relatorios':return self.redir('/historico')
                    if path=='/emails':return self.relatorios(s,'emails')
                    if path=='/notas':return self.relatorios(s,'notas')
                    if path=='/portal-cliente':return self.portal_cliente(s)
                    partes=path.strip('/').split('/')
                    if len(partes)==2 and partes[0]=='clientes' and partes[1].isdigit():
                        return self.cliente_form(s,int(partes[1]))
                    if len(partes)==2 and partes[0]=='os' and partes[1].isdigit():
                        return self.os_form(s,int(partes[1]))
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit() and partes[2] in ('pdf','email','nota'):
                        return self.documentos(s,int(partes[1]),partes[2])
                    if len(partes)==3 and partes[0]=='arquivos' and partes[1]=='anexo' and partes[2].isdigit():
                        return self.anexo(s,int(partes[2]))
                    return self.erro('Página não encontrada.',404,s)
                except PermissionError as e:return self.erro(str(e),403,self.sessao())
                except ValueError as e:return self.erro(str(e),409,self.sessao())
                except Exception:
                    LOG.exception('Erro GET %s',path)
                    return self.erro('Falha interna. Consulte o log do aplicativo.',500,self.sessao())

            def do_POST(self):
                path=urlparse(self.path).path.rstrip('/') or '/'
                try:
                    d=self.form()
                    if path=='/prestadores' or path.startswith('/prestadores/'):
                        return self.erro('O cadastro de prestadores é feito somente no aplicativo desktop. '
                                         'O portal web não aceita cadastro de prestadores.',403,self.sessao())
                    if path=='/login':
                        ip=self.client_address[0]
                        agora=time.time()
                        with LOCK_LOGIN:
                            tent=[t for t in TENTATIVAS.get(ip,[]) if agora-t<600]
                            if len(tent)>=10: return self.erro('Muitas tentativas. Aguarde dez minutos.',429)
                        p=ext.autenticar(banco,str(d.get('email','')),str(d.get('senha','')))
                        if not p:
                            with LOCK_LOGIN:TENTATIVAS[ip]=tent+[agora]
                            return self.erro('Usuário ou senha incorretos.',401)
                        with LOCK_LOGIN:TENTATIVAS.pop(ip,None)
                        tok=secrets.token_urlsafe(36)
                        SESSOES[tok]={'pid':p['id'],'nome':p['nome'],'csrf':secrets.token_urlsafe(32),'exp':time.time()+28800}
                        return self.redir('/',self.cookie(tok))
                    s=self.sessao()
                    self.csrf(s,d)
                    if path=='/sair':
                        cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
                        if 'autosseg_session' in cookie:SESSOES.pop(cookie['autosseg_session'].value,None)
                        return self.redir('/',self.cookie('',True))
                    pid=s['pid']
                    if path.startswith('/chamados/') or path.startswith('/organizacoes/') or path=='/organizacoes/mesclar' or (path.startswith('/clientes/') and path.endswith('/desativar')):
                        return v9.post(self,path,d,banco,s)
                    partes=path.strip('/').split('/')
                    if path=='/clientes/novo/salvar' or (len(partes)==3 and partes[0]=='clientes' and partes[1].isdigit() and partes[2]=='salvar'):
                        senha_nova=str(d.get('senha_cliente',''))
                        confirmar=str(d.get('confirmar_senha_cliente',''))
                        if senha_nova or confirmar:
                            if len(senha_nova)<10:raise ValueError('A senha do cliente deve ter pelo menos 10 caracteres.')
                            if senha_nova!=confirmar:raise ValueError('A confirmação da senha não corresponde.')
                        editar=int(partes[1]) if len(partes)==3 and partes[1].isdigit() else None
                        cid=neg.cliente_salvar(banco,d,pid,editar)
                        if senha_nova:fluxo.definir_senha_cliente(banco,cid,senha_nova)
                        return self.redir(f'/clientes/{cid}')
                    if len(partes)==3 and partes[0]=='clientes' and partes[1].isdigit() and partes[2]=='excluir':
                        neg.cliente_excluir(banco,int(partes[1]),pid)
                        return self.redir('/clientes')
                    if path=='/os/nova/salvar':
                        oid=neg.os_salvar(banco,d,pid)
                        return self.redir(f'/os/{oid}')
                    if len(partes)==5 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='anexo' and partes[3].isdigit() and partes[4]=='publico':
                        oid=int(partes[1]);aid=int(partes[3])
                        with ext.db(banco) as c:
                            ok=c.execute('SELECT 1 FROM os_anexos WHERE id=? AND os_id=?',(aid,oid)).fetchone()
                        if not ok:raise ValueError('Anexo não pertence à OS.')
                        cad9.aprovar_anexo(banco,aid,str(d.get('visivel','0'))=='1',str(d.get('legenda','')),s['nome'])
                        return self.redir(f'/os/{oid}')
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit():
                        oid=int(partes[1]);acao=partes[2]
                        if acao=='salvar':
                            if d.get('modo_envio')!='encerrar':raise ValueError('Use Confirmar situação da OS. O botão de salvar progresso foi removido.')
                            # Só o botão de encerramento aplica o status escolhido.
                            if d.get('modo_envio')=='encerrar' and str(d.get('acao_status',''))=='Concluída' and not (str(d.get('v9_execucao','')).strip() or str(d.get('relatorio_tecnico','')).strip()):
                                raise ValueError('Preencha Serviço executado antes de concluir.')
                            if not str(d.get('relatorio_tecnico','')).strip():
                                d['relatorio_tecnico']='\n'.join(str(d.get(x,'')).strip() for x in ('v9_diagnostico','v9_execucao','v9_resultado') if str(d.get(x,'')).strip())
                            neg.os_salvar(banco,d,pid,oid)
                            cad9.salvar_detalhes(banco,oid,str(d.get('v9_diagnostico','')),str(d.get('v9_execucao','')),str(d.get('v9_resultado','')))
                            if str(d.get('acao_status','')) in fluxo.FIM:
                                try: fluxo.publicar_relatorio(banco,oid)
                                except Exception as falha:
                                    LOG.exception('Encerrada OS %s, mas falhou a publicação do PDF',oid)
                                    return self.pagina('OS encerrada — PDF pendente',card('Encerramento salvo',
                                        '<p>Os dados da OS foram preservados. Falhou apenas a publicação do PDF.</p>'
                                        +f'<p class="bad">{esc(str(falha)[:400])}</p>'
                                        +botao('Abrir OS e republicar PDF',f'/os/{oid}')),s,503)
                        elif acao=='publicar':
                            fluxo.publicar_relatorio(banco,oid)
                        elif acao=='atribuir':
                            ext.atribuir(banco,oid,int(d['prestador_id']),ator=f'Prestador {s["nome"]}')
                        elif acao=='liberar':
                            ext.desatribuir(banco,oid,ator=f'Prestador {s["nome"]}')
                        elif acao=='assumir':
                            ext.assumir(banco,oid,pid)
                        elif acao=='iniciar':
                            aten.iniciar_assumindo(banco,oid,pid)
                        else:return self.erro('Operação desconhecida.',404,s)
                        return self.redir(f'/os/{oid}')
                    if len(partes)==3 and partes[0]=='financeiro' and partes[1].isdigit() and partes[2]=='receber':
                        neg.financeiro_receber(banco,int(partes[1]),pid)
                        return self.redir('/financeiro')
                    return self.erro('Operação desconhecida.',404,s)
                except PermissionError as e:return self.erro(str(e),403,self.sessao())
                except (KeyError,ValueError,TypeError) as e:return self.erro(str(e),400,self.sessao())
                except Exception:
                    LOG.exception('Erro POST %s',path)
                    return self.erro('Falha interna ao salvar. Consulte o log.',500,self.sessao())

        try:
            self.servidor=ThreadingHTTPServer((self.host,self.porta),Handler)
        except OSError as exc:
            LOG.error('Porta %s indisponível: %s',self.porta,exc)
            raise RuntimeError(
                f'A porta {self.porta} já está em uso. Feche o outro AUTOSEG (ou o processo '
                f'antigo) antes de iniciar. Nenhuma versão antiga deve continuar atendendo /cliente.'
            ) from exc
        self.porta=self.servidor.server_port
        self.thread=threading.Thread(target=self.servidor.serve_forever,daemon=True)
        self.thread.start()
        host_exibido='127.0.0.1' if self.host in ('0.0.0.0','::') else self.host
        return f'http://{host_exibido}:{self.porta}'

    def url_rede(self):
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
                s.connect(('192.0.2.1',80))
                ip=s.getsockname()[0]
            return f'http://{ip}:{self.porta}'
        except OSError:
            return f'http://127.0.0.1:{self.porta}'

    def parar(self):
        if self.servidor:
            self.servidor.shutdown();self.servidor.server_close();self.servidor=None
