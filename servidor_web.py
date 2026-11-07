"""
Portal do Cliente AUTOSEG — site completo na porta 8765.

Arquitetura obrigatória do AUTOSEG:

  * http://127.0.0.1:8765/  -> Portal do Cliente (este arquivo)
  * http://127.0.0.1:8766/  -> Portal do Prestador (portal_prestador.py)
  * aplicativo desktop       -> gtk_app.py

Os dois sites usam o MESMO banco SQLite (dados.db) e as mesmas regras de
negócio. Este módulo não redireciona para a 8766: ele serve o portal inteiro
(login, cadastro, OS particular, chamados para condomínio/empresa,
acompanhamento e PDFs) na própria porta 8765.

Login principal: CPF + senha (hash PBKDF2 em prestadores_ext).
O acesso histórico por ID + senha continua em /legado, sem link na página
principal e sempre exigindo senha. Não existe login por telefone/e-mail/CNPJ.
"""
from __future__ import annotations

import html
import json
import mimetypes
import os
import sqlite3
import logging
from logging.handlers import RotatingFileHandler
import queue
import secrets
import socket
import socketserver
import threading
import time
import traceback
from email.parser import BytesParser
from email.policy import default as email_policy
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from banco import BANCO, PASTA_APP, criar_banco
import cadastros_v9 as cad
import catalogo_servicos as catalogo
import atendimento_os as aten
import produtividade_os as prod
import cliente_fluxo_v94 as fluxo_pf
import fluxo_os as fluxo
import portal_cliente_v94 as cliente
import prestadores_ext as ext
from versao_app import versao_local
from repositorios import ordens as ordens_repo

VERSAO = versao_local('9.6.0')
PORTA_PADRAO = 8765
PASTA_WEB = os.path.join(PASTA_APP, 'web')
MAX_POST = 10 * 1024 * 1024

# Diagnóstico persistente: não registra CPF, senhas nem dados de formulários.
LOG = logging.getLogger('autoseg.portal_cliente')
if not LOG.handlers:
    _log_dir = Path(PASTA_APP) / 'logs'
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_handler = RotatingFileHandler(_log_dir / 'portal_cliente.log', maxBytes=500_000, backupCount=3, encoding='utf-8')
    _log_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    LOG.addHandler(_log_handler)
LOG.setLevel(logging.WARNING)

SESSOES_LEGADO = {}
FALHAS_LEGADO = {}
LOCK_LEGADO = threading.Lock()


def obter_ip_local():
    """IP da rede local, com fallback seguro quando não há rede ativa."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.6)
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'


class _ServidorHTTP(ThreadingHTTPServer):
    """HTTPServer sem consulta de DNS reverso (evita travas no macOS)."""

    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        host, porta = self.server_address[:2]
        self.server_name = host or 'localhost'
        self.server_port = porta


class ServidorPortal:
    """Servidor HTTP do Portal do Cliente (porta 8765)."""

    def __init__(self, caminho_banco=None, pasta_app=None, pasta_web=None,
                 porta=PORTA_PADRAO, host='0.0.0.0'):
        self.caminho_banco = caminho_banco or BANCO
        self.pasta_app = Path(pasta_app or PASTA_APP)
        self.pasta_web = Path(pasta_web or PASTA_WEB)
        self.host = host
        self.porta_solicitada = int(porta)
        self.httpd = None
        self.thread = None
        self.erro = None
        self.iniciado_em = None
        self.eventos = queue.Queue()
        criar_banco(self.caminho_banco)

    # --------------------------------------------------------
    # CICLO DE VIDA
    # --------------------------------------------------------

    @property
    def ativo(self):
        return self.httpd is not None

    @property
    def porta(self):
        if self.httpd is None:
            return None
        return self.httpd.server_address[1]

    def iniciar(self):
        if self.ativo:
            return self.info()

        banco = self.caminho_banco
        pasta_app = self.pasta_app
        host = self.host

        # Migrações aditivas e idempotentes do v9 (mesmas usadas pela 8766/desktop).
        ext.instalar(banco)
        fluxo.instalar(banco)
        cad.instalar(banco)
        catalogo.instalar(banco)
        aten.instalar(banco)
        prod.instalar(banco)
        cad.sincronizar_solicitacoes_pendentes(banco)

        class Handler(BaseHTTPRequestHandler):
            server_version = f'AUTOSEG-PortalCliente/{VERSAO}'

            def log_message(self, formato, *args):
                pass

            # ---------- respostas ----------
            def send_bytes(self, data, mime='text/html; charset=utf-8', filename=None,
                           status=200, cookie=None):
                self.send_response(status)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store, max-age=0')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('X-Frame-Options', 'DENY')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('X-AUTOSEG-Portal', VERSAO)
                self.send_header(
                    'Content-Security-Policy',
                    "default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; "
                    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'; img-src 'self' data:")
                if filename:
                    from urllib.parse import quote
                    self.send_header('Content-Disposition',
                                     "attachment; filename*=UTF-8''" + quote(Path(filename).name))
                if cookie:
                    self.send_header('Set-Cookie', cookie)
                self.end_headers()
                self.wfile.write(data)

            def responder(self, html_text, status=200, cookie=None):
                # O portal roda na raiz da 8765: remove apenas o prefixo interno /cliente.
                html_text = html_text.replace('href="/cliente/', 'href="/').replace('href="/cliente"', 'href="/"')
                html_text = html_text.replace('action="/cliente/', 'action="/').replace('action="/cliente"', 'action="/"')
                return self.send_bytes(html_text.encode('utf-8'), status=status, cookie=cookie)

            def redir(self, path, cookie=None):
                if not path.startswith('/') or path.startswith('//'):
                    path = '/'
                path = path.replace('/cliente', '') or '/'
                self.send_response(303)
                self.send_header('Location', path)
                self.send_header('Cache-Control', 'no-store')
                if cookie:
                    self.send_header('Set-Cookie', cookie)
                self.end_headers()

            def erro(self, mensagem, status=400):
                destino = '/'
                try:
                    ref = urlparse(self.headers.get('Referer', ''))
                    host = self.headers.get('Host', '').lower()
                    if (ref.scheme in ('http', 'https') and ref.netloc.lower() == host
                            and ref.path.startswith('/') and not ref.path.startswith('//')):
                        destino = ref.path + (('?' + ref.query) if ref.query else '')
                except (ValueError, TypeError):
                    pass
                return self.responder(
                    cliente.pagina_texto('Operação não concluída',
                                         '<p class="bad">' + html.escape(str(mensagem)) + '</p>'
                                         '<p><a href="' + html.escape(destino, quote=True)
                                         + '">Voltar à página anterior</a></p>'), status)

            # ---------- entrada ----------
            def form(self):
                try:
                    tamanho = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    raise ValueError('Tamanho inválido.')
                if not (0 < tamanho <= MAX_POST):
                    raise ValueError('Envio vazio ou acima de 10 MB.')
                tipo = self.headers.get('Content-Type', '')
                bruto = self.rfile.read(tamanho)
                if tipo.startswith('multipart/form-data'):
                    msg = BytesParser(policy=email_policy).parsebytes(
                        ('Content-Type: ' + tipo + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + bruto)
                    dados = {}
                    for parte in msg.iter_parts():
                        nome = parte.get_param('name', header='Content-Disposition')
                        if not nome:
                            continue
                        dados[nome] = (parte.get_payload(decode=True) or b'').decode('utf-8', 'replace')
                    return dados
                if tipo.startswith('application/x-www-form-urlencoded'):
                    texto = bruto.decode('utf-8', 'replace')
                    parsed = parse_qs(texto, keep_blank_values=True, max_num_fields=400)
                    return {k: v[0] for k, v in parsed.items()}
                raise ValueError('Formato de formulário não suportado.')

            # ---------- sessão histórica (ID + senha) ----------
            def _legado_sessao(self):
                try:
                    jar = SimpleCookie()
                    jar.load(self.headers.get('Cookie', ''))
                    token = jar['autosseg_legado'].value
                except (KeyError, ValueError):
                    return None
                with LOCK_LEGADO:
                    s = SESSOES_LEGADO.get(token)
                    if not s or s['exp'] < time.time():
                        SESSOES_LEGADO.pop(token, None)
                        return None
                return s

            def _legado_cookie(self, token, remover=False):
                seguro = ('Secure; ' if (self.headers.get('CF-Ray')
                                         or self.headers.get('X-Forwarded-Proto', '').lower() == 'https') else '')
                return f'autosseg_legado={token}; Path=/; HttpOnly; SameSite=Strict; {seguro}Max-Age={0 if remover else 28800}'

            def _legado_login(self, aviso=''):
                card, _, campos, _, _, esc, _, _ = cliente.u()
                corpo = ('<p>Área para clientes que já receberam <b>ID e senha</b> da AUTOSEG. '
                         'Se você tem conta por CPF e senha, use o login principal.</p>')
                if aviso:
                    corpo += '<p class="notice">' + esc(aviso) + '</p>'
                corpo += ('<form method="post" action="/legado/entrar">'
                          + campos('ID do cliente', 'cliente_id', required=True, kind='number')
                          + campos('Senha', 'senha', kind='password', required=True)
                          + '<button>Entrar no acesso antigo</button></form>')
                return self.responder(cliente.pagina_texto(
                    'Acesso antigo do cliente',
                    card('Login por ID e senha', corpo)
                    + '<p><a class="btn secondary" href="/">Ir para o login por CPF</a></p>'))

            def _legado_lista(self, s):
                card, _, _, _, _, esc, botao, tabela = cliente.u()
                with ext.db(banco) as c:
                    nome = c.execute('SELECT nome,tipo_pessoa FROM clientes WHERE id=?', (s['cid'],)).fetchone()
                    registros = c.execute(
                        '''SELECT o.id,o.numero_os,o.status,o.descricao FROM ordens_servico o
                           WHERE o.cliente_id=? ORDER BY o.id DESC LIMIT 250''', (s['cid'],)).fetchall()
                linhas = []
                for r in registros:
                    publicado = fluxo.ultimo_documento(banco, r['id']) if r['status'] in fluxo.FIM else None
                    numero_url = quote(str(r['numero_os'] or r['id']), safe='')
                    doc = (botao('Baixar relatório PDF', f'/legado/os/{numero_url}/pdf')
                           if publicado and nome and nome['tipo_pessoa']=='Física' else '<span class="muted">Relatório restrito ao titular PF ou síndico autorizado</span>')
                    linhas.append((esc(r['numero_os']), esc(r['descricao'] or '')[:160],
                                   '<span class="tag">' + esc(r['status']) + '</span>', doc))
                corpo = ('<p>Olá, <b>' + esc(nome['nome'] if nome else 'Cliente') + '</b>. '
                         'Este acesso histórico é somente leitura.</p>'
                         '<form method="post" action="/legado/sair">'
                         '<button class="secondary">Sair</button></form>')
                return self.responder(cliente.pagina_texto(
                    'Minhas OS — acesso antigo',
                    card('Minhas ordens de serviço', corpo)
                    + card('Ordens', tabela(['OS', 'Serviço', 'Situação', 'Relatório'], linhas))))

            def _legado_pdf(self, s, oid):
                with ext.db(banco) as c:
                    dono = c.execute('SELECT o.status,cl.tipo_pessoa FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id WHERE o.id=? AND o.cliente_id=?',
                                     (oid, s['cid'])).fetchone()
                if not dono:
                    return self.erro('Documento não pertence a este cadastro.', 404)
                if dono['tipo_pessoa']!='Física':
                    return self.erro('PDF de condomínio somente ao síndico autorizado pelo Portal Cliente.', 403)
                if dono['status'] not in fluxo.FIM:
                    return self.erro('O atendimento ainda não foi encerrado.', 409)
                info = fluxo.ultimo_documento(banco, oid)
                if not info:
                    return self.erro('Relatório ainda não publicado.', 409)
                arquivo = Path(fluxo.validar_pdf_publicado(info))
                return self.send_bytes(arquivo.read_bytes(), 'application/pdf', filename=arquivo.name)

            # ---------- roteamento ----------
            @staticmethod
            def _rel(path):
                if path in ('', '/'):
                    return '/cliente'
                if path.startswith('/cliente'):
                    return path
                return '/cliente' + path

            def do_GET(self):
                path = urlparse(self.path).path.rstrip('/') or '/'
                try:
                    if path == '/static/portal.js':
                        js = pasta_app / 'portal.js'
                        return self.send_bytes(js.read_bytes(), 'application/javascript; charset=utf-8') if js.is_file() else self.erro('Recurso não encontrado.', 404)
                    if path == '/static/cliente_whatsapp.js':
                        js = (pasta_app / 'web' / 'cliente_whatsapp.js')
                        return self.send_bytes(js.read_bytes(), 'application/javascript; charset=utf-8') if js.is_file() else self.erro('Recurso não encontrado.', 404)
                    if path == '/api/versao':
                        dados = json.dumps({
                            'app': 'Gestão de Serviços — AUTOSEG',
                            'site': 'portal do cliente',
                            'versao': VERSAO,
                            'porta': getattr(self.server, 'server_port', None),
                            'login_cliente': 'CPF e senha',
                        }).encode('utf-8')
                        return self.send_bytes(dados, 'application/json; charset=utf-8')
                    if path == '/api/health':
                        return self.send_bytes(json.dumps({'ok': True, 'portal': 'cliente'}).encode(),
                                               'application/json; charset=utf-8')
                    if path == '/api/info':
                        return self.send_bytes(json.dumps({'site': 'cliente', 'versao': VERSAO,
                                                           'porta': self.server.server_port}).encode(),
                                               'application/json; charset=utf-8')
                    if path == '/manifest.webmanifest':
                        return self.send_bytes(json.dumps({
                            'name': 'Portal do Cliente · Gestão de Serviços',
                            'short_name': 'Cliente',
                            'start_url': '/',
                            'display': 'standalone',
                            'background_color': '#0A0A0A',
                            'theme_color': '#FFD400',
                        }).encode(), 'application/manifest+json')
                    if path in ('/icone.png', '/favicon.ico', '/logo.png'):
                        if path == '/logo.png':
                            icone = pasta_app / 'logo.png'
                            if icone.is_file():
                                mime = mimetypes.guess_type(icone.name)[0] or 'image/png'
                                return self.send_bytes(icone.read_bytes(), mime)
                        else:
                            icone = ext.caminho_icone(pasta_app)
                            if icone:
                                mime = mimetypes.guess_type(icone.name)[0] or 'image/png'
                                return self.send_bytes(icone.read_bytes(), mime)
                        return self.erro('Imagem não encontrada.', 404)

                    # Acesso histórico (ID + senha), sem link na página principal.
                    if path == '/legado':
                        s = self._legado_sessao()
                        if not s:
                            return self._legado_login()
                        return self._legado_lista(s)
                    partes = path.strip('/').split('/')
                    if len(partes) == 4 and partes[0] == 'legado' and partes[1] == 'os' and partes[3] == 'pdf':
                        registro = ordens_repo.obter_por_token(banco, unquote(partes[2]))
                        if not registro:
                            return self.erro('OS não encontrada.', 404)
                        s = self._legado_sessao()
                        if not s:
                            return self._legado_login('Entre com ID e senha.')
                        return self._legado_pdf(s, int(registro['id']))

                    return cliente.get(self, self._rel(path), banco)
                except PermissionError as exc:
                    return self.erro(str(exc), 403)
                except ValueError as exc:
                    return self.erro(str(exc), 400)
                except sqlite3.OperationalError as exc:
                    LOG.exception('Falha SQLite em GET %s', path)
                    if 'locked' in str(exc).lower() or 'busy' in str(exc).lower():
                        return self.erro('O banco está ocupado por outra operação. Aguarde alguns segundos e tente novamente. Se persistir, reinicie os servidores AUTOSEG.', 503)
                    return self.erro('Falha de acesso aos dados. Consulte logs/portal_cliente.log.', 500)
                except Exception:
                    LOG.exception('Erro inesperado em GET %s', path)
                    return self.erro('Falha interna no portal do cliente. Consulte logs/portal_cliente.log.', 500)

            def do_POST(self):
                path = urlparse(self.path).path.rstrip('/') or '/'
                try:
                    d = self.form()
                    if path == '/legado/entrar':
                        ip = 'legado:' + self.client_address[0]
                        agora = time.time()
                        with LOCK_LEGADO:
                            falhas = [t for t in FALHAS_LEGADO.get(ip, []) if agora - t < 600]
                        if len(falhas) >= 10:
                            return self.erro('Muitas tentativas. Aguarde dez minutos.', 429)
                        r = fluxo.autenticar_cliente(banco, d.get('cliente_id'), str(d.get('senha', '')))
                        if not r:
                            with LOCK_LEGADO:
                                FALHAS_LEGADO[ip] = falhas + [agora]
                            return self._legado_login('ID ou senha incorretos.')
                        token = secrets.token_urlsafe(36)
                        with LOCK_LEGADO:
                            FALHAS_LEGADO.pop(ip, None)
                            SESSOES_LEGADO[token] = {'cid': r['id'], 'exp': time.time() + 28800}
                        return self.redir('/legado', self._legado_cookie(token))
                    if path == '/legado/sair':
                        jar = SimpleCookie()
                        jar.load(self.headers.get('Cookie', ''))
                        if 'autosseg_legado' in jar:
                            with LOCK_LEGADO:
                                SESSOES_LEGADO.pop(jar['autosseg_legado'].value, None)
                        return self.redir('/legado', self._legado_cookie('', True))

                    return cliente.post(self, self._rel(path), d, banco)
                except PermissionError as exc:
                    return self.erro(str(exc), 403)
                except (ValueError, KeyError, TypeError) as exc:
                    return self.erro(str(exc), 400)
                except sqlite3.OperationalError as exc:
                    LOG.exception('Falha SQLite em POST %s', path)
                    if 'locked' in str(exc).lower() or 'busy' in str(exc).lower():
                        return self.erro('O banco está ocupado por outra operação. Sua solicitação pode não ter sido salva; confira o painel antes de tentar novamente.', 503)
                    return self.erro('Falha de acesso ao banco ao salvar. Consulte logs/portal_cliente.log.', 500)
                except Exception:
                    LOG.exception('Erro inesperado em POST %s', path)
                    return self.erro('Falha interna ao salvar. Consulte logs/portal_cliente.log.', 500)

        try:
            httpd = _ServidorHTTP((host, self.porta_solicitada), Handler)
        except OSError as exc:
            self.erro = (f'A porta {self.porta_solicitada} está em uso. Feche o outro AUTOSEG '
                         f'ou o processo antigo antes de iniciar o portal do cliente.')
            raise RuntimeError(self.erro) from exc

        self.httpd = httpd
        self.thread = threading.Thread(target=httpd.serve_forever,
                                       name='portal-do-cliente', daemon=True)
        self.thread.start()
        self.iniciado_em = time.localtime()
        self.erro = None
        return self.info()

    def parar(self):
        httpd, thread = self.httpd, self.thread
        self.httpd = self.thread = None
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=3)

    def info(self):
        ip = obter_ip_local()
        return {
            'ativo': self.ativo,
            'porta': self.porta,
            'ip_local': ip,
            'url_local': f'http://127.0.0.1:{self.porta}' if self.ativo else '',
            'url_rede': f'http://{ip}:{self.porta}' if self.ativo else '',
            'iniciado_em': time.strftime('%d/%m/%Y %H:%M', self.iniciado_em) if self.iniciado_em else '',
            'erro': self.erro or '',
            'versao': VERSAO,
            'site': 'Portal do Cliente',
        }

    # Compatibilidade com o desktop (avisos de novas solicitações).
    def consumir_eventos(self):
        itens = []
        while True:
            try:
                itens.append(self.eventos.get_nowait())
            except queue.Empty:
                break
        return itens


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Portal do Cliente AUTOSEG (8765)')
    parser.add_argument('--porta', type=int, default=PORTA_PADRAO)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    srv = ServidorPortal(porta=args.porta, host=args.host)
    info = srv.iniciar()
    print('Portal do Cliente AUTOSEG', info['url_local'])
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        srv.parar()


if __name__ == '__main__':
    main()
