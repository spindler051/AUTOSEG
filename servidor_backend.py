#!/usr/bin/env python3
"""Backend HTTP headless do AUTOSEG.

Sobe somente os portais do cliente e do prestador, sem interface gráfica. Útil para
deixar o banco no macOS e acessar os portais do Linux via túnel SSH.

Variáveis:
  GESTAO_BANCO / AUTOSEG_BASE   banco e pastas de dados
  CLIENTE_PORT / CLIENTE_BIND   portal do cliente
  PRESTADOR_PORT / PRESTADOR_BIND
  AUTOSEG_DEV=1                 portas 8865/8866 por padrão
"""
import signal
import time
from pathlib import Path

from banco import BANCO, criar_banco
from servidor_web import ServidorPortal
import runtime_config
from portal_prestador import PortalPrestador
import prestadores_ext as ext
import fluxo_os as fluxo
import atendimento_os as aten
import cadastros_v9 as cad9
import estoque_materiais as estoque
import catalogo_servicos as catalogo

PASTA_APP = Path(__file__).resolve().parent


def main():
    criar_banco()
    ext.instalar(BANCO)
    fluxo.instalar(BANCO)
    aten.instalar(BANCO)
    cad9.instalar(BANCO)
    estoque.instalar(BANCO)
    catalogo.instalar(BANCO)

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

    parar = False

    def encerrar(*_args):
        nonlocal parar
        parar = True

    signal.signal(signal.SIGINT, encerrar)
    signal.signal(signal.SIGTERM, encerrar)

    try:
        cliente.iniciar()
        prestador.iniciar()
        info = cliente.info()
        print("AUTOSEG backend headless")
        print("Banco:", BANCO)
        host_prestador = ("127.0.0.1" if prestador.host in ("0.0.0.0", "::")
                          else prestador.host)
        print("Cliente:", info.get("url_local"))
        print("Prestador:", f"http://{host_prestador}:{prestador.porta}")
        print("Ctrl+C para encerrar.")
        while not parar:
            time.sleep(0.5)
    finally:
        try:
            prestador.parar()
        except Exception:
            pass
        try:
            cliente.parar()
        except Exception:
            pass


if __name__ == "__main__":
    main()
