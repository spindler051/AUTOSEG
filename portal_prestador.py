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
import re
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
import feedback_portal as feedback
import importacao_yaml as yaml_import
import catalogo_servicos as catalogo
import estoque_materiais as estoque
import portal_v9 as v9
import links_publicos as links9
import produtividade_os as prod
import solicitacoes_pj as pj_publico
import socket
from versao_app import versao_local

LOG = logging.getLogger('autosseg.portal')
VERSAO_PORTAL = versao_local('9.6.0-dev.6')


CSS_MOBILE = """
.lista-organizacoes-pj{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.lista-organizacoes-pj .resultado-organizacao{margin:0}
.resultado-organizacao{border:1px solid #666;border-radius:13px;padding:18px 20px;margin:14px 0;background:#202020}
.resultado-organizacao h3{margin:0 0 5px;font-size:21px}
.resultado-organizacao p{margin:4px 0 12px;color:#ddd;overflow-wrap:anywhere}
.resultado-organizacao .btn{width:100%;text-align:center;margin:0}
.aviso-claro{border-left:5px solid var(--yellow);padding:15px 18px;background:#2a2617;border-radius:8px}
.busca-pj .busca-linha{display:flex;gap:8px;align-items:flex-end}
.busca-pj .busca-linha input{flex:1;min-width:0}
@media (max-width: 760px) {
  html, body { max-width: 100%; overflow-x: hidden; }
  .top { gap: 10px; padding: 10px 14px; }
  .brand img { height: 28px !important; }
  .nav { display: flex !important; flex-wrap: wrap; gap: 6px; }
  .nav a { font-size: 13px; padding: 9px 10px; }
  main { padding: 0 12px 40px; }
  .card { padding: 16px; }
  .table-scroll { overflow-x: visible; }
  table { min-width: 0 !important; width: 100%; }
  thead { display: none; }
  tbody tr { display: block; border: 1px solid #3d3d3d; border-radius: 10px; margin: 10px 0; padding: 8px; }
  tbody td { display: block; border: 0; padding: 6px 8px; min-width: 0 !important; white-space: normal; overflow-wrap: anywhere; }
  tbody td::before { content: attr(data-label) ": "; color: #ffd400; font-weight: 700; }
  .col2 { grid-template-columns: 1fr; }
  .material-row { grid-template-columns: 1fr 1fr; }
  .material-row > div:first-child { grid-column: 1 / -1; }
  .actions button, .actions .btn, .stack button, .stack .btn { width: 100%; margin: 6px 0; }
  .foto-rascunho { grid-template-columns: 1fr !important; }
  .foto-rascunho img { width: 100% !important; height: auto !important; }
  img { max-width: 100%; height: auto; }
  input, select, textarea { font-size: 16px; }
  .busca-pj .busca-linha { display: flex; flex-direction: column; gap: 8px; }
  .busca-pj button { width: 100%; }
  .lista-organizacoes-pj { grid-template-columns: 1fr; }
}
"""

CSS_FEEDBACK = """
.feedback-fab{position:fixed;right:22px;bottom:22px;z-index:1200;box-shadow:0 8px 24px #000a;border-radius:999px;padding:14px 20px}
.feedback-dialog{width:min(680px,calc(100vw - 28px));max-height:calc(100vh - 50px);overflow:auto;border:2px solid #ffd400;border-radius:16px;background:#151515;color:#fff;padding:0;box-shadow:0 18px 60px #000d}
.feedback-dialog::backdrop{background:#000c}
.feedback-dialog form{padding:22px}
.feedback-dialog h2{margin:0 0 6px;color:#ffd400}
.feedback-dialog textarea{min-height:150px;resize:vertical}
.feedback-dialog input[readonly]{background:#222;color:#c9c9c9;border-color:#555}
.feedback-dialog .feedback-check{display:flex;gap:10px;align-items:flex-start;margin:16px 0;font-weight:600}
.feedback-dialog .feedback-check input{width:22px;height:22px;min-height:22px;margin-top:2px;flex:0 0 auto}
.feedback-dialog .feedback-actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}
.feedback-dialog .feedback-actions button{margin:0}
.feedback-dialog .feedback-privacidade{font-size:13px;line-height:1.5;color:#c9c9c9}
@media(max-width:620px){.feedback-fab{right:12px;bottom:12px;padding:12px 16px;font-size:14px}.feedback-dialog form{padding:17px}}
"""


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
    def linha(cells):
        saida=''
        for i,x in enumerate(cells):
            rotulo=esc(headers[i] if i<len(headers) else '')
            saida+=f'<td data-label="{rotulo}">{x}</td>'
        return saida
    return '<div class="table-scroll"><table><thead><tr>'+''.join(f'<th>{esc(h)}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+linha(cells)+'</tr>' for cells in rows)+'</tbody></table></div>'


def _dialogo_feedback(usuario):
    """Botão e diálogo globais do Portal do Prestador (nunca no portal do cliente)."""
    if not usuario:
        return ''
    return f'''
<button type="button" class="feedback-fab" id="abrir-feedback" aria-haspopup="dialog" aria-controls="dialogo-feedback">Dê um feedback</button>
<dialog class="feedback-dialog" id="dialogo-feedback" aria-labelledby="feedback-titulo">
  <form method="post" action="/feedback" id="form-feedback">
    <input type="hidden" name="csrf" value="{esc(usuario.get('csrf',''))}">
    <h2 id="feedback-titulo">Dê um feedback</h2>
    <p class="muted">Conte o que funcionou, o que confundiu ou o que precisa melhorar nesta página.</p>
    <label for="feedback-pagina">Página atual</label>
    <input type="text" id="feedback-pagina" name="pagina" value="" readonly autocomplete="off">
    <label for="feedback-mensagem">Seu feedback</label>
    <textarea id="feedback-mensagem" name="mensagem" minlength="5" maxlength="4000" rows="6" required placeholder="Ex.: não encontrei onde alterar o preço do serviço; ou: o botão de iniciar OS não apareceu para mim."></textarea>
    <label class="feedback-check" for="feedback-responder-ia">
      <input type="checkbox" id="feedback-responder-ia" name="responder_ia" value="1">
      <span>Pedir uma resposta da IA com base no conhecimento do AUTOSEG (opcional)</span>
    </label>
    <p class="muted feedback-privacidade">O texto digitado fica salvo apenas nesta aba até você enviar ou cancelar. Ao enviar, registramos seu usuário, a página, o navegador, o dispositivo e o endereço IP (a rede é truncada por padrão) para diagnóstico e segurança. Se você pedir resposta por IA, o texto é anonimizado antes de sair do servidor. A IA pode errar e não altera o sistema; o feedback fica para revisão humana.</p>
    <div class="feedback-actions">
      <button type="submit">Enviar feedback</button>
      <button type="button" class="secondary" id="fechar-feedback">Cancelar</button>
    </div>
  </form>
</dialog>'''


def layout(titulo,corpo,usuario=None,nonce=None,cliente=False):
    menus=[('/','Início'),('/clientes','Clientes'),('/os','Ordens de serviço'),('/servicos','Serviços e valores'),('/financeiro','Financeiro'),('/pj-publicas','Solicitações PJ'),('/notas','Notas fiscais'),('/emails','E-mails'),('/historico','Histórico e relatórios')]
    if usuario and usuario.get('admin') and not cliente:
        menus.append(('/feedback/recebidos','Feedbacks'))
    nav=(''.join(f'<a href="{url}">{esc(nome)}</a>' for url,nome in menus[:4])
         +'<details class="nav-more"><summary>Mais opções</summary>'
         +''.join(f'<a href="{url}">{esc(nome)}</a>' for url,nome in menus[4:])+'</details>') if usuario else ''
    us=f'<span class="usuario">{esc(usuario["nome"])} · Prestador</span>' if usuario else ''
    ambiente='DEV (testes)' if os.environ.get('AUTOSEG_DEV')=='1' else 'produção'
    footer=f'''<footer>AUTOSEG {VERSAO_PORTAL} · ambiente {ambiente} · relatórios por e-mail e NFS-e em anexo quando cadastrados.</footer>'''
    feedback_html=_dialogo_feedback(None if cliente else usuario)
    logout=(f'<form method="post" action="/sair" class="logout"><input type="hidden" name="csrf" value="{esc(usuario["csrf"])}">'
            '<button class="subtle">Sair</button></form>') if usuario else ''
    if cliente:
        # Portal do Cliente: apenas a logo, grande, sem textos auxiliares.
        topo=('<a class="brand" href="/cliente" style="display:flex;align-items:center">'
              '<img src="/logo.png" alt="AUTOSEG" style="height:88px;max-width:380px;object-fit:contain;display:block">'
              '</a>')
    else:
        topo=('<a class="brand" href="/" style="display:flex;align-items:center;gap:10px">'
              '<img src="/logo.png" alt="AUTOSEG" style="height:34px;max-width:150px;object-fit:contain;display:block">'
              '<span style="font-size:13px;color:#ddd;font-weight:600">Gestão de Serviços</span></a>'
              '<span class="tagline">AUTOMAÇÃO E SEGURANÇA · Portal de Serviços</span>')
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(titulo)} · AUTOSEG</title><link rel="icon" href="/icone.png" type="image/png"><style>
:root{{--yellow:#ffd400;--bg:#080808;--card:#191919;--border:#424242;--muted:#bababa;--green:#52edb2;--red:#ff7d7d}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:#fff;font:16px -apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;line-height:1.45}}
a{{color:var(--yellow)}}header{{background:#171717;border-bottom:3px solid var(--yellow)}}.top{{max-width:1240px;margin:auto;display:flex;gap:14px;align-items:center;flex-wrap:wrap;padding:12px 18px}}
.brand{{color:var(--yellow);font-size:26px;font-weight:900;letter-spacing:.3px;text-decoration:none}}.tagline{{color:#ddd;font-size:13px}}
.nav{{display:flex;gap:6px;flex-wrap:wrap;max-width:1240px;margin:auto;padding:0 18px 13px}}.nav a{{color:#fff;text-decoration:none;border:1px solid #414141;padding:10px 13px;border-radius:8px;font-weight:650}}.nav a:hover{{background:var(--yellow);color:#101010}}.nav-more{{position:relative;z-index:2;border:1px solid #414141;border-radius:8px;padding:9px 13px}}.nav-more summary{{cursor:pointer;font-weight:650}}.nav-more[open]{{background:#232323}}.nav-more a{{display:block;margin:8px 0}}
main{{max-width:1240px;margin:20px auto;padding:0 18px 50px;min-width:0}}h1{{font-size:clamp(22px,4vw,32px);margin:14px 0}}h2{{font-size:21px;margin:0 0 15px}}h3{{font-size:17px;margin:10px 0}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;margin:15px 0}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:13px}}.grid .card{{margin:0}}
label{{display:block;margin:13px 0 5px;font-weight:650}}input,textarea,select{{width:100%;font:inherit;color:#fff;background:#090909;border:1.5px solid #989898;border-radius:7px;padding:10px;max-width:100%}}
input:focus,textarea:focus,select:focus{{outline:2px solid var(--yellow)}}input[type=file]{{padding:12px}}input[type=checkbox]{{width:auto}}
button,.btn{{display:inline-flex;align-items:center;justify-content:center;max-width:100%;overflow-wrap:anywhere;white-space:normal;text-align:center;vertical-align:middle;min-width:0;border-radius:8px;font:bold 15px Arial;padding:13px 16px;cursor:pointer;color:#161616;background:var(--yellow);border:1px solid var(--yellow);text-decoration:none;margin:4px 5px 4px 0;min-height:44px}}
button.secondary,.btn.secondary{{background:#262626;border-color:#9b9b9b;color:#fff}}button.danger,.btn.danger{{background:#451b1b;color:#fff;border-color:#b75151}}button.subtle{{background:transparent;color:#fff;border:1px solid #777}}
.usuario{{color:#ddd;font-size:13px}}.logout{{margin:0 0 0 auto}}.muted,small{{color:var(--muted)}}.good{{color:var(--green)}}.warn{{color:#ffce79}}.bad{{color:var(--red)}}.tag{{background:#4a400c;color:#ffe678;border-radius:6px;padding:4px 9px;font-size:13px;white-space:nowrap}}
.table-scroll{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;min-width:640px}}th,td{{border-bottom:1px solid #414141;padding:12px 10px;text-align:left;vertical-align:top;overflow-wrap:normal;word-break:normal}}th{{color:var(--yellow);background:#222}}td:nth-child(3){{min-width:125px}}td:nth-child(3),td:nth-child(4),td:nth-child(5){{overflow-wrap:normal;word-break:normal}} .material-row button{{min-width:90px}}.col2{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:15px}}.actions{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}}.kpi{{background:#171717;border:1px solid #444;padding:17px;border-radius:10px}}.kpi strong{{display:block;font-size:26px;color:var(--yellow)}}.kpi span{{font-size:13px;color:var(--muted)}}
form{{max-width:100%;min-width:0}}.col2>div{{min-width:0}}.card{{min-width:0;overflow-wrap:anywhere}}.nav-more{{max-width:100%}}
fieldset{{border:1px solid #444;border-radius:10px;padding:14px;margin:14px 0}}legend{{color:var(--yellow);font-weight:800;padding:0 9px}}.material-row{{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,1fr) minmax(0,1fr) auto;gap:8px;align-items:end;margin:7px 0}}.material-row label{{font-size:12px;margin:0}}.material-row input{{width:100%}}
.flash{{background:#163c29;border:1px solid #67e2a8;padding:13px;border-radius:8px}}.notice{{background:#3e320e;border:1px solid #937d2f;border-radius:9px;padding:13px}}.stack{{display:flex;gap:8px;flex-wrap:wrap}}.stack form{{display:inline}}.pic{{display:inline-block;padding:8px 12px;border:1px solid #555;border-radius:6px;margin:4px}}footer{{color:#999;padding:20px;text-align:center;border-top:1px solid #292929;font-size:13px}}
@media(max-width:620px){{.material-row{{grid-template-columns:1fr 1fr}}.material-row>div:first-child{{grid-column:1/-1}}.nav a{{font-size:13px;padding:9px}}.top{{padding:12px}}main{{padding:0 12px}}}}
{CSS_MOBILE}{CSS_FEEDBACK}</style><script src="/static/portal.js" defer></script></head><body><header><div class="top">{topo}{us}{logout}</div><nav class="nav">{nav}</nav></header><main><h1>{esc(titulo)}</h1>{corpo}</main>{footer}{feedback_html}</body></html>'''


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
                pasta=ext.BASE/'logs'
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
        prod.instalar(banco)
        pj_publico.instalar(banco)
        fluxo.instalar(banco)
        aten.instalar(banco)
        cad9.instalar(banco)
        catalogo.instalar(banco)
        estoque.instalar(banco)
        feedback.instalar(banco)
        # Repara chamados antigos que não receberam OS após falha/interrupção,
        # inclusive quando apenas o Portal do Prestador é iniciado.
        recuperadas=cad9.sincronizar_solicitacoes_pendentes(banco)
        if recuperadas:
            LOG.warning('Solicitações antigas vinculadas a OS pendentes: %d',recuperadas)
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
                self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; img-src 'self'")
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
                if titulo=='Ordens de serviço ativas':
                    # Inert marker: portal.js owns the timer and pauses it while
                    # the feedback dialog is open or a form control is in use.
                    pagina=pagina.replace('</head>','<meta name="autoseg-auto-refresh" content="20"></head>')
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
                    p=c.execute('SELECT nome,senha_hash FROM prestadores WHERE id=? AND ativo=1',(s['pid'],)).fetchone()
                if not p or not secrets.compare_digest(s.get('cred',''),p['senha_hash']):
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

            def pj_publicas(self, s):
                pendentes = pj_publico.listar(banco, 'Aguardando verificação')
                historico = pj_publico.listar(banco)
                token = self.hidden(s)
                linhas = []
                for p in pendentes:
                    acoes = (
                        f'<form method="post" action="/pj-publicas/{p["id"]}/aceitar" style="display:inline">'
                        f'{token}<button type="submit">Aceitar</button></form> '
                        f'<form method="post" action="/pj-publicas/{p["id"]}/recusar" style="display:inline">'
                        f'{token}<input name="motivo" required placeholder="Motivo da recusa" '
                        f'style="max-width:220px;display:inline-block"><button class="danger" type="submit">Recusar</button></form>')
                    linhas.append((f'PJ-{p["id"]:04d}', esc(p['organizacao']), esc(p['nome']),
                                   esc(p['telefone']), esc(p['descricao'][:160]), esc(p['criado_em']), acoes))
                if pendentes:
                    tabela_pend = tabela(['Protocolo','Condomínio/empresa','Solicitante','Telefone','Solicitação','Recebido','Verificação'], linhas)
                else:
                    tabela_pend = '<p class="muted">Nenhuma solicitação aguardando verificação.</p>'
                hist = []
                for p in historico:
                    if p['status'] == 'Aguardando verificação':
                        continue
                    os_link = (f'<a href="/os/{p["os_id"]}">OS {esc(p["os_id"])}</a>'
                               if p['os_id'] else '—')
                    hist.append((f'PJ-{p["id"]:04d}', esc(p['organizacao']), esc(p['nome']),
                                 esc(p['status']), os_link, esc(p['motivo'] or ''), esc(p['decidido_em'] or '')))
                tabela_hist = (tabela(['Protocolo','Condomínio/empresa','Solicitante','Situação','OS','Motivo','Decidido em'], hist)
                               if hist else '<p class="muted">Sem histórico.</p>')
                return self.pagina('Solicitações PJ sem cadastro',
                    '<p class="muted">Pedidos de abertura de OS feitos por condomínios/empresas sem cadastro PF. '
                    'Aceitar cria uma OS <b>Aberta</b>; recusar exige motivo.</p>'
                    + card('Aguardando verificação', tabela_pend)
                    + card('Histórico de verificação', tabela_hist), s)

            def os_lista(self,s,concluidas=False):
                if concluidas:
                    with ext.db(banco) as c:
                        lista=c.execute('''SELECT o.id,o.numero_os,o.status,o.descricao,o.data_abertura,
                            o.valor_total,cl.nome cliente,MAX(d.versao) versao
                            FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id
                            LEFT JOIN os_documentos d ON d.os_id=o.id AND d.tipo='relatorio_pdf'
                            WHERE o.status NOT IN ('Aberta','Iniciada','Pendente')
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
                    estado=x['status']
                    try:
                        with ext.db(banco) as c:
                            if ext.em_rota_atual(c, x['id']): estado='Em rota'
                    except Exception:
                        pass
                    rows.append((f'<a href="/os/{x["id"]}">{esc(x["numero_os"])}</a>',esc(x['cliente']),
                        f'<span class="tag">{esc(estado)}</span>',esc(x.get('responsavel') or 'Não atribuído'),
                        esc(x.get('participantes') or 'Nenhum')))
                return self.pagina('Ordens de serviço ativas',
                    '<p class="muted">Todos os prestadores veem as OS abertas, iniciadas e pendentes, mesmo quando atribuídas a outros.</p>'
                    +f'<p>{botao("+ Nova OS rápida","/os/rapida")} {botao("Nova OS completa","/os/nova","secondary")}</p>'
                    +card('Ordens de serviço',tabela(['OS','Cliente','Status','Responsável','Participantes'],rows)),s)

            def inicio(self,s):
                with ext.db(banco) as c:
                    o=c.execute('''SELECT COUNT(*) total,
                        SUM(CASE WHEN status='Aberta' THEN 1 ELSE 0 END) abertas,
                        SUM(CASE WHEN status='Iniciada' THEN 1 ELSE 0 END) iniciadas,
                        SUM(CASE WHEN status='Pendente' THEN 1 ELSE 0 END) pendentes,
                        SUM(CASE WHEN status='Concluída' THEN 1 ELSE 0 END) concluidas FROM ordens_servico''').fetchone()
                    f=c.execute('''SELECT SUM(CASE WHEN status='Recebido' THEN valor ELSE 0 END) recebido,
                        SUM(CASE WHEN status='Aguardando pagamento' THEN valor ELSE 0 END) pendente FROM financeiro''').fetchone()
                    cl=c.execute("SELECT COUNT(*) total FROM clientes WHERE status!='Inativo'").fetchone()
                indic=[('OS abertas',o['abertas'] or 0),('OS iniciadas',o['iniciadas'] or 0),
                       ('OS pendentes',o['pendentes'] or 0),('OS concluídas',o['concluidas'] or 0),
                       ('A receber',dinheiro(f['pendente'])),('Recebido',dinheiro(f['recebido'])),('Clientes ativos',cl['total'])]
                k='<div class="kpis">'+''.join(f'<div class="kpi"><span>{esc(n)}</span><strong>{esc(v)}</strong></div>' for n,v in indic)+'</div>'
                corpo=f'<p>Olá, <b>{esc(s["nome"])}</b>. Acesso completo às funcionalidades operacionais, com auditoria.</p>{k}'
                atalhos=[('Clientes','/clientes'),('Ordens de serviço','/os'),('Serviços e valores','/servicos'),('Financeiro','/financeiro'),('Notas fiscais','/notas'),('E-mails','/emails'),('Histórico e relatórios','/historico')]
                corpo+=card('Acesso rápido',''.join(botao(t,url) for t,url in atalhos))
                corpo+=v9.barra_links('prestador')
                corpo+='<div class="notice">As alterações são registradas com o prestador autenticado. E-mails e notas fiscais ainda dependem das APIs externas.</div>'
                return self.pagina('Painel principal',corpo,s)

            def feedback_admin(self,s,status_dev='',aviso='',erro=''):
                if not s.get('admin'):
                    raise PermissionError('Feedbacks recebidos são visíveis apenas para administradores.')
                contagens=feedback.contagens(banco)
                itens=feedback.listar(banco,status_dev=status_dev,limite=300)
                kpis='<div class="kpis">'+''.join(
                    f'<div class="kpi"><span>{esc(nome)}</span><strong>{int(contagens.get(nome,0))}</strong></div>'
                    for nome in feedback.STATUS_TRIAGEM)+'</div>'
                opcoes=[('','Todos os feedbacks')]+[(x,x) for x in feedback.STATUS_TRIAGEM]
                filtro=('<form method="get" action="/feedback/recebidos">'
                        +select('Filtrar por situação na DEV','status',opcoes,status_dev)
                        +'<button type="submit">Filtrar</button></form>')
                linhas=[]
                for item in itens:
                    resumo=re.sub(r'\s+',' ',item['mensagem_anonimizada']).strip()[:140]
                    linhas.append((
                        f'<a href="/feedback/{item["id"]}">FB-{item["id"]:04d}</a>',
                        esc(item['criado_em']),esc(item['prestador_nome']),
                        f'<code>{esc(item["pagina"])}</code>',esc(resumo),
                        esc(item['categoria']),esc(item['urgencia']),
                        f'<span class="tag">{esc(item["status_dev"])}</span>'))
                aberturas=feedback.listar_aberturas(banco,limite=30)
                linhas_aberturas=[(
                    esc(x['criado_em']),esc(x['prestador_nome']),
                    f'<code>{esc(x["pagina"])}</code>',esc(x['dispositivo']),
                    esc(x['navegador']),esc(x['sistema'])) for x in aberturas]
                aviso_html=f'<p class="good">{esc(aviso)}</p>' if aviso else ''
                erro_html=f'<p class="bad">{esc(erro)}</p>' if erro else ''
                return self.pagina('Feedbacks recebidos',
                    '<p class="muted">Canal interno de feedback do Portal do Prestador. '
                    'A classificação da IA é uma sugestão; a decisão de registrar uma pendência na DEV é humana. '
                    'O texto abaixo é a versão anonimizada.</p>'
                    +aviso_html+erro_html
                    +card('Resumo por situação',kpis)
                    +card('Filtrar',filtro)
                    +card('Feedbacks',
                        '<p>'+botao('Baixar pendências da DEV (.md)','/feedback/pendencias.md','secondary')
                        +botao('Exportar dados de feedback (.json)','/feedback/dados/exportar.json','secondary')+'</p>'
                        +tabela(['ID','Recebido','Prestador','Página','Relato anonimizado','Categoria','Urgência','Situação na DEV'],linhas))
                    +card('Aberturas recentes do canal',
                        '<p class="muted">Registra quem abriu o diálogo, em qual página, com qual dispositivo e navegador. '
                        'Serve para diagnosticar dificuldades de uso e correlação com erros.</p>'
                        +tabela(['Quando','Prestador','Página','Dispositivo','Navegador','Sistema'],linhas_aberturas)),s)

            def feedback_detalhe(self,s,fid):
                item=feedback.obter(banco,fid)
                if not item:
                    return self.erro('Feedback não encontrado.',404,s)
                if not s.get('admin') and int(item['prestador_id'])!=int(s['pid']):
                    raise PermissionError('Este feedback pertence a outro prestador.')
                resposta=''
                if item['responder_ia']:
                    if item['ia_status']=='ok':
                        resposta=card('Resposta da IA',
                            '<p class="notice">A IA pode errar. Ela não altera o sistema e não substitui a revisão humana.</p>'
                            +f'<p style="white-space:pre-wrap">{esc(item["resposta_ia"])}</p>'
                            +f'<p class="muted">Categoria sugerida: {esc(item["categoria"])} · '
                            +f'Urgência sugerida: {esc(item["urgencia"])} · Confiança: {float(item["confianca"]):.0%}</p>'
                            +((f'<p><b>Possível melhoria:</b> {esc(item["possivel_melhoria"])}</p>') if item['possivel_melhoria'] else ''))
                    else:
                        resposta=card('Resposta automática indisponível',
                            f'<p class="warn">{esc(item["ia_erro"] or "A IA não respondeu.")}</p>'
                            '<p>O feedback foi salvo e está disponível para análise humana.</p>')
                admin=False
                if s.get('admin'):
                    admin=True
                    opcoes=''.join(
                        f'<option value="{esc(x)}" {"selected" if x==item["status_dev"] else ""}>{esc(x)}</option>'
                        for x in feedback.STATUS_TRIAGEM)
                    triagem=card('Triagem para a DEV',
                        f'<form method="post" action="/feedback/{item["id"]}/triagem">{self.hidden(s)}'
                        '<label for="c_status_dev">Situação</label>'
                        f'<select id="c_status_dev" name="status_dev" required>{opcoes}</select>'
                        +textarea('Nota da triagem (opcional)','nota_dev',item['nota_dev'],rows=4)
                        +'<p class="muted">Use “Pendente na DEV” quando o relato identificou um problema real ou melhoria necessária. '
                        'A IA não decide isso sozinha.</p>'
                        +'<button type="submit">Salvar triagem</button></form>')
                    meta=tabela(['Campo','Valor'],[
                        ('IP completo (somente se configurado)',esc(item['ip'] or '—')),
                        ('Rede truncada',esc(item['ip_rede'] or '—')),
                        ('Hash do IP',esc(item['ip_hash'] or '—')),
                        ('Hash da sessão',esc(item['sessao_hash'] or '—')),
                        ('Navegador',esc(item['navegador'] or '—')),
                        ('Sistema',esc(item['sistema'] or '—')),
                        ('Dispositivo',esc(item['dispositivo'] or '—')),
                        ('User-Agent',esc(item['user_agent'] or '—')),
                        ('Texto anonimizado enviado à IA',esc(item['mensagem_anonimizada'] or '—')),
                    ])
                    detalhes=card('Contexto técnico (administrador)',meta)
                else:
                    triagem=''
                    detalhes=''
                return self.pagina(f'Feedback FB-{item["id"]:04d}',
                    botao('← Voltar','/feedback/recebidos' if admin else '/','secondary')
                    +card('Relato',
                        f'<p class="muted">{esc(item["criado_em"])} · {esc(item["prestador_nome"])} · '
                        f'<code>{esc(item["pagina"])}</code></p>'
                        f'<p style="white-space:pre-wrap">{esc(item["mensagem"])}</p>'
                        f'<p><span class="tag">{esc(item["status_dev"])}</span></p>')
                    +resposta+triagem+detalhes,s)

            def servicos_lista(self,s):
                termo=str(parse_qs(urlparse(self.path).query).get('q',[''])[0]).strip()[:100].casefold()
                rows=[]
                for serv in catalogo.listar(banco):
                    if termo and termo not in (serv['nome']+' '+serv['descricao']).casefold():continue
                    valor=catalogo.valores_orcamento(banco,serv['id']) if serv['ativo'] else None
                    excluir=(f'<form method="post" action="/servicos/{serv["id"]}/excluir" '
                             'data-confirm="Excluir definitivamente este serviço do catálogo?">'
                             +self.hidden(s)
                             +'<button class="danger" type="submit">Excluir</button></form>')
                    rows.append((esc(serv['nome']),esc(serv['descricao'][:100]),
                        catalogo.reais(valor['total']) if valor else 'Arquivado',
                        botao('Editar',f'/servicos/{serv["id"]}/editar','secondary')+excluir))
                return self.pagina('Serviços e valores',
                    '<p>Catálogo para propostas e preenchimento de relatórios. Os preços são editados somente por prestadores.</p>'
                    +botao('+ Novo serviço','/servicos/novo')
                    +'<form method="get" action="/servicos">'+campos_escuros('Buscar serviço por nome ou descrição','q',termo)+'<button>Pesquisar</button></form>'
                    +card('Serviços cadastrados',tabela(['Serviço','Descrição','Preço estimado','Ação'],rows)),s)

            def servico_form(self,s,identificador=None,preenchimento=None,erro=None):
                atual=catalogo.obter(banco,identificador) if identificador else None
                if identificador and not atual:return self.erro('Serviço não encontrado.',404,s)
                dados=preenchimento if preenchimento is not None else (atual or {})
                import json
                if 'materiais_lista' in dados:
                    itens=dados['materiais_lista']
                elif 'material_nome[]' in dados:
                    def normal(x):return x if isinstance(x,list) else [x]
                    itens=[{'nome':n,'quantidade':q,'valor_unitario':v} for n,q,v in zip(normal(dados.get('material_nome[]',[])),normal(dados.get('material_qtd[]',[])),normal(dados.get('material_valor[]',[])))]
                else:
                    itens=json.loads(dados.get('materiais_json') or '[]')
                form=(f'<form method="post" action="/servicos/salvar" id="form-servico">{self.hidden(s)}'
                   +f'<input type="hidden" name="servico_id" value="{identificador or ""}">'
                   +campos_escuros('Nome do serviço','nome',dados.get('nome') or '',required=True)
                   +textarea('Descrição para o cliente','descricao',dados.get('descricao') or '')
                   +campos_escuros('Preço base da mão de obra (R$)','preco_servico',
                       dados.get('preco_servico',str((dados.get('preco_servico_centavos') or 0)/100).replace('.',',')),required=True)
                   +'<fieldset><legend>Materiais — opcionais</legend><p class="muted">Preencha os três campos, sem usar barras ou separadores. Remova linhas que não precisar.</p>'
                   +'<div id="lista-materiais-servico">')
                for x in itens:
                    valor=x.get('valor_unitario',str(x.get('preco_centavos',0)/100).replace('.',','))
                    form+=('<div class="material-row">'
                           +f'<label>Material<input name="material_nome[]" value="{esc(x.get("nome",""))}" placeholder="Controle remoto"></label>'
                           +f'<label>Quantidade<input name="material_qtd[]" value="{esc(x.get("quantidade",""))}" placeholder="1"></label>'
                           +f'<label>Valor unitário (R$)<input name="material_valor[]" value="{esc(valor)}" placeholder="75,00"></label>'
                           +'<button type="button" class="secondary remover-material-servico">Remover</button></div>')
                form+=("""</div><button type="button" class="secondary" id="adicionar-material-servico">+ Adicionar material</button>
                    <template id="modelo-material-servico"><div class="material-row"><label>Material<input name="material_nome[]" placeholder="Nome"></label>
                    <label>Quantidade<input name="material_qtd[]" placeholder="1"></label><label>Valor unitário (R$)<input name="material_valor[]" placeholder="0,00"></label>
                    <button type="button" class="secondary remover-material-servico">Remover</button></div></template></fieldset>""")
                form+=(textarea('Modelo de relatório técnico do serviço','relatorio_padrao',dados.get('relatorio_padrao') or '',rows=6)
                   +'<p class="muted">Modelo é sugestão editável; não substitui o relatório próprio de cada atendimento.</p>'
                   +'<button type="submit">Salvar serviço</button></form>')
                if identificador and not dados.get('ativo',True):
                    form+=(f'<form method="post" action="/servicos/{identificador}/reativar">'
                           +self.hidden(s)+'<button>Reativar serviço</button></form>')
                if identificador and dados.get('ativo',True):
                    form+=(f'<form method="post" action="/servicos/{identificador}/arquivar" '
                           'data-confirm="Arquivar este serviço do catálogo?">'+self.hidden(s)
                           +'<button type="submit" class="danger">Arquivar serviço</button></form>')
                importar=(f'<form method="post" enctype="multipart/form-data" action="/servicos/yaml">{self.hidden(s)}'
                           '<label for="yaml-servico">Preencher serviço a partir de YAML (até 64 KB)</label>'
                           '<input type="file" id="yaml-servico" name="yaml" accept=".yaml,.yml" required>'
                           '<button type="submit" class="secondary">Pré-visualizar YAML de serviço</button></form>'
                           '<p class="muted"><a href="/modelos/servico.yaml">Baixar modelo YAML oficial</a> · Apenas pré-preenche; confira antes de salvar.</p>')
                aviso=card('Verifique os dados',f'<p class="bad">{esc(erro)}</p>') if erro else ''
                return self.pagina('Editar serviço' if identificador else 'Novo serviço',
                    botao('← Catálogo','/servicos','secondary')+aviso+card('Importação rápida',importar)+card('Valores e relatório padrão',form),s,400 if erro else 200)

            def clientes_lista(self,s):
                """Busca e paginação: evita lista imensa após a importação Asaas."""
                qs=parse_qs(urlparse(self.path).query)
                busca=str(qs.get('q',[''])[0]).strip()[:110]
                try:pagina=max(1,min(10000,int(qs.get('pagina',['1'])[0])))
                except (ValueError,TypeError):pagina=1
                limite=40;offset=(pagina-1)*limite
                filtro=(" WHERE nome LIKE ? ESCAPE '!' OR documento LIKE ? ESCAPE '!' OR cidade LIKE ? ESCAPE '!' OR email LIKE ? ESCAPE '!' "
                       "OR replace(replace(replace(documento,'.',''),'/',''),'-','') LIKE ? ESCAPE '!' ") if busca else ''
                params=[]
                if busca:
                    termo='%'+busca.replace('!','!!').replace('%','!%').replace('_','!_')+'%'
                    docs=cad9.digitos(busca)
                    params=[termo]*4+['%'+docs+'%' if docs else 'documento_nunca_corresponde']
                with ext.db(banco) as c:
                    total=c.execute('SELECT COUNT(*) FROM clientes'+filtro,params).fetchone()[0]
                    rows=c.execute('SELECT id,nome,documento,cidade,telefone,email,status FROM clientes'+filtro+' ORDER BY nome LIMIT ? OFFSET ?',params+[limite,offset]).fetchall()
                linhas=[]
                for r in rows:
                    linhas.append((f'<a href="/clientes/{r["id"]}">{esc(r["nome"])}</a>',esc(cad9.formatar_documento(r['documento'])),esc(r['cidade']),
                        esc(r['telefone']),esc(r['email']),esc(r['status'])))
                pesquisa='<form method="get" action="/clientes">'+campos_escuros('Buscar por nome, CPF/CNPJ, cidade ou e-mail','q',busca)+'<button>Buscar cliente</button></form>'
                navegacao=f'<p class="muted">{total} cliente(s) encontrado(s). Página {pagina}.</p>'
                if pagina>1:navegacao+=botao('Anterior','/clientes?'+urllib_parse_urlencode({'q':busca,'pagina':pagina-1}),'secondary')
                if offset+len(rows)<total:navegacao+=botao('Próximos clientes','/clientes?'+urllib_parse_urlencode({'q':busca,'pagina':pagina+1}),'secondary')
                return self.pagina('Clientes',botao('+ Novo cliente','/clientes/novo')+botao('Novo orçamento','/orcamento','secondary')+botao('Nomear síndico / gestor','/clientes/responsaveis','secondary')
                    +card('Pesquisar clientes',pesquisa)
                    +card('Clientes cadastrados',navegacao+tabela(['Nome','Documento','Cidade','Telefone','E-mail','Status'],linhas)),s)

            def orcamento_form(self, s, erro='', cliente_id=None,
                               servicos=None, materiais=None, aviso=''):
                """Orçamento com cliente, vários serviços e materiais adicionais."""
                with ext.db(banco) as c:
                    clientes = c.execute(
                        "SELECT id,nome,documento FROM clientes WHERE status!='Inativo' "
                        "ORDER BY nome LIMIT 500").fetchall()
                catalogo_servicos = catalogo.listar(banco, ativos=True)
                produtos = estoque.listar(banco, ativos=True)
                if not clientes:
                    return self.pagina('Novo orçamento', card('Sem clientes',
                        '<p>Cadastre um cliente antes de gerar um orçamento.</p>'
                        + botao('Cadastrar cliente','/clientes/novo')), s)
                if not catalogo_servicos and not produtos:
                    return self.pagina('Novo orçamento', card('Sem serviços ou materiais',
                        '<p>Cadastre um serviço no catálogo ou um material no estoque antes de gerar um orçamento.</p>'
                        + botao('Serviços e valores','/servicos')), s)

                selecionado = str(cliente_id or '')
                if selecionado and not any(str(x['id']) == selecionado for x in clientes):
                    selecionado = ''
                opcoes_clientes = [('', 'Selecione o cliente')] + [
                    (x['id'], f'{x["nome"]} — {cad9.formatar_documento(x["documento"])}')
                    for x in clientes]

                def total_servico(servico):
                    try:
                        itens = json.loads(servico['materiais_json'] or '[]')
                        materiais_servico = sum(
                            int(Decimal(str(m.get('quantidade', 0))) *
                                int(m.get('preco_centavos', 0)))
                            for m in itens)
                    except (TypeError, ValueError, KeyError):
                        materiais_servico = 0
                    return (servico['preco_servico_centavos'] or 0) + materiais_servico

                opcoes_servico = [
                    {'id': str(x['id']), 'nome': x['nome'],
                     'unitario': total_servico(x)}
                    for x in catalogo_servicos]
                opcoes_material = [
                    {'id': str(x['id']), 'nome': x['nome'],
                     'unitario': int(x.get('venda_centavos') or 0),
                     'unidade': x.get('unidade') or 'un'}
                    for x in produtos]

                def opcoes_html(opcoes, selecionado_id=''):
                    return ''.join(
                        f'<option value="{esc(x["id"])}" '
                        f'data-unitario-centavos="{int(x["unitario"])}"'
                        f'{" selected" if str(selecionado_id) == x["id"] else ""}>'
                        f'{esc(x["nome"])} — {esc(catalogo.reais(x["unitario"]))}</option>'
                        for x in opcoes)

                def linha_servico(item):
                    item = item or {}
                    escolhido = str(item.get('id') or '')
                    quantidade = str(item.get('quantidade') or '1')
                    return ('<div class="orcamento-servico-row">'
                            '<label>Serviço<select name="servico_id[]">'
                            '<option value="">Selecione o serviço</option>'
                            + opcoes_html(opcoes_servico, escolhido)
                            + '</select></label>'
                            '<label>Quantidade<input name="servico_qtd[]" type="number" '
                            f'min="1" max="20" step="1" value="{esc(quantidade)}"></label>'
                            '<button type="button" class="secondary remover-servico-orcamento">Remover</button>'
                            '</div>')

                def linha_material(item):
                    item = item or {}
                    escolhido = str(item.get('id') or '')
                    quantidade = str(item.get('quantidade') or '1')
                    return ('<div class="orcamento-material-row">'
                            '<label>Material<select name="material_id[]">'
                            '<option value="">Selecione o material</option>'
                            + opcoes_html(opcoes_material, escolhido)
                            + '</select></label>'
                            '<label>Quantidade<input name="material_qtd[]" type="number" '
                            f'min="0.01" max="1000" step="0.01" value="{esc(quantidade)}"></label>'
                            '<button type="button" class="secondary remover-material-orcamento">Remover</button>'
                            '</div>')

                ids_servico = {x['id'] for x in opcoes_servico}
                ids_material = {x['id'] for x in opcoes_material}
                if servicos is None:
                    linhas_servico = ([{'id': '', 'quantidade': '1'}]
                                      if opcoes_servico else [])
                else:
                    linhas_servico = [
                        {'id': str(x.get('id') or ''),
                         'quantidade': str(x.get('quantidade') or '1')}
                        for x in servicos]
                linhas_material = [
                    {'id': str(x.get('id') or ''),
                     'quantidade': str(x.get('quantidade') or '1')}
                    for x in (materiais or [])]
                linhas_servico = [
                    x for x in linhas_servico
                    if not x['id'] or x['id'] in ids_servico]
                linhas_material = [
                    x for x in linhas_material
                    if not x['id'] or x['id'] in ids_material]

                campo_busca = ('<label for="busca-cliente-os">Buscar cliente ou condomínio</label>'
                               '<input type="search" id="busca-cliente-os" '
                               'placeholder="Digite o nome ou ID para localizar" autocomplete="off">')
                secao_servicos = ''
                if opcoes_servico:
                    secao_servicos = (
                        '<fieldset><legend>Serviços</legend>'
                        '<p class="muted">Cada serviço já inclui os materiais cadastrados no próprio serviço. '
                        'Use "Materiais adicionais" apenas para itens cobrados separadamente.</p>'
                        '<div id="lista-servicos-orcamento">'
                        + ''.join(linha_servico(x) for x in linhas_servico)
                        + '</div>'
                        '<button type="button" class="secondary" id="adicionar-servico-orcamento">'
                        '+ Adicionar serviço</button>'
                        f'<template id="modelo-servico-orcamento">{linha_servico({})}</template>'
                        '</fieldset>')
                secao_materiais = ''
                if opcoes_material:
                    secao_materiais = (
                        '<fieldset><legend>Materiais adicionais — opcional</legend>'
                        '<p class="muted">Preço de venda ativo do estoque. '
                        'Não repita materiais que já fazem parte do serviço.</p>'
                        '<div id="lista-materiais-orcamento">'
                        + ''.join(linha_material(x) for x in linhas_material)
                        + '</div>'
                        '<button type="button" class="secondary" id="adicionar-material-orcamento">'
                        '+ Adicionar material</button>'
                        f'<template id="modelo-material-orcamento">{linha_material({})}</template>'
                        '</fieldset>')

                form = (f'<form method="post" action="/orcamento/pdf" id="form-orcamento">{self.hidden(s)}'
                        + campo_busca
                        + select('Cliente','cliente_id',opcoes_clientes,selecionado,required=True)
                        + secao_servicos
                        + secao_materiais
                        + '<p><strong>Total estimado: <span id="total-orcamento">—</span></strong></p>'
                        + '<p class="notice">O PDF é apenas um orçamento estimativo. '
                          'Nenhuma ordem de serviço, cobrança ou movimentação de estoque é criada.</p>'
                        + '<button type="submit">Gerar orçamento em PDF</button></form>')
                aviso_yaml = (f'<p class="good" id="yaml-orcamento-importado">{esc(aviso)}</p>'
                              if aviso else '')
                erro_html = card('Verifique os dados', f'<p class="bad">{esc(erro)}</p>') if erro else ''
                importar = (
                    f'<form method="post" enctype="multipart/form-data" action="/orcamento/yaml">'
                    f'{self.hidden(s)}'
                    '<label for="yaml-orcamento">Criar orçamento por YAML (até 64 KB)</label>'
                    '<input type="file" id="yaml-orcamento" name="yaml" accept=".yaml,.yml" required>'
                    '<button type="submit" class="secondary">Pré-visualizar YAML de orçamento</button>'
                    '</form>'
                    '<p class="muted"><a href="/modelos/orcamento.yaml">Baixar modelo YAML oficial</a> · '
                    'A importação não cria OS nem cobrança; apenas preenche a tela para revisão.</p>')
                return self.pagina('Novo orçamento',
                    botao('← Clientes','/clientes','secondary')
                    + card('Importação por YAML', importar)
                    + erro_html
                    + card('Orçamento (não é OS)',
                           aviso_yaml
                           + '<p class="notice">Escolha um ou mais serviços e, se precisar, '
                             'materiais adicionais. Os preços vêm do catálogo e do estoque ativos.</p>'
                           + form), s)

            def cliente_form(self,s,cid=None,preenchimento=None):
                with ext.db(banco) as c:
                    x=c.execute('SELECT * FROM clientes WHERE id=?',(cid,)).fetchone() if cid else None
                if cid and not x: return self.erro('Cliente não encontrado.',404,s)
                d=dict(x) if x else {}
                if cid is None and preenchimento:d.update(preenchimento)
                fields=[]
                campos=[('nome','Nome / Razão social'),('documento','CPF / CNPJ'),('nome_fantasia','Nome fantasia'),
                    ('endereco','Logradouro'),('numero','Número'),('complemento','Complemento'),('bairro','Bairro'),
                    ('cep','CEP'),('cidade','Cidade'),('uf','UF'),('telefone','Telefone'),('email','E-mail'),
                    ('sindico_nome','Síndico / responsável'),('sindico_telefone','Telefone do síndico'),('sindico_email','E-mail do síndico'),
                    ('administradora','Administradora / imobiliária'),('administradora_telefone','Telefone da administradora'),
                    ('administradora_email','E-mail da imobiliária / administradora')]
                for k,t in campos:
                    fields.append(campos_escuros(t,k,cad9.formatar_documento(d.get(k,'')) if k=='documento' else (d.get(k,'') or ''),required=k=='nome',kind='email' if k.endswith('email') or k=='email' else 'text'))
                corpo=(f'<p>{botao("← Clientes","/clientes","secondary")}'
                    + (botao("Novo orçamento",f"/orcamento?cliente_id={cid}","secondary") if cid else '')
                    + f'</p><form method="post" action="/clientes/{cid if cid else "novo"}/salvar">{self.hidden(s)}'
                    '<div class="col2"><div>'
                    +select('Tipo de pessoa','tipo_pessoa',[(z,z) for z in ('Jurídica','Física')],d.get('tipo_pessoa') or 'Jurídica')
                    +'</div><div>'+select('Situação','status',[(z,z) for z in ('Ativo','Inativo','Prospect')],d.get('status') or 'Ativo')
                    +'</div></div><div class="col2">'+''.join(f'<div>{f}</div>' for f in fields)+'</div>'
                    +textarea('Observações','observacoes',d.get('observacoes') or '')
                    +'<details class="ajuda"><summary>Acesso histórico (opcional, não usado no login CPF)</summary><p>Use somente quando houver necessidade de acesso legado por ID. Senhas de contas pessoais são criadas pelo próprio usuário.</p>'
                    +campos_escuros('Senha do cliente (opcional)','senha_cliente',kind='password')
                    +campos_escuros('Confirmar senha','confirmar_senha_cliente',kind='password')+'</details>'
                    +'<button type="submit">Salvar cliente</button></form>')
                if not cid:
                    importar=(f'<form method="post" action="/clientes/yaml" enctype="multipart/form-data">{self.hidden(s)}'
                       '<label for="importar-cliente-yaml">Preencher cadastro com arquivo YAML (até 64 KB)</label>'
                       '<input type="file" id="importar-cliente-yaml" name="yaml" accept=".yaml,.yml" required>'
                       '<button type="submit" class="secondary">Pré-visualizar cadastro YAML</button></form>'
                       '<p class="muted">Use o modelo pronto: <a href="/modelos/cadastro.yaml">Baixar YAML de cliente</a>. Revise antes de salvar.</p>')
                    corpo=card('Importação assistida — apenas prestador',importar)+corpo
                    if preenchimento:
                        corpo='<p class="notice">Dados importados para revisão. Confira nome, documento, vínculos e endereço antes de salvar.</p>'+corpo
                if cid:
                    corpo+=f'<form method="post" action="/clientes/{cid}/desativar">{self.hidden(s)}<button class="secondary">Desativar (preservar histórico)</button></form>'
                    corpo+=f'<form method="post" action="/clientes/{cid}/excluir" data-confirm="Confirma a exclusão deste cliente sem ordens de serviço?">{self.hidden(s)}<button class="danger" type="submit">Excluir cliente sem OS vinculadas</button></form>'
                return self.pagina('Novo cliente' if cid is None else 'Editar cliente',card('Dados cadastrais',corpo),s)

            def os_rapida_form(self, s, erro='', q='', cliente_id=None):
                """Abertura rápida com busca e cartões, no mesmo padrão do Portal do Cliente."""
                with ext.db(banco) as c:
                    if cliente_id:
                        cliente = c.execute(
                            "SELECT id,nome,tipo_pessoa,cidade,bairro,email FROM clientes "
                            "WHERE id=? AND status!='Inativo'", (int(cliente_id),)).fetchone()
                        if not cliente:
                            return self.os_rapida_form(
                                s, 'Cliente não encontrado ou inativo. Escolha outro na lista.', q=q)
                        prestadores = c.execute(
                            "SELECT id,nome FROM prestadores WHERE ativo=1 AND excluido=0 ORDER BY nome").fetchall()
                        local = ' · '.join(x for x in (cliente['tipo_pessoa'], cliente['bairro'],
                                                       cliente['cidade']) if x)
                        form = (f'<form method="post" action="/os/rapida/salvar">{self.hidden(s)}'
                                f'<input type="hidden" name="cliente_id" value="{int(cliente["id"])}">'
                                f'<p class="passo">{esc(cliente["nome"])}'
                                + (f' · {esc(local)}' if local else '') + '</p>'
                                + textarea('Solicitação / descrição do serviço', 'descricao',
                                           required=True)
                                + select('Forma de pagamento', 'forma_pagamento',
                                         [('', 'Selecione a forma de pagamento')]
                                         + [(z, z) for z in neg.OS_FORMAS], '', required=True))
                        if prestadores:
                            form += select('Atribuir prestador (opcional)', 'prestador_id',
                                           [('', 'Não atribuir agora')]
                                           + [(x['id'], x['nome']) for x in prestadores])
                        else:
                            form += ('<p class="muted">Nenhum prestador ativo cadastrado; '
                                     'a OS ficará sem responsável.</p>')
                        form += ('<p class="notice">A OS será criada como <b>Aberta</b>. '
                                 'Ela só fica <b>Pendente</b> se o atendimento for iniciado e '
                                 'encerrado com essa situação.</p>'
                                 '<button type="submit" style="width:100%">Criar OS aberta</button></form>')
                        aviso = f'<p class="bad">{esc(erro)}</p>' if erro else ''
                        return self.pagina(
                            'Nova OS rápida — ' + cliente['nome'],
                            card('Solicitação para ' + cliente['nome'], aviso + form)
                            + botao('← Voltar e escolher outro cliente', '/os/rapida', 'secondary'), s)

                    termo = str(q or '').strip()[:120]
                    esc_like = termo.replace('!', '!!').replace('%', '!%').replace('_', '!_')
                    digitos = cad9.digitos(termo)
                    if termo:
                        filtro = ("WHERE status!='Inativo' AND (nome LIKE ? ESCAPE '!' "
                                  "OR documento LIKE ? ESCAPE '!' OR cidade LIKE ? ESCAPE '!' "
                                  "OR email LIKE ? ESCAPE '!'")
                        params = ['%' + esc_like + '%'] * 4
                        if digitos:
                            filtro += " OR documento LIKE ? ESCAPE '!'"
                            params.append('%' + digitos + '%')
                        filtro += ")"
                        clientes = c.execute(
                            "SELECT id,nome,tipo_pessoa,cidade,bairro,email,documento "
                            "FROM clientes " + filtro + " ORDER BY nome LIMIT 100",
                            params).fetchall()
                    else:
                        clientes = c.execute(
                            "SELECT id,nome,tipo_pessoa,cidade,bairro,email,documento "
                            "FROM clientes WHERE status!='Inativo' ORDER BY nome LIMIT 100").fetchall()

                busca = ('<form method="get" action="/os/rapida" class="busca-pj">'
                         '<label for="q-os-rapida">Buscar condomínio, empresa ou cliente</label>'
                         '<div class="busca-linha">'
                         f'<input id="q-os-rapida" name="q" type="search" value="{esc(termo)}" '
                         'placeholder="Digite o nome, CNPJ/CPF, cidade ou e-mail" autocomplete="off">'
                         '<button type="submit">Buscar</button></div></form>')
                cards = []
                for x in clientes:
                    local = ' · '.join(y for y in (x['tipo_pessoa'], x['bairro'], x['cidade']) if y)
                    contato = (' · ' + esc(x['email'])) if x['email'] else ''
                    cards.append(
                        '<article class="resultado-organizacao">'
                        f'<h3>{esc(x["nome"])}</h3><p>{esc(local)}{contato}</p>'
                        f'<a class="btn" href="/os/rapida?cliente={int(x["id"])}">'
                        'Abrir OS para este cliente</a></article>')
                lista = ''.join(cards) or (
                    '<p class="aviso-claro">Nenhum cliente encontrado para esta busca. '
                    'Tente outro nome ou <a href="/clientes/novo">cadastre o cliente</a>.</p>')
                aviso = f'<p class="bad">{esc(erro)}</p>' if erro else ''
                return self.pagina(
                    'Nova OS rápida',
                    card('1. Encontre o cliente',
                         '<p>Busque pelo nome, CNPJ/CPF, cidade ou e-mail. '
                         'Ao escolher, você informa a solicitação e cria a OS.</p>' + aviso + busca)
                    + card('2. Escolha o cliente', '<div class="lista-organizacoes-pj">'
                           + lista + '</div>')
                    + botao('Nova OS completa', '/os/nova', 'secondary')
                    + botao('Voltar às OS', '/os', 'secondary'), s)

            def os_form(self,s,oid=None,preenchimento=None,erro=None):
                with ext.db(banco) as c:
                    cl=c.execute("SELECT id,nome FROM clientes WHERE status!='Inativo' ORDER BY nome").fetchall()
                    o=c.execute('SELECT * FROM ordens_servico WHERE id=?',(oid,)).fetchone() if oid else None
                    mat=c.execute('SELECT * FROM materiais_os WHERE os_id=? ORDER BY id',(oid,)).fetchall() if oid else []
                    eventos=c.execute('SELECT * FROM os_eventos WHERE os_id=? ORDER BY id DESC LIMIT 150',(oid,)).fetchall() if oid else []
                    anexos=c.execute('''SELECT a.id,a.nome_original,a.criado_em,a.tipo,
                        COALESCE(v.legenda,'') legenda,COALESCE(v.visivel,1) visivel
                        FROM os_anexos a LEFT JOIN v9_anexos_visiveis v ON v.anexo_id=a.id
                        WHERE a.os_id=? ORDER BY a.id''',(oid,)).fetchall() if oid else []
                    responsavel=ext.responsavel_atual(c,oid) if oid else None
                    prestadores=c.execute('SELECT id,nome,email FROM prestadores WHERE ativo=1 ORDER BY nome').fetchall()
                    detalhes=c.execute('SELECT * FROM v9_detalhes_os WHERE os_id=?',(oid,)).fetchone() if oid else None
                    imagens_v9={r['anexo_id']:dict(r) for r in c.execute('SELECT * FROM v9_anexos_visiveis')} if oid else {}
                    solicitacao=c.execute('SELECT * FROM os_solicitacoes WHERE os_id=?',(oid,)).fetchone() if oid else None
                    andamento=c.execute('SELECT * FROM os_atendimentos WHERE os_id=?',(oid,)).fetchone() if oid else None
                    particip=c.execute('''SELECT p.nome FROM os_prestadores op JOIN prestadores p ON p.id=op.prestador_id
                        WHERE op.os_id=? ORDER BY p.nome''',(oid,)).fetchall() if oid else []
                    notas_fiscais=c.execute('SELECT id,nome_original,criado_em FROM os_notas_fiscais WHERE os_id=? ORDER BY id',
                                            (oid,)).fetchall() if oid else []
                    contatos_os=prod.contatos_email_os(banco,oid) if oid else None
                if oid and not o: return self.erro('OS não encontrada.',404,s)
                d=dict(o) if o else {}
                if preenchimento:
                    # YAML é um modelo: preenche apenas campos vazios por padrão.
                    # A escolha explícita "substituir" é necessária para sobrescrever.
                    substituir=bool(preenchimento.get('_substituir'))
                    if detalhes:
                        for chave in ('diagnostico','execucao','resultado'):
                            d.setdefault('v9_'+chave,detalhes[chave] or '')
                    if andamento:d.setdefault('relatorio_tecnico',andamento['rascunho'] or '')
                    for k,v in preenchimento.items():
                        if k.startswith('v9_') or k=='relatorio_tecnico':
                            if substituir or not str(d.get(k,'')).strip():d[k]=v
                    # Rascunho completo do servidor (produtividade_os) também chega aqui.
                    for k in ('tecnico','valor_mao_obra','valor_materiais_manual','custo_materiais','valor_total_override','forma_pagamento'):
                        if k in preenchimento and (substituir or not str(d.get(k,'')).strip()):
                            d[k]=preenchimento[k]
                    if 'material_yaml' in preenchimento and (substituir or not mat):
                        mat=preenchimento['material_yaml']
                    # Composição declarativa (pai + filhos) vinda do YAML/agente.
                    if 'composicao_yaml' in preenchimento:
                        d['composicao_yaml'] = preenchimento['composicao_yaml']
                    itens=preenchimento.get('material_item[]',[])
                    quantidades=preenchimento.get('material_qtd[]',[])
                    unitarios=preenchimento.get('material_unit[]',[])
                    if itens and (substituir or not mat):
                        mat=[dict(item=item,quantidade=quantidades[i] if i<len(quantidades) else '',valor_unitario=unitarios[i] if i<len(unitarios) else '')
                             for i,item in enumerate(itens) if item]
                token=self.hidden(s)
                titulo=f'OS {d["numero_os"]}' if oid else 'Nova ordem de serviço'
                action=f'/os/{oid}/salvar' if oid else '/os/nova/salvar'
                corpo=botao('← Ordens de serviço','/os','secondary')
                if erro:corpo+=card('Corrija o arquivo YAML',f'<p class="bad" id="yaml-erro-rev08">{esc(erro)}</p><p>Você pode selecionar outro arquivo sem sair da OS.</p>')
                if preenchimento:
                    corpo+=('<p class="notice" id="yaml-importado-rev08" data-yaml-importado="1">'
                        'Prévia importada. Seus campos já digitados podem ser restaurados; '
                        'revise as informações antes de confirmar a OS.</p>'
                        '<button class="secondary" type="button" id="desfazer-yaml-rev08">'
                        'Desfazer importação YAML</button>')
                if oid and d['status'] in ext.ATIVAS:
                    importar=(f'<form method="post" action="/os/{oid}/yaml" enctype="multipart/form-data">{token}'
                      '<label for="importar-relatorio-yaml">Preencher relatório com arquivo YAML (até 64 KB)</label>'
                      '<input type="file" id="importar-relatorio-yaml" name="yaml" accept=".yaml,.yml" required>'
                      '<label><input type="checkbox" name="substituir" value="1"> Substituir campos e materiais já preenchidos</label>'
                      '<button type="submit" class="secondary">Pré-visualizar relatório YAML</button></form>'
                      '<p class="muted">Modelo pronto: <a href="/modelos/relatorio.yaml">Baixar YAML de relatório</a>. Reutilizável em qualquer OS; sem número obrigatório. Nada será salvo sem confirmação.</p>')
                    corpo+=card('Importação rápida de relatório',importar)
                    if responsavel==s['pid']:
                        corpo+=card('Rascunho persistente',
                            botao('Recuperar rascunho',f'/os/{oid}/rascunho','secondary')
                            +'<p class="muted">Seus dados salvos no servidor são recarregados automaticamente ao abrir a OS.</p>')
                if oid:
                    nome_resp=next((p['nome'] for p in prestadores if p['id']==responsavel),'Não atribuído')
                    corpo+=f'<p><span class="tag">{esc(d["status"])}</span> · Responsável: <b>{esc(nome_resp)}</b> · Participantes: {esc(", ".join(p["nome"] for p in particip) or "Nenhum")}</p>'
                    if d['status'] in ext.ATIVAS:
                        em_rota = False
                        try:
                            with ext.db(banco) as c:
                                em_rota = ext.em_rota_atual(c, oid)
                        except Exception:
                            em_rota = False
                        iniciado = bool(andamento and andamento['iniciado_em'])
                        if responsavel != s['pid'] and (responsavel is None or d['status']=='Pendente'):
                            corpo+=f'<form method="post" action="/os/{oid}/assumir">{token}<button type="submit" class="secondary">ASSUMIR OS</button></form>'
                            corpo+='<p class="muted">Assume a responsabilidade sem iniciar o atendimento.</p>'
                        if responsavel in (None, s['pid']) and not iniciado:
                            if em_rota:
                                corpo+='<p class="notice">🚗 EM ROTA — deslocamento iniciado.</p>'
                                corpo+=f'<form method="post" action="/os/{oid}/cancelar-rota">{token}<button type="submit" class="secondary">CANCELAR EM ROTA</button></form>'
                            else:
                                corpo+=f'<form method="post" action="/os/{oid}/em-rota">{token}<button type="submit" class="secondary">EM ROTA</button></form>'
                            corpo+=f'<form method="post" action="/os/{oid}/iniciar">{token}<button type="submit" class="iniciar-atendimento">INICIAR OS</button></form>'
                            corpo+='<p class="muted">INICIAR OS registra o início efetivo do atendimento e encerra o deslocamento. Ao iniciar uma OS sem responsável, ela será atribuída a você com registro explícito.</p>'
                        elif iniciado:
                            corpo+='<p class="good">Atendimento iniciado em '+esc(andamento['iniciado_em'])+' por '+esc(andamento['ator_inicio'])+'.</p>'
                        elif responsavel is not None and responsavel != s['pid']:
                            corpo+='<p class="notice">OS atribuída a outro prestador. Todos podem visualizar; para assumir, aguarde pendência ou peça transferência.</p>'

                if not cl:
                    corpo+='<p class="notice">Cadastre primeiro um cliente.</p>'
                    return self.pagina(titulo,corpo,s)
                dados_cliente=[(x['id'],f'{x["nome"]} — ID {x["id"]}') for x in cl]
                # Carregar rascunho salvo pelo prestador se existir
                try:
                    rasc_salvo = ext.obter_rascunho_web(banco, oid, s['pid']) if oid else None
                    if rasc_salvo:
                        for k,v in rasc_salvo.items():
                            if k.startswith('_'):
                                continue
                            if k not in d and isinstance(v,(str,list)):
                                d[k]=v
                except Exception:
                    rasc_salvo = None
                corpo+=f'<form method="post" action="{action}" id="form-os" enctype="multipart/form-data">{token}'
                if d.get('composicao_yaml'):
                    import json as _json_comp
                    corpo+=('<input type="hidden" name="composicao_yaml" value="'
                            +esc(_json_comp.dumps(d['composicao_yaml'],ensure_ascii=False))+'">')
                servicos_ativos=catalogo.listar(banco,ativos=True)
                if servicos_ativos:
                    import json
                    js_json=json.dumps([{'id':v['id'],'nome':v['nome'],
                        'preco':str(v['preco_servico_centavos']/100),
                        'relatorio':v['relatorio_padrao'],
                        'materiais':json.loads(v['materiais_json'])} for v in servicos_ativos],ensure_ascii=False).replace('<','\\u003c')
                    corpo+=(card('Serviço pré-cadastrado — opcional',
                       '<p>Selecione um modelo de serviço:</p>'
                       +select('Modelo','modelo_servico_id',[('', 'Não utilizar modelo')]+[(v['id'],v['nome']) for v in servicos_ativos])
                       +'<button id="aplicar-modelo-servico" type="button" class="secondary">Preencher dados a partir do modelo</button>'
                       +'<p class="muted">Só é aplicado quando você clicar. Verifique e ajuste os valores e o relatório.</p>')
                       +f'<script type="application/json" id="catalogo-os-json">{js_json}</script>')
                corpo+='<input type="hidden" name="materiais_presentes" value="1">'
                if oid:
                    corpo+=f'<input type="hidden" name="_versao_os" value="{esc(d.get("atualizado_em") or "") }">'
                corpo+='<fieldset><legend>Identificação e serviço</legend><div class="col2"><div>'
                if solicitacao:
                    nome_cliente_solicitacao=next((x['nome'] for x in cl if x['id']==solicitacao['cliente_id']),'')
                    corpo+=('<p class="notice"><strong>Chamado de origem — somente leitura</strong><br>'
                        f'Cliente: {esc(nome_cliente_solicitacao)} · {esc(solicitacao["criado_em"])}<br>'
                        f'{esc(solicitacao["descricao_original"])}<br>'
                        f'<span class="muted">Número da OS: {esc(d.get("numero_os") or "")}. '
                        'O chamado de origem não é o número da OS.</span></p>')
                    corpo+=f'<input type="hidden" name="cliente_id" value="{int(solicitacao["cliente_id"])}">'
                else:
                    corpo+='<label for="busca-cliente-os">Buscar cliente ou condomínio</label><input type="search" id="busca-cliente-os" placeholder="Digite o nome ou ID para localizar" autocomplete="off">'
                    corpo+=select('Cliente','cliente_id',dados_cliente,d.get('cliente_id',cl[0]['id']),required=True)
                corpo+=campos_escuros('Atendido por (cliente no local)','tecnico',d.get('tecnico','') or '')
                corpo+='</div><div>'+select('Forma de pagamento','forma_pagamento',
                    [('', 'Selecione a forma de pagamento')]+[(z,z) for z in neg.OS_FORMAS],
                    d.get('forma_pagamento') or '')
                corpo+=campos_escuros('Valor de mão de obra (R$)','valor_mao_obra',d.get('valor_mao_obra') or '0',required=True)+'</div></div>'
                corpo+='<p class="muted">Serviço em garantia ou cortesia: informe <b>0,00</b> na mão de obra e <b>0,00</b> no valor cobrado dos materiais. ' \
                       'O custo real dos materiais é interno e não entra no total cobrado.</p>'
                corpo+='<div class="col2"><div>'+campos_escuros('Valor de materiais sem itens detalhados (R$)','valor_materiais_manual',d.get('valor_materiais') or '0')+'</div>'
                corpo+='<div>'+campos_escuros('Total negociado (R$), opcional — substitui a soma','valor_total_override',
                  (d.get('valor_total') if d and abs(float(d.get('valor_total') or 0)-float(d.get('valor_mao_obra') or 0)-float(d.get('valor_materiais') or 0))>0.009 else ''))+'</div></div>'
                corpo+=campos_escuros('Custo real dos materiais (R$) — interno, não cobrado','custo_materiais',d.get('custo_materiais') or '0')
                if solicitacao:
                    corpo+=f'<input type="hidden" name="descricao" value="{esc(solicitacao["descricao_original"])}">'
                else:
                    corpo+=textarea('Descrição do serviço','descricao',d.get('descricao') or '',required=True)
                if solicitacao and d.get('origem')=='Portal':
                    obs_origem=str(solicitacao['observacoes_originais'] or '').replace(
                        'Solicitação #','Chamado de origem #').replace(
                        'Solicitação pública','Chamado público')
                    corpo+=f'<p class="muted">Protocolo do chamado (não é o número da OS): {esc(obs_origem)}</p>'
                    corpo+=f'<input type="hidden" name="observacoes" value="{esc(d.get("observacoes") or "") }">'
                else:
                    corpo+=textarea('Observações gerais','observacoes',d.get('observacoes') or '')
                corpo+='</fieldset>'
                corpo+='<fieldset><legend>Materiais utilizados</legend><p class="muted">O total é calculado por mão de obra + materiais; o total negociado, quando informado, prevalece. Materiais detalhados prevalecem sobre o campo de materiais sem itens.</p>'
                linhas=list(mat)
                corpo+='<div id="lista-materiais">'
                for i,m in enumerate(linhas):
                    item=m['item'] if 'item' in m.keys() else ''
                    qtd=m['quantidade'] if 'quantidade' in m.keys() else ''
                    unit=m['valor_unitario'] if 'valor_unitario' in m.keys() else ''
                    corpo+='<div class="material-row">'
                    corpo+=f'<div><label>Material<input name="material_item[]" value="{esc(item)}" placeholder="Cabo, câmera, fonte..."></label></div>'
                    corpo+=f'<div><label>Quantidade<input name="material_qtd[]" value="{esc(qtd)}" placeholder="1"></label></div>'
                    corpo+=f'<div><label>Valor unitário (R$)<input name="material_unit[]" value="{esc(unit)}" placeholder="0,00"></label></div>'
                    corpo+='<button type="button" class="secondary remover-material" title="Remover material">Remover</button></div>'
                corpo+='</div><p class="muted">Nenhum material é obrigatório. Use “Adicionar material” somente se necessário.</p>'
                corpo+='''<template id="modelo-material"><div class="material-row"><div><label>Material<input name="material_item[]" placeholder="Cabo, câmera, fonte..."></label></div><div><label>Quantidade<input name="material_qtd[]" placeholder="1"></label></div><div><label>Valor unitário (R$)<input name="material_unit[]" placeholder="0,00"></label></div><button type="button" class="secondary remover-material">Remover</button></div></template>'''
                corpo+='<button id="adicionar-material" class="secondary" type="button">+ Adicionar material</button>'
                produtos=estoque.listar(banco,ativos=True)
                if produtos:
                    import json as _jm
                    catalogo_json=_jm.dumps([{'nome':x['nome'],'valor':x['venda_centavos']/100} for x in produtos],ensure_ascii=False).replace('<','\\u003c')
                    corpo+='<label for="material-estoque-selecionar">Usar material cadastrado no estoque</label>'
                    corpo+='<select id="material-estoque-selecionar">'+''.join(f'<option value="{i}">{esc(x["nome"])}</option>' for i,x in enumerate(produtos))+'</select>'
                    corpo+='<button class="secondary" id="adicionar-do-estoque" type="button">+ Adicionar do estoque</button>'
                    corpo+=f'<script type="application/json" id="produtos-estoque-os">{catalogo_json}</script>'
                corpo+='<p><strong>Total previsto: <span id="total-previsto">—</span></strong></p></fieldset>'
                corpo+='<fieldset><legend>Situação e relatório técnico</legend>'
                corpo+=textarea('Diagnóstico','v9_diagnostico',d.get('v9_diagnostico',(detalhes['diagnostico'] if detalhes else '')) or '',rows=3)
                corpo+=textarea('Serviço executado','v9_execucao',d.get('v9_execucao',(detalhes['execucao'] if detalhes else '')) or '',rows=4)
                corpo+=textarea('Resultado e testes','v9_resultado',d.get('v9_resultado',(detalhes['resultado'] if detalhes else '')) or '',rows=3)
                corpo+=textarea('Relato técnico complementar (histórico interno)','relatorio_tecnico',d.get('relatorio_tecnico',(andamento['rascunho'] if andamento else '')) or '',rows=4)
                if oid and d['status'] in ext.ATIVAS:
                    if andamento and andamento['iniciado_em']:
                        corpo+=f'<p class="good">Atendimento iniciado em {esc(andamento["iniciado_em"])} por {esc(andamento["ator_inicio"])}</p>'
                    else:
                        corpo+='<p class="warn">OS ainda não iniciada. Assumir uma OS não inicia o atendimento automaticamente.</p>'
                corpo+=textarea('Motivo — obrigatório para serviço cancelado','motivo_encerramento','',rows=3)
                if oid and d['status'] in ext.ATIVAS:
                    corpo+='<p class="notice">Selecione a situação e confirme uma única vez. OS pendente permanece ativa; concluída/cancelada publica PDF para o cliente.</p>'
                    corpo+=select('Situação do atendimento','acao_status',
                        [('', 'Selecione a situação'),('Pendente','Pendente'),('Concluída','Concluído'),('Cancelada','Cancelado')],
                        '',required=True)
                    if contatos_os:
                        selecionados_d = d.get('destinatario_sel[]') or []
                        if isinstance(selecionados_d, str):
                            selecionados_d = [selecionados_d]
                        selecionados_d = [str(x) for x in selecionados_d if str(x).strip()]
                        if not selecionados_d:
                            selecionados_d = ['cliente', 'sindico']
                        corpo+='<fieldset><legend>Destinatários do relatório</legend>'
                        corpo+='<p class="muted">Marque apenas quem deve receber o relatório. A seleção é gravada e usada no envio automático.</p>'
                        for chave,rotulo in (('cliente','Cliente'),('sindico','Síndico'),('administradora','Administradora / imobiliária')):
                            email=contatos_os.get(chave) or ''
                            if email:
                                marcado=' checked' if chave in selecionados_d else ''
                                corpo+=f'<label style="display:block;margin:5px 0"><input type="checkbox" name="destinatario_sel[]" value="{chave}"{marcado}> {rotulo}: {esc(email)}</label>'
                        corpo+=f'<label>E-mails adicionais (separe por vírgula)<input name="emails_adicionais" type="text" maxlength="500" value="{esc(str(d.get("emails_adicionais","")))}" placeholder="financeiro@imobiliaria.com.br"></label>'
                        corpo+='<p class="muted">A lista final é registrada no banco e enviada a todos os destinatários selecionados em um único e-mail.</p></fieldset>'
                    if responsavel==s['pid']:
                        corpo+='<div id="rateio-conclusao"><h3>Técnicos secundários — somente na conclusão</h3>'
                        corpo+='<p class="muted">Distribua valores do mesmo total cobrado à imobiliária. O restante fica com o técnico que conclui a OS. Deixar vazio não cria parcela.</p>'
                        opcoes=[('', 'Sem técnico secundário')]+[(p['id'],p['nome']) for p in prestadores if p['id']!=s['pid']]
                        for i in range(3):
                            corpo+='<div class="col2"><div>'+select('Técnico secundário','rateio_tecnico[]',opcoes,'')+'</div>'
                            corpo+='<div>'+campos_escuros('Valor da parcela (R$)','rateio_valor[]','',placeholder='0,00')+'</div></div>'
                        corpo+='</div>'
                corpo+='</fieldset>'
                if oid and d['status'] in ext.ATIVAS:
                    pode_editar_fotos = (responsavel == s['pid'])
                    pode_nota = (responsavel == s['pid']) or cad9.prestador_admin(banco, s['pid'])
                    corpo+='<fieldset><legend>Fotos do relatório e legendas</legend>'
                    corpo+='<p class="muted">Cada foto recebe uma legenda individual. A legenda é salva no SQLite, reaparece ao reabrir a OS e é incluída no PDF final.</p>'
                    if anexos:
                        corpo+='<div class="fotos-rascunho">'
                        for a in anexos:
                            legenda=esc(a['legenda'] or '')
                            vis=esc(str(a['visivel'] if a['visivel'] is not None else 1))
                            corpo+=('<div class="foto-rascunho" data-anexo-id="'+str(a['id'])+'" style="display:grid;grid-template-columns:150px 1fr;gap:12px;border:1px solid #3b3b3b;padding:10px;margin:10px 0;border-radius:8px">'
                                +'<img src="/arquivos/anexo/'+str(a['id'])+'" alt="Foto da OS" loading="lazy" style="width:150px;height:112px;object-fit:cover;border-radius:6px">'
                                +'<div>')
                            if pode_editar_fotos:
                                corpo+=('<label>Legenda da foto<input name="anexo_legenda[]" maxlength="160" value="'+legenda+'" placeholder="Ex.: Quadro elétrico antes do reparo"></label>'
                                    +'<input type="hidden" name="anexo_id[]" value="'+str(a['id'])+'">'
                                    +select('Incluir no PDF','anexo_visivel[]',[('1','Sim — incluir no PDF'),('0','Não — ocultar por privacidade')],vis))
                            else:
                                corpo+='<p><b>Legenda:</b> '+(legenda or 'Sem legenda')+'</p>'
                            corpo+='</div></div>'
                        corpo+='</div>'
                    if pode_editar_fotos:
                        corpo+='<div id="anexo-encerramento"><label for="fotos-relatorio">Adicionar fotos novas (até 10, 8 MB por foto)</label>'
                        corpo+='<input type="file" id="fotos-relatorio" name="imagens_encerramento[]" multiple accept="image/jpeg,image/png,image/webp">'
                        corpo+='<div id="lista-fotos-selecionadas" aria-live="polite"></div>'
                        corpo+='<button class="secondary" id="limpar-fotos" type="button" hidden>Limpar fotos selecionadas</button>'
                        corpo+='<p class="muted">A prévia e o campo Legenda da foto aparecem abaixo para cada arquivo. Use <b>SALVAR RASCUNHO</b> para guardar fotos e legendas sem finalizar.</p></div>'
                    else:
                        corpo+='<p class="notice">Assuma a OS para adicionar fotos e editar as legendas.</p>'
                    if pode_nota:
                        corpo+='<div id="nota-fiscal-upload" style="margin-top:14px;border-top:1px solid #444;padding-top:12px">'
                        corpo+='<label for="nota-fiscal-pdf">Anexar nota fiscal (PDF, até 20 MB)</label>'
                        corpo+='<input type="file" id="nota-fiscal-pdf" name="nota_fiscal" accept="application/pdf">'
                        corpo+=f'<button class="secondary" type="submit" formaction="/os/{oid}/nota-fiscal" formnovalidate>Anexar nota fiscal</button>'
                        corpo+='<div style="margin-top:12px;padding:12px;border:1px solid #E2B800;border-radius:8px;background:#2a2617">'
                        corpo+='<label style="display:flex;align-items:center;gap:8px;font-weight:700;cursor:pointer"><input type="checkbox" name="sem_nota_fiscal" value="1" style="width:18px;height:18px"> Não precisa de nota fiscal</label>'
                        corpo+='<p class="muted" style="margin:6px 0 0">Marque esta opção ou anexe o PDF da nota fiscal para poder concluir a OS.</p></div>'
                        corpo+='<p class="muted">A nota fiscal aparece na lista de documentos e é anexada ao e-mail de conclusão ou de reenvio.</p></div>'
                    corpo+='</fieldset>'
                if oid:
                    corpo+=f'<p style="margin-top:16px"><span class="tag">{esc(d["status"])}</span> · Responsável: <b>{esc(nome_resp)}</b></p>'
                corpo+='<div class="actions">'
                if not oid:
                    corpo+='<button class="secondary" name="modo_envio" value="salvar" type="submit">Criar OS</button>'
                else:
                    if d['status'] in ext.ATIVAS:
                        if responsavel==s['pid']:
                            corpo+=f'<button class="secondary" type="submit" formaction="/os/{oid}/rascunho/salvar">SALVAR RASCUNHO</button>'
                        else:
                            corpo+='<button class="secondary" name="modo_envio" value="rascunho" type="submit">SALVAR RASCUNHO</button>'
                    else:
                        corpo+='<span class="notice">OS encerrada: edição bloqueada. Documentos publicados ficam no histórico.</span>'
                if oid and d['status'] in ext.ATIVAS:
                    corpo+='<button type="submit" id="confirmar-situacao" name="modo_envio" value="encerrar" data-encerrar="1">Confirmar situação da OS</button>'
                corpo+='</div></form>'
                if not oid:
                    corpo+='<p class="muted">Depois de salvar a OS, você poderá atribuir um prestador e, no encerramento, anexar imagens e publicar PDF.</p>'
                    return self.pagina(titulo,card('Dados da OS',corpo),s)
                # Atribuição e desatribuição administrativas são exclusivas do desktop.
                if d['status'] in ext.ATIVAS:
                    corpo+=card('Atribuição',f'<p>Responsável atual: <b>{esc(next((p["nome"] for p in prestadores if p["id"]==responsavel),"Não atribuído"))}</b></p>'
                        '<p class="muted">Prestadores podem assumir apenas OS não atribuídas. Transferências são feitas no desktop.</p>')
                if anexos and d['status'] not in ext.ATIVAS:
                    itens=[]
                    for a in anexos:
                        vis=imagens_v9.get(a['id'],{})
                        form=(f'<form method="post" action="/os/{oid}/anexo/{a["id"]}/publico">{token}'
                              +campos_escuros('Legenda para o PDF','legenda',vis.get('legenda',''))
                              +select('Incluir no PDF','visivel',[('1','Sim — incluir foto (padrão)'),('0','Não — ocultar por privacidade')],str(vis.get('visivel',1)))
                              +'<button type="submit" class="secondary">Salvar visibilidade</button></form>')
                        itens.append('<div class="card"><img src="/arquivos/anexo/'+str(a['id'])+'" alt="Foto" loading="lazy" style="width:110px;height:90px;object-fit:cover;display:block"><b>'+esc(a['nome_original'])+'</b>'+form+'</div>')
                    corpo+=card('Fotos da OS','<p>As fotos anexadas entram automaticamente no PDF. Se houver informação particular, selecione Ocultar por privacidade. Após alterar uma OS encerrada, publique outra versão do relatório.</p>'+''.join(itens))
                if oid:
                    with ext.db(banco) as c:
                        email_log=c.execute('SELECT status,erro FROM produtividade_email WHERE os_id=?',(oid,)).fetchone()
                    if email_log:
                        corpo+=card('Envio de e-mail',
                            '<p class="'+('good' if email_log['status']=='enviado' else 'warn')+'">Status: '
                            +esc(email_log['status'])+'</p>'
                            +('<p>'+esc(email_log['erro'])+'</p>' if email_log['erro'] else ''))
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
                    if d['status'] in fluxo.FIM and (responsavel==s['pid'] or cad9.prestador_admin(banco,s['pid'])):
                        docs+=(f'<form method="post" action="/os/{oid}/reenviar-email" style="display:inline">'
                               f'{token}<button class="secondary" type="submit">Reenviar e-mail com anexos</button></form>'
                               '<p class="muted">Use após anexar a nota fiscal. O reenvio inclui o PDF do relatório e a NFS-e mais recente.</p>')
                else:
                    docs='<p class="muted">O PDF e o rascunho de e-mail serão liberados após a conclusão/cancelamento e publicação do relatório.</p>'
                itens_notas=''
                for nota in notas_fiscais:
                    itens_notas+=(f'<p><a href="/os/{oid}/nota-fiscal/{nota["id"]}">Baixar {esc(nota["nome_original"])}</a>'
                                  f' <small>{esc(nota["criado_em"])}</small></p>')
                if not itens_notas:
                    itens_notas='<p class="muted">Nenhuma nota fiscal anexada.</p>'
                upload_nf=''
                if responsavel==s['pid'] or cad9.prestador_admin(banco,s['pid']):
                    upload_nf=(f'<form method="post" action="/os/{oid}/nota-fiscal" enctype="multipart/form-data" style="margin-top:10px">'
                               f'{token}'
                               '<label for="nota-fiscal-concluida">Anexar / atualizar nota fiscal (PDF, até 20 MB)</label>'
                               '<input type="file" id="nota-fiscal-concluida" name="nota_fiscal" accept="application/pdf" required>'
                               '<button type="submit" class="secondary">Anexar nota fiscal</button></form>')
                corpo+=card('Notas fiscais da OS',
                            itens_notas +
                            '<p class="muted">A nota fiscal anexada é enviada junto ao relatório no e-mail de conclusão e em cada reenvio. '
                            'O arquivo fica armazenado no servidor e só é liberado para usuários autorizados.</p>'
                            +upload_nf)
                corpo+=card('Documentos e relatórios',docs+'<p class="muted">O e-mail é enviado automaticamente na conclusão. A nota fiscal é anexada ao e-mail quando cadastrada.</p>')
                corpo+=card('Histórico permanente', ''.join(f'<div class="card"><small>{esc(e["criado_em"])} · {esc(e["ator"])}</small><p><b>{esc(e["acao"])}</b> — {esc(e["descricao"])}</p></div>' for e in eventos) or '<p>Nenhum evento.</p>')
                return self.pagina(titulo,card('Dados e execução da OS',corpo),s)

            def financeiro(self,s):
                with ext.db(banco) as c:
                    reg=c.execute('''SELECT f.*,o.numero_os,cl.nome cliente FROM financeiro f
                        JOIN ordens_servico o ON o.id=f.os_id JOIN clientes cl ON cl.id=f.cliente_id
                        JOIN os_encerramentos con ON con.os_id=f.os_id AND con.prestador_id=?
                        ORDER BY f.id DESC''',(s['pid'],)).fetchall()
                pessoal=prod.financeiro_pessoal(banco,s['pid'])
                partes_por_os={item['os_id']:item['partes_centavos']/100
                               for item in pessoal['brutos_proprios']}
                linhas=[]
                for x in reg:
                    acao=(f'<form method="post" action="/financeiro/{x["id"]}/receber" data-confirm="Confirma que o valor foi realmente recebido?">{self.hidden(s)}'
                          '<button type="submit">Confirmar recebimento</button></form>') if x['status']!='Recebido' else '<span class="good">Recebido</span>'
                    minha_parcela=float(x['valor'] or 0)-partes_por_os.get(x['os_id'],0)
                    linhas.append((f'<a href="/os/{x["os_id"]}">{esc(x["numero_os"])}</a>',esc(x['cliente']),
                        dinheiro(x['valor']),dinheiro(minha_parcela),
                        esc(x['forma_pagamento']),esc(x['status']),esc(x['vencimento'] or ''),acao))
                banco_texto=prod.obter_dados_bancarios(banco,s['pid'])
                token=self.hidden(s)
                extras=card('Dados bancários para e-mail de cobrança',
                    f'<form method="post" action="/financeiro/banco/salvar">{token}'
                    +textarea('Dados bancários / Pix (texto livre)','dados_bancarios',banco_texto,rows=5)
                    +'<button type="submit">Salvar meus dados bancários</button></form>')
                dividas=[]
                for item in pessoal['repassar_a_colegas']:
                    devido=item['valor_centavos']-item['pago_centavos']
                    acao=''
                    if devido>0:
                        acao=(f'<form method="post" action="/financeiro/repasse">{token}'
                              +f'<input type="hidden" name="os_id" value="{int(item["os_id"])}">'
                              +f'<input type="hidden" name="secundario_id" value="{int(item["tecnico_id"])}">'
                              +campos_escuros('Valor pago manualmente (R$)','valor',f'{devido/100:.2f}',required=True)
                              +'<button type="submit">Registrar repasse efetuado</button></form>')
                    dividas.append((esc(item['numero_os']),esc(item['tecnico']),dinheiro(item['valor_centavos']/100),
                                   dinheiro(item['pago_centavos']/100),dinheiro(devido/100),acao))
                extras+=card('Repasses manuais a outros técnicos',
                    tabela(['OS','Colega','Parcela','Já repassado','Restante','Ação'],dividas))
                meus=[(esc(x['numero_os']),dinheiro(x['valor_centavos']/100),
                       dinheiro(x['pago_centavos']/100),
                       dinheiro((x['valor_centavos']-x['pago_centavos'])/100))
                      for x in pessoal['receber_de_colegas']]
                extras+=card('Minha produção como técnico secundário',
                    tabela(['OS','Valor','Já recebido (registrado)','Restante'],meus))
                extras+=card('Minha parcela nas OS que eu finalizei',
                    tabela(['OS','Cobrado da imobiliária','Repasses devidos','Minha parcela'],
                        [(esc(x['numero_os']),dinheiro(x['valor']),dinheiro(x['partes_centavos']/100),
                          dinheiro(float(x['valor'])-x['partes_centavos']/100))
                          for x in pessoal['brutos_proprios']]))
                # O KPI é a produção PRÓPRIA do prestador, não o bruto da imobiliária:
                # no encerramento, desconta os rateios dos técnicos secundários;
                # nos rateios em que ele é secundário, soma a parcela dele.
                a_receber=0.0
                recebido=0.0
                for item in pessoal['brutos_proprios']:
                    parte=float(item['valor'] or 0)-item['partes_centavos']/100
                    if item['status']=='Recebido':
                        recebido+=parte
                    elif item['status']=='Aguardando pagamento':
                        a_receber+=parte
                for item in pessoal['receber_de_colegas']:
                    recebido+=item['pago_centavos']/100
                    a_receber+=(item['valor_centavos']-item['pago_centavos'])/100
                a_receber=round(a_receber,2)
                recebido=round(recebido,2)
                return self.pagina('Financeiro',f'<div class="kpis"><div class="kpi"><span>A receber (minha produção)</span><strong>{dinheiro(a_receber)}</strong></div>'
                    f'<div class="kpi"><span>Recebido (minha produção)</span><strong>{dinheiro(recebido)}</strong></div></div>'
                    +'<p class="notice">A forma de pagamento PIX não comprova recebimento. Use “Confirmar recebimento” apenas após verificar o pagamento.</p>'
                    +'<p class="muted">Os lançamentos abaixo mostram o valor bruto cobrado da imobiliária. '
                    'Os KPIs acima mostram somente a sua parcela, já descontados os rateios dos técnicos secundários.</p>'
                    +card('Lançamentos financeiros das OS que eu finalizei',
                        tabela(['OS','Cliente','Valor bruto','Minha parcela','Forma','Status','Vencimento','Ação'],linhas))+extras,s)

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
                url_cliente='http://127.0.0.1:'+os.environ.get('CLIENTE_PORT','8765')+'/'
                info=botao('Abrir Portal do Cliente (8765)',url_cliente)
                info+=('<p class="muted">O Portal do Cliente é um site separado, na porta 8765. '
                       'O login dele é por CPF e senha e não se mistura com o login do prestador. '
                       'As solicitações registradas lá aparecem nesta lista e no desktop.</p>')
                with ext.db(banco) as c:
                    web=c.execute("SELECT id,numero_os,status,data_abertura FROM ordens_servico WHERE origem='Portal' ORDER BY id DESC LIMIT 100").fetchall()
                registros=[(f'<a href="/os/{o["id"]}">{esc(o["numero_os"])}</a>',esc(o['status']),esc(o['data_abertura'])) for o in web]
                return self.pagina('Portal do cliente',info+card('Solicitações recebidas pelo portal',tabela(['OS','Situação','Abertura'],registros)),s)

            def documentos(self,s,oid,kind):
                prod.controlar_pdf(banco,oid,s['pid'])
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
                        arq=ext.criar_email_rascunho(banco,oid,pdf,prestador_id=s['pid']);mime='message/rfc822'
                    elif kind=='nota':
                        arq=ext.criar_rascunho_fiscal(banco,oid);mime='application/json; charset=utf-8'
                    else:return self.erro('Arquivo inválido.',404,s)
                    with ext.db(banco) as c:
                        neg.audit(c,s['pid'],'Documento gerado',oid,kind)
                    return self.send_bytes(Path(arq).read_bytes(),mime,filename=Path(arq).name)

            def anexo(self,s,aid):
                with ext.db(banco) as c:
                    x=c.execute('SELECT os_id,nome_original,caminho FROM os_anexos WHERE id=?',(aid,)).fetchone()
                    if x and not prod.participou(c,x['os_id'],s['pid']):
                        raise PermissionError('Anexo restrito aos técnicos participantes.')
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
                    if path=='/static/portal.js':
                        return self.send_bytes((Path(__file__).parent/'portal.js').read_bytes(),'application/javascript; charset=utf-8')
                    if path in ('/logo.png','/icone.png','/favicon.ico'):
                        if path == '/logo.png':
                            arquivo = ext.BASE/'logo.png'
                            if not arquivo.is_file():
                                arquivo = Path(__file__).parent/'logo.png'
                        else:
                            arquivo = (ext.caminho_icone(ext.BASE)
                                       or ext.caminho_icone(Path(__file__).parent))
                        if arquivo and arquivo.is_file():
                            return self.send_bytes(arquivo.read_bytes(),'image/png')
                        return self.erro('Imagem não encontrada.',404,self.sessao())
                    if path=='/prestadores' or path.startswith('/prestadores/'):
                        return self.erro('O cadastro de prestadores é feito somente no aplicativo desktop.',403,self.sessao())
                    if path in ('/cliente','/pj') or path.startswith('/cliente/') or path.startswith('/pj/'):
                        return self.erro('O Portal do Cliente fica em http://127.0.0.1:8765/ (porta 8765). '
                                         'Este endereço é o Portal do Prestador.',404,self.sessao())
                    s=self.sessao()
                    if not s:return self.login()
                    if path in ('/modelos/cadastro.yaml','/modelos/relatorio.yaml','/modelos/servico.yaml','/modelos/orcamento.yaml'):
                        nome={'/modelos/cadastro.yaml':'modelo_cadastro_cliente.yaml','/modelos/relatorio.yaml':'modelo_relatorio_os.yaml','/modelos/servico.yaml':'modelo_servico.yaml','/modelos/orcamento.yaml':'modelo_orcamento.yaml'}[path]
                        arquivo=Path(__file__).parent/nome
                        return self.send_bytes(arquivo.read_bytes(),'application/x-yaml; charset=utf-8',filename=nome)
                    if path=='/feedback/recebidos':
                        if not s.get('admin'):
                            raise PermissionError('Feedbacks recebidos são visíveis apenas para administradores.')
                        qs=parse_qs(urlparse(self.path).query)
                        status_dev=str(qs.get('status',[''])[0]).strip()
                        if status_dev and status_dev not in feedback.STATUS_TRIAGEM:
                            status_dev=''
                        return self.feedback_admin(s,status_dev=status_dev)
                    if path=='/feedback/pendencias.md':
                        if not s.get('admin'):
                            raise PermissionError('Pendências de feedback são visíveis apenas para administradores.')
                        with ext.db(banco) as c:
                            neg.audit(c,s['pid'],'Feedback exportado','pendencias','markdown')
                        corpo=feedback.pendencias_markdown(banco).encode('utf-8')
                        return self.send_bytes(corpo,'text/markdown; charset=utf-8',
                                               filename='pendencias_feedback_dev.md')
                    if path=='/feedback/dados/exportar.json':
                        if not s.get('admin'):
                            raise PermissionError('Exportação de feedback restrita a administradores.')
                        with ext.db(banco) as c:
                            neg.audit(c,s['pid'],'Feedback exportado','dados','json')
                        corpo=json.dumps(feedback.exportar_dados(banco),ensure_ascii=False,
                                         indent=2).encode('utf-8')
                        return self.send_bytes(corpo,'application/json; charset=utf-8',
                                               filename='feedback_export.json')
                    partes_feedback=path.strip('/').split('/')
                    if len(partes_feedback)==2 and partes_feedback[0]=='feedback' and partes_feedback[1].isdigit():
                        return self.feedback_detalhe(s,int(partes_feedback[1]))
                    if path in ('/chamados','/organizacoes'):
                        return self.redir('/os' if path=='/chamados' else '/clientes')
                    if path in ('/clientes/responsaveis','/organizacoes/responsaveis'):
                        return v9.get(self,'/organizacoes/responsaveis',banco,s)
                    if path=='/':return self.inicio(s)
                    if path=='/os':return self.os_lista(s)
                    if path=='/pj-publicas':return self.pj_publicas(s)
                    if path=='/servicos':return self.servicos_lista(s)
                    if path=='/servicos/novo':return self.servico_form(s)
                    if path=='/historico':return self.os_lista(s,True)
                    if path=='/os/rapida':
                        qs=parse_qs(urlparse(self.path).query)
                        q=qs.get('q',[''])[0][:120]
                        try:cliente_rapido=int(qs.get('cliente',['0'])[0]) or None
                        except (ValueError,TypeError):cliente_rapido=None
                        return self.os_rapida_form(s,q=q,cliente_id=cliente_rapido)
                    if path=='/os/nova':return self.os_form(s)
                    if path=='/clientes':return self.clientes_lista(s)
                    if path=='/orcamento':
                        qs=parse_qs(urlparse(self.path).query)
                        try:cliente_orcamento=int(qs.get('cliente_id',['0'])[0]) or None
                        except (ValueError,TypeError):cliente_orcamento=None
                        return self.orcamento_form(s,cliente_id=cliente_orcamento)
                    if path=='/clientes/novo':return self.cliente_form(s)
                    if path=='/financeiro':return self.financeiro(s)
                    if path=='/relatorios':return self.redir('/historico')
                    if path=='/emails':return self.relatorios(s,'emails')
                    if path=='/notas':return self.relatorios(s,'notas')
                    if path=='/portal-cliente':return self.portal_cliente(s)
                    partes=path.strip('/').split('/')
                    if len(partes)==3 and partes[0]=='servicos' and partes[1].isdigit() and partes[2]=='editar':
                        return self.servico_form(s,int(partes[1]))
                    if len(partes)==2 and partes[0]=='clientes' and partes[1].isdigit():
                        return self.cliente_form(s,int(partes[1]))
                    if len(partes)==2 and partes[0]=='os' and partes[1].isdigit():
                        return self.os_form(s,int(partes[1]))
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='rascunho':
                        oid=int(partes[1])
                        rascunho=prod.recuperar_rascunho(banco,oid,s['pid'])
                        if not rascunho:return self.erro('Nenhum rascunho salvo para esta OS.',404,s)
                        return self.os_form(s,oid,preenchimento=rascunho['dados'])
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit() and partes[2] in ('pdf','email','nota'):
                        return self.documentos(s,int(partes[1]),partes[2])
                    if len(partes)==4 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='nota-fiscal' and partes[3].isdigit():
                        oid=int(partes[1]);nid=int(partes[3])
                        with ext.db(banco) as c:
                            if ext.responsavel_atual(c,oid)!=s['pid'] and not cad9.prestador_admin(banco,s['pid']):
                                raise PermissionError('Nota fiscal restrita ao responsável ou administrador.')
                        registro,caminho=ext.obter_nota_fiscal(banco,oid,nid)
                        return self.send_bytes(Path(caminho).read_bytes(),'application/pdf',
                                               filename=registro['nome_original'])
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
                        SESSOES[tok]={'pid':p['id'],'nome':p['nome'],'cred':p['senha_hash'],
                                      'csrf':secrets.token_urlsafe(32),
                                      'telemetry_session':secrets.token_urlsafe(18),
                                      'exp':time.time()+28800}
                        return self.redir('/',self.cookie(tok))
                    s=self.sessao()
                    self.csrf(s,d)
                    if path=='/sair':
                        cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
                        if 'autosseg_session' in cookie:SESSOES.pop(cookie['autosseg_session'].value,None)
                        return self.redir('/',self.cookie('',True))
                    pid=s['pid']
                    if path=='/feedback/aberto':
                        pagina=str(d.get('pagina') or urlparse(self.headers.get('Referer','')).path or '/')[:300]
                        meta=feedback.contexto(banco,s,
                                               feedback.ip_requisicao(self.client_address[0],self.headers),
                                               self.headers.get('User-Agent',''))
                        feedback.registrar_abertura(banco,s,pagina,meta)
                        return self.send_bytes(b'','text/plain; charset=utf-8',status=204)
                    if path=='/feedback':
                        pagina=str(d.get('pagina') or urlparse(self.headers.get('Referer','')).path or '/')[:300]
                        meta=feedback.contexto(banco,s,
                                               feedback.ip_requisicao(self.client_address[0],self.headers),
                                               self.headers.get('User-Agent',''))
                        try:
                            fid,_=feedback.criar(
                                banco,s,pagina,str(d.get('mensagem','')),
                                str(d.get('responder_ia','')) in ('1','on','true','sim'),
                                meta)
                        except ValueError as erro:
                            return self.pagina('Feedback não enviado',
                                card('Não foi possível enviar',
                                     f'<p class="bad">{esc(erro)}</p>'
                                     '<p>Seu texto não foi perdido pelo sistema; volte e tente novamente.</p>'
                                     +botao('Voltar ao início','/','secondary')),s,400)
                        return self.redir(f'/feedback/{fid}')
                    partes_feedback=path.strip('/').split('/')
                    if len(partes_feedback)==3 and partes_feedback[0]=='feedback' and partes_feedback[1].isdigit() and partes_feedback[2]=='triagem':
                        if not s.get('admin'):
                            raise PermissionError('Somente administradores podem triar feedbacks.')
                        feedback.triar(banco,int(partes_feedback[1]),str(d.get('status_dev','')),
                                       str(d.get('nota_dev','')),s)
                        return self.redir(f'/feedback/{int(partes_feedback[1])}')
                    if path.startswith('/chamados/') or path.startswith('/organizacoes/') or path=='/organizacoes/mesclar' or (path.startswith('/clientes/') and path.endswith('/desativar')):
                        return v9.post(self,path,d,banco,s)
                    partes=path.strip('/').split('/')
                    if path=='/servicos/yaml':
                        arq=d.get('yaml')
                        if not isinstance(arq,tuple):raise ValueError('Selecione um arquivo YAML de serviço.')
                        return self.servico_form(s,preenchimento=yaml_import.servico(arq[0],arq[1]))
                    if path=='/servicos/salvar':
                        sid=str(d.get('servico_id','')).strip()
                        try:catalogo.salvar(banco,d,int(sid) if sid else None)
                        except ValueError as e:return self.servico_form(s,int(sid) if sid else None,preenchimento=d,erro=str(e))
                        return self.redir('/servicos')
                    if len(partes)==3 and partes[0]=='servicos' and partes[1].isdigit() and partes[2]=='arquivar':
                        catalogo.arquivar(banco,int(partes[1]))
                        return self.redir('/servicos')
                    if len(partes)==3 and partes[0]=='servicos' and partes[1].isdigit() and partes[2]=='excluir':
                        catalogo.excluir(banco,int(partes[1]))
                        return self.redir('/servicos')
                    if len(partes)==3 and partes[0]=='servicos' and partes[1].isdigit() and partes[2]=='reativar':
                        catalogo.reativar(banco,int(partes[1]))
                        return self.redir('/servicos')
                    if path=='/clientes/yaml':
                        arq=d.get('yaml')
                        if not isinstance(arq,tuple):raise ValueError('Selecione um arquivo YAML.')
                        pre=yaml_import.cliente(arq[0],arq[1])
                        return self.cliente_form(s,preenchimento=pre)
                    if path=='/orcamento/yaml':
                        arq=d.get('yaml')
                        if not isinstance(arq,tuple):
                            raise ValueError('Selecione um arquivo YAML de orçamento.')
                        try:
                            pre=yaml_import.orcamento(arq[0],arq[1],banco)
                        except ValueError as erro:
                            return self.orcamento_form(s,erro=str(erro))
                        if not pre:
                            return self.orcamento_form(
                                s,erro='O YAML está em branco. Preencha a seção "orcamento" '
                                       'e remova as instruções antes de importar.')
                        return self.orcamento_form(
                            s,cliente_id=pre['cliente_id'],
                            servicos=pre['servicos'],materiais=pre['materiais'],
                            aviso='YAML importado. Confira cliente, serviços, materiais e '
                                  'quantidades antes de gerar o PDF.')
                    if path=='/orcamento/pdf':
                        try:
                            cliente_id=int(str(d.get('cliente_id','')).strip())
                        except (TypeError,ValueError):
                            return self.orcamento_form(s,'Selecione o cliente.',None)
                        with ext.db(banco) as c:
                            cliente=c.execute('SELECT id,nome,documento FROM clientes '
                                              'WHERE id=? AND status!=\'Inativo\'',
                                              (cliente_id,)).fetchone()
                        if not cliente:
                            return self.orcamento_form(s,'Cliente não encontrado.',cliente_id)
                        try:
                            itens=catalogo.itens_orcamento_formulario(banco,d)
                        except ValueError as erro:
                            try:
                                brutos=catalogo.linhas_orcamento_formulario(d)
                            except ValueError:
                                brutos={'servicos':None,'materiais':None}
                            return self.orcamento_form(
                                s,str(erro),cliente_id=cliente_id,
                                servicos=brutos['servicos'],materiais=brutos['materiais'])
                        try:
                            if len(itens['servicos'])==1 and not itens['materiais']:
                                servico=itens['servicos'][0]
                                pdf=catalogo.pdf_orcamento(
                                    banco,servico['id'],servico['quantidade'],
                                    cliente=cliente['nome'],
                                    cliente_documento=cliente['documento'] or '')
                                nome_pdf=f'Orcamento_{cliente_id}_{servico["id"]}.pdf'
                            else:
                                pdf=catalogo.pdf_orcamento_itens(
                                    banco,cliente['nome'],cliente['documento'] or '',itens)
                                nome_pdf=f'Orcamento_{cliente_id}.pdf'
                        except ValueError as erro:
                            return self.orcamento_form(
                                s,str(erro),cliente_id=cliente_id,
                                servicos=itens['servicos'],materiais=itens['materiais'])
                        return self.send_bytes(pdf,'application/pdf',filename=nome_pdf)
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='yaml':
                        oid=int(partes[1]);arq=d.get('yaml')
                        if not isinstance(arq,tuple):raise ValueError('Selecione um arquivo YAML.')
                        with ext.db(banco) as c:
                            os_atual=c.execute('SELECT numero_os,status FROM ordens_servico WHERE id=?',(oid,)).fetchone()
                        if not os_atual or os_atual['status'] not in ext.ATIVAS:
                            raise ValueError('Somente OS ativas podem importar relatório.')
                        try:pre=yaml_import.relatorio(arq[0],arq[1])
                        except ValueError as erro:return self.os_form(s,oid,erro=str(erro))
                        if not pre:
                            return self.os_form(s,oid,erro='O YAML está em branco. Preencha a seção "os" antes de importar.')
                        pre['_substituir']=str(d.get('substituir',''))=='1'
                        return self.os_form(s,oid,preenchimento=pre)
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
                    if path=='/os/rapida/salvar':
                        texto=(str(d.get('cliente_id','')).strip()
                               or str(d.get('cliente_texto','')).strip())
                        try:
                            cliente_id=int(texto.split('—',1)[0].strip())
                        except (ValueError,TypeError):
                            return self.os_rapida_form(s,erro='Selecione um cliente/condomínio válido na lista.')
                        descricao=str(d.get('descricao','')).strip()
                        if len(descricao)<5:
                            return self.os_rapida_form(s,erro='Descreva a solicitação com pelo menos 5 caracteres.',
                                                       cliente_id=cliente_id)
                        forma=str(d.get('forma_pagamento','')).strip()
                        if forma not in neg.OS_FORMAS:
                            return self.os_rapida_form(
                                s, erro='Escolha a forma de pagamento.',
                                cliente_id=cliente_id)
                        dados={'cliente_id':str(cliente_id),'descricao':descricao,'tecnico':'',
                               'forma_pagamento':forma,'valor_mao_obra':'0','valor_materiais_manual':'0',
                               'materiais_presentes':'1','acao_status':'salvar'}
                        oid=neg.os_salvar(banco,dados,pid)
                        prestador_id=str(d.get('prestador_id','')).strip()
                        if prestador_id:
                            ext.atribuir(banco,oid,int(prestador_id),ator=f'Prestador {s["nome"]}')
                        return self.redir(f'/os/{oid}')
                    if path=='/os/nova/salvar':
                        oid=neg.os_salvar(banco,d,pid)
                        return self.redir(f'/os/{oid}')
                    if len(partes)==5 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='anexo' and partes[3].isdigit() and partes[4]=='publico':
                        oid=int(partes[1]);aid=int(partes[3])
                        with ext.db(banco) as c:
                            ok=c.execute('SELECT 1 FROM os_anexos WHERE id=? AND os_id=?',(aid,oid)).fetchone()
                        if not ok:raise ValueError('Anexo não pertence à OS.')
                        with ext.db(banco) as c:
                            if ext.responsavel_atual(c,oid)!=pid and not cad9.prestador_admin(banco,pid):
                                raise PermissionError('Somente o técnico responsável ou administrador edita a legenda do anexo.')
                        cad9.aprovar_anexo(banco,aid,str(d.get('visivel','0'))=='1',str(d.get('legenda','')),s['nome'])
                        return self.redir(f'/os/{oid}')
                    if len(partes)==4 and partes[0]=='os' and partes[1].isdigit() and partes[2:] == ['rascunho','salvar']:
                        oid=int(partes[1])
                        prod.salvar_rascunho(banco,oid,pid,d)
                        dados_rasc = {k: d[k] for k in d.keys() if k not in ('csrf','modo_envio','nota_fiscal')}
                        ext.salvar_rascunho_web(banco,oid,pid,dados_rasc)
                        sem_fechar = dict(d)
                        sem_fechar['acao_status'] = 'salvar'
                        neg.os_salvar(banco,sem_fechar,pid,oid)
                        try:
                            cad9.salvar_detalhes(banco,oid,str(d.get('v9_diagnostico','')),str(d.get('v9_execucao','')),str(d.get('v9_resultado','')))
                        except Exception:
                            pass
                        if str(d.get('relatorio_tecnico','')).strip():
                            with ext.db(banco) as c:
                                aten.salvar_rascunho(c,oid,str(d.get('relatorio_tecnico','')),f'Prestador {s["nome"]}')
                        # A nota fiscal anexada no mesmo envio é gravada junto com o rascunho.
                        arquivo=d.get('nota_fiscal')
                        if isinstance(arquivo,tuple) and arquivo[0]:
                            try:
                                ext.salvar_nota_fiscal(banco,oid,pid,arquivo[0],arquivo[1])
                            except Exception as falha:
                                LOG.exception('Falha ao salvar NF no rascunho da OS %s', oid)
                        return self.pagina('Rascunho salvo',card('Rascunho',
                            '<p class="good">Rascunho salvo com sucesso. Ele será recuperado ao reabrir esta OS.</p>'
                            +botao('Voltar à OS',f'/os/{oid}')),s)
                    if len(partes)==3 and partes[0]=='pj-publicas' and partes[1].isdigit() and partes[2] in ('aceitar','recusar'):
                        sid=int(partes[1])
                        if partes[2]=='aceitar':
                            resultado=pj_publico.aceitar(banco,sid,ator=s['nome'])
                            return self.redir(f'/os/{resultado["os_id"]}')
                        pj_publico.recusar(banco,sid,str(d.get('motivo','')),ator=s['nome'])
                        return self.redir('/pj-publicas')
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit() and partes[2]=='nota-fiscal':
                        oid=int(partes[1])
                        arquivo=d.get('nota_fiscal')
                        if not isinstance(arquivo,tuple) or not arquivo[0]:
                            raise ValueError('Selecione um arquivo PDF de nota fiscal.')
                        with ext.db(banco) as c:
                            if ext.responsavel_atual(c,oid)!=pid and not cad9.prestador_admin(banco,pid):
                                raise PermissionError('Somente o responsável ou administrador pode anexar nota fiscal.')
                        # Anexar a NF não deve apagar os campos já preenchidos no formulário.
                        try:
                            dados_rasc = {k: d[k] for k in d.keys() if k not in ('csrf','modo_envio','nota_fiscal')}
                            ext.salvar_rascunho_web(banco,oid,pid,dados_rasc)
                            try:
                                cad9.salvar_detalhes(banco,oid,str(d.get('v9_diagnostico','')),
                                                     str(d.get('v9_execucao','')),str(d.get('v9_resultado','')))
                            except Exception:
                                pass
                            if str(d.get('relatorio_tecnico','')).strip():
                                with ext.db(banco) as c:
                                    aten.salvar_rascunho(c,oid,str(d.get('relatorio_tecnico','')),f'Prestador {s["nome"]}')
                        except Exception as falha:
                            LOG.exception('Falha ao preservar rascunho ao anexar NF na OS %s', oid)
                        ext.salvar_nota_fiscal(banco,oid,pid,arquivo[0],arquivo[1])
                        return self.redir(f'/os/{oid}')
                    if len(partes)==3 and partes[0]=='os' and partes[1].isdigit():
                        oid=int(partes[1]);acao=partes[2]
                        if acao=='rota':
                            prod.marcar_em_rota(banco,oid,pid,str(d.get('ativo','0'))=='1')
                            return self.redir(f'/os/{oid}')
                        if acao=='salvar':
                            if d.get('modo_envio') in ('rascunho','salvar'):
                                try:
                                    dados_rasc = {k: d[k] for k in d.keys() if k not in ('csrf','modo_envio')}
                                    ext.salvar_rascunho_web(banco, oid, pid, dados_rasc)
                                    d2 = dict(d)
                                    d2['acao_status'] = 'salvar'
                                    try:
                                        neg.os_salvar(banco,d2,pid,oid)
                                    except Exception:
                                        pass
                                    try:
                                        cad9.salvar_detalhes(banco,oid,str(d.get('v9_diagnostico','')),str(d.get('v9_execucao','')),str(d.get('v9_resultado','')))
                                    except Exception:
                                        pass
                                    if d.get('relatorio_tecnico'):
                                        try:
                                            with ext.db(banco) as c:
                                                aten.salvar_rascunho(c,oid,str(d.get('relatorio_tecnico','')) or '', f'Prestador {s["nome"]}')
                                        except Exception:
                                            pass
                                    arquivo=d.get('nota_fiscal')
                                    if isinstance(arquivo,tuple) and arquivo[0]:
                                        try:
                                            ext.salvar_nota_fiscal(banco,oid,pid,arquivo[0],arquivo[1])
                                        except Exception as falha:
                                            LOG.exception('Falha ao salvar NF no rascunho da OS %s', oid)
                                    return self.pagina('Rascunho salvo',card('Rascunho',
                                        '<p class="good">Rascunho salvo com sucesso.</p>'+botao('Voltar à OS',f'/os/{oid}')),s)
                                except Exception as e:
                                    return self.erro(str(e),400,s)
                            acao_status = str(d.get('acao_status',''))
                            if acao_status in ('Pendente','Concluída','Cancelada') and not d.get('modo_envio'):
                                d = dict(d); d['modo_envio'] = 'encerrar'
                            if d.get('modo_envio')!='encerrar':raise ValueError('Use Confirmar situação da OS.')
                            if acao_status not in ('Pendente','Concluída','Cancelada'):
                                raise ValueError('Selecione a situação da OS: Pendente, Concluída ou Cancelada.')
                            # Só o botão de encerramento aplica o status escolhido.
                            if d.get('modo_envio')=='encerrar' and str(d.get('acao_status',''))=='Concluída' and not (str(d.get('v9_execucao','')).strip() or str(d.get('relatorio_tecnico','')).strip()):
                                raise ValueError('Preencha Serviço executado antes de concluir.')
                            # Exige nota fiscal (ou a opção "não precisa") para concluir a OS.
                            if (d.get('modo_envio')=='encerrar' and str(d.get('acao_status',''))=='Concluída'
                                    and not d.get('sem_nota_fiscal')
                                    and not ext.listar_notas_fiscais(banco, oid)):
                                raise ValueError('Anexe a nota fiscal ou marque "Não precisa de nota fiscal" antes de concluir.')
                            if not str(d.get('relatorio_tecnico','')).strip():
                                d['relatorio_tecnico']='\n'.join(str(d.get(x,'')).strip() for x in ('v9_diagnostico','v9_execucao','v9_resultado') if str(d.get(x,'')).strip())
                            with ext.db(banco) as c:
                                prod._os_ativa_responsavel(c,oid,pid)
                            if str(d.get('acao_status','')) in ('Concluída','Pendente'):
                                destinatarios=prod.destinatarios_para_os(
                                    banco,oid,d.get('destinatario_sel[]'),
                                    str(d.get('emails_adicionais','')))
                            else:
                                destinatarios=None
                            neg.os_salvar(banco,d,pid,oid)
                            prod.limpar_rota_ao_iniciar(banco,oid)
                            if d.get('acao_status') in ('Pendente','Concluída'):
                                prod.registrar_etapa(banco,oid,pid,str(d.get('acao_status')),d)
                            if destinatarios:
                                prod.registrar_envio(banco,oid,destinatarios)
                            cad9.salvar_detalhes(banco,oid,str(d.get('v9_diagnostico','')),str(d.get('v9_execucao','')),str(d.get('v9_resultado','')))
                            if str(d.get('acao_status','')) in fluxo.PUBLICAVEIS:
                                try: fluxo.publicar_relatorio(banco,oid)
                                except Exception as falha:
                                    LOG.exception('Encerrada OS %s, mas falhou a publicação do PDF',oid)
                                    return self.pagina('OS encerrada — PDF pendente',card('Encerramento salvo',
                                        '<p>Os dados da OS foram preservados. Falhou apenas a publicação do PDF.</p>'
                                        +f'<p class="bad">{esc(str(falha)[:400])}</p>'
                                        +botao('Abrir OS e republicar PDF',f'/os/{oid}')),s,503)
                                if destinatarios:
                                    # Disparo automático do e-mail em segundo plano:
                                    # nunca bloqueia a resposta da conclusão da OS.
                                    try:
                                        import gmail_service
                                        gmail_service.enviar_relatorio_os_concluida(banco, oid, destinatarios)
                                    except Exception as falha:
                                        LOG.exception('Gmail: OS %s — falha ao agendar envio', oid)
                                        prod.registrar_envio(banco, oid, destinatarios, 'falhou', erro=str(falha))
                        elif acao=='publicar':
                            fluxo.publicar_relatorio(banco,oid)
                        elif acao in ('atribuir','liberar'):
                            raise PermissionError('Atribuição administrativa disponível apenas no desktop.')
                        elif acao=='assumir':
                            ext.assumir(banco,oid,pid)
                        elif acao=='em-rota':
                            ext.marcar_em_rota(banco,oid,pid,ator=f'Prestador {s["nome"]}')
                        elif acao=='cancelar-rota':
                            ext.cancelar_em_rota(banco,oid,pid,ator=f'Prestador {s["nome"]}')
                        elif acao=='iniciar':
                            aten.iniciar_assumindo(banco,oid,pid)
                            prod.limpar_rota_ao_iniciar(banco,oid)
                        elif acao=='reenviar-email':
                            with ext.db(banco) as c:
                                if ext.responsavel_atual(c,oid)!=pid and not cad9.prestador_admin(banco,pid):
                                    raise PermissionError('Somente o responsável ou administrador pode reenviar o e-mail.')
                                registro=c.execute('SELECT destinatarios_json FROM produtividade_email WHERE os_id=?',(oid,)).fetchone()
                            destinatarios=None
                            if registro and registro['destinatarios_json']:
                                try:destinatarios=json.loads(registro['destinatarios_json'])
                                except Exception:destinatarios=None
                            # Republica o PDF com as imagens/legendas atuais antes de reenviar.
                            try:
                                fluxo.publicar_relatorio(banco,oid)
                            except Exception:
                                pass
                            import gmail_service
                            gmail_service.enviar_relatorio_os_concluida(banco,oid,destinatarios)
                        else:return self.erro('Operação desconhecida.',404,s)
                        return self.redir(f'/os/{oid}')
                    if path=='/financeiro/banco/salvar':
                        prod.salvar_dados_bancarios(banco,pid,str(d.get('dados_bancarios','')))
                        return self.redir('/financeiro')
                    if path=='/financeiro/repasse':
                        prod.confirmar_repasse(banco,int(d['os_id']),pid,int(d['secundario_id']),str(d['valor']))
                        return self.redir('/financeiro')
                    if len(partes)==3 and partes[0]=='financeiro' and partes[1].isdigit() and partes[2]=='receber':
                        with ext.db(banco) as c:
                            autorizado=c.execute('''SELECT 1 FROM financeiro f JOIN os_encerramentos con ON con.os_id=f.os_id
                                WHERE f.id=? AND con.prestador_id=?''',(int(partes[1]),pid)).fetchone()
                        if not autorizado:raise PermissionError('Financeiro restrito ao técnico finalizador.')
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
