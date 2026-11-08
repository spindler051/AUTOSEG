#!/usr/bin/env python3
"""Backend HTTP headless do AUTOSEG/Officina.

Modos:
  python servidor_backend.py --api   # servidor: somente /api/v1, sem HTML
  python servidor_backend.py --site  # GUI do site (Officina Web)
  python servidor_backend.py --web   # alias antigo de --site

O processo não depende do app GTK e não depende de Cloudflare. Túneis são uma
comodidade separada; o servidor pode rodar em localhost, LAN ou atrás de um
proxy reverso com domínio próprio.

Variáveis:
  GESTAO_BANCO / AUTOSEG_BASE   banco e pastas de dados
  CLIENTE_PORT / CLIENTE_BIND   portal do cliente (modo --web)
  PRESTADOR_PORT / PRESTADOR_BIND
  AUTOSEG_DEV=1                 portas 8865/8866 por padrão
"""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
if __package__ in (None, ''):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[3]))

import argparse
import signal
import time
from pathlib import Path

from officina.core.banco import BANCO, criar_banco
from officina.core import runtime_config
from officina.core import prestadores_ext as ext
from officina.core import fluxo_os as fluxo
from officina.core import atendimento_os as aten
from officina.core import cadastros_v9 as cad9
from officina.core import estoque_materiais as estoque
from officina.core import catalogo_servicos as catalogo
from officina.core import composicao
from officina.core import empresa_financeiro as empresa
from officina.core import produtividade_os as prod
PASTA_APP = runtime_config.base_dir()


def _instalar_base():
    criar_banco()
    ext.instalar(BANCO)
    fluxo.instalar(BANCO)
    aten.instalar(BANCO)
    cad9.instalar(BANCO)
    estoque.instalar(BANCO)
    catalogo.instalar(BANCO)
    empresa.instalar(BANCO)
    composicao.instalar()
    composicao.instalar_banco(BANCO)
    prod.instalar(BANCO)


def _esperar():
    parar = False

    def encerrar(*_args):
        nonlocal parar
        parar = True

    signal.signal(signal.SIGINT, encerrar)
    signal.signal(signal.SIGTERM, encerrar)
    while not parar:
        time.sleep(0.5)


def run_site():
    from flavors.autoseg.modules.servidor_web import ServidorPortal
    from flavors.autoseg.modules.portal_prestador import PortalPrestador

    _instalar_base()
    cliente_cfg = runtime_config.client_server()
    prestador_cfg = runtime_config.provider_server()
    cliente = ServidorPortal(
        BANCO, PASTA_APP,
        porta=cliente_cfg.port,
        host=cliente_cfg.host)
    prestador = PortalPrestador(
        BANCO,
        host=prestador_cfg.host,
        porta=prestador_cfg.port)
    try:
        cliente.iniciar()
        prestador.iniciar()
        info = cliente.info()
        print("Officina Web — GUI do site")
        print("Banco:", BANCO)
        host_prestador = ("127.0.0.1" if prestador.host in ("0.0.0.0", "::")
                          else prestador.host)
        print("Cliente:", info.get("url_local"))
        print("Prestador:", f"http://{host_prestador}:{prestador.porta}")
        print("API embutida no mesmo processo (temporário):",
              f"http://{host_prestador}:{prestador.porta}/api/v1")
        print("Para servidor separado, use --api.")
        print("Cloudflare: opcional, iniciado separadamente.")
        print("Ctrl+C para encerrar.")
        _esperar()
    finally:
        try:
            prestador.parar()
        except Exception:
            pass
        try:
            cliente.parar()
        except Exception:
            pass


def run_api(host='127.0.0.1', port=None):
    from flavors.autoseg.modules.api_server import start, url

    _instalar_base()
    if port is None:
        port = runtime_config.provider_server().port
    server = start(BANCO, host, port)
    print("Officina API headless")
    print("Banco:", BANCO)
    print("API:", url(server))
    print("Sem HTML, sem GTK e sem Cloudflare.")
    print("Ctrl+C para encerrar.")
    try:
        _esperar()
    finally:
        server.shutdown()
        server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Backend headless do AUTOSEG/Officina.')
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument('--site', '--web', dest='site', action='store_true',
                      help='GUI do site (Officina Web); --web é alias antigo')
    modo.add_argument('--api', action='store_true',
                      help='servidor: somente /api/v1, sem HTML')
    parser.add_argument('--host', default='127.0.0.1',
                        help='bind do modo --api (padrão: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=None,
                        help='porta do modo --api (padrão: porta do prestador)')
    args = parser.parse_args(argv)
    if args.api:
        run_api(args.host, args.port)
    else:
        run_site()


if __name__ == '__main__':
    main()
