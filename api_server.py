"""Headless JSON API server for a data-only Officina server.

This process serves only ``/api/v1``. It does not import the HTML portals, does
not open the client/provider sites and has no Cloudflare dependency. The GTK
desktop uses this process in server mode.
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import api_desktop
import api_financeiro as api_financeiro
from versao_app import versao_local

LOG = logging.getLogger('autoseg.api_server')


class _APIHandler(BaseHTTPRequestHandler):
    server_version = 'Officina-API/1'

    def log_message(self, formato, *args):
        LOG.info('%s %s', self.address_string(), formato % args)

    def do_OPTIONS(self):
        self._encaminhar('OPTIONS')

    def do_GET(self):
        self._encaminhar('GET')

    def do_POST(self):
        self._encaminhar('POST')

    def do_PUT(self):
        self._encaminhar('PUT')

    def do_DELETE(self):
        self._encaminhar('DELETE')

    def _encaminhar(self, metodo):
        caminho = urlparse(self.path).path
        if api_desktop.handle(self, caminho, self.server.banco, metodo):
            return
        if caminho == api_financeiro.API_PREFIX or caminho.startswith(
                api_financeiro.API_PREFIX + '/'):
            api_financeiro.handle(self, caminho, self.server.banco, metodo)
            return
        self._json(404, {
            'error': {'code': 'not_found', 'message': 'Rota não encontrada.'},
            'server': 'officina-api',
        })

    def _metodo_nao_permitido(self):
        self._json(405, {
            'error': {'code': 'method_not_allowed',
                      'message': 'A API é somente leitura.'},
        })

    def _json(self, status, payload):
        corpo = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(corpo)))
        self.send_header('Cache-Control', 'no-store, max-age=0')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-AUTOSEG-API-Version', 'v1')
        self.end_headers()
        self.wfile.write(corpo)


class _APIServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, endereco, handler, banco):
        self.banco = banco
        super().__init__(endereco, handler)


def start(banco, host='127.0.0.1', port=8766):
    """Create and start the API server; returns the server object."""
    api_financeiro.instalar(banco)
    server = _APIServer((host, int(port)), _APIHandler, banco)
    import threading
    thread = threading.Thread(target=server.serve_forever,
                              name='officina-api', daemon=True)
    thread.start()
    server.thread = thread
    return server


def url(server) -> str:
    host, porta = server.server_address[:2]
    host = '127.0.0.1' if host in ('0.0.0.0', '::') else host
    return f'http://{host}:{porta}/api/v1'


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Officina API headless (somente /api/v1, sem HTML).')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--banco', default=None)
    args = parser.parse_args(argv)

    from banco import BANCO, criar_banco
    import atendimento_os as aten
    import cadastros_v9 as cad9
    import catalogo_servicos as catalogo
    import composicao
    import empresa_financeiro as empresa
    import estoque_materiais as estoque
    import fluxo_os as fluxo
    import prestadores_ext as ext
    import produtividade_os as prod
    banco = args.banco or BANCO
    criar_banco(banco)
    ext.instalar(banco)
    fluxo.instalar(banco)
    aten.instalar(banco)
    cad9.instalar(banco)
    estoque.instalar(banco)
    catalogo.instalar(banco)
    empresa.instalar(banco)
    composicao.instalar()
    composicao.instalar_banco(banco)
    prod.instalar(banco)
    api_financeiro.instalar(banco)

    server = start(banco, args.host, args.port)
    parar = False

    def encerrar(*_args):
        nonlocal parar
        parar = True

    signal.signal(signal.SIGINT, encerrar)
    signal.signal(signal.SIGTERM, encerrar)
    print('Officina API headless', versao_local())
    print('Banco:', banco)
    print('API:', url(server))
    print('Ctrl+C para encerrar.')
    try:
        while not parar:
            time.sleep(0.5)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
