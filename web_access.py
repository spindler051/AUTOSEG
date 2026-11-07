"""Owns the optional local web servers used by the desktop app.

The GTK shell must not import portal classes or know their lifecycle. It asks
this manager for status, URLs and events. In local-only mode no portal module
is imported and no port is opened.
"""
from __future__ import annotations

from pathlib import Path

import runtime_config


class WebAccessManager:
    """Start, stop and report the provider/client HTTP portals."""

    def __init__(self, banco, pasta_app=None, enabled: bool = True,
                 provider_factory=None, client_factory=None):
        self.banco = str(banco)
        self.pasta_app = Path(pasta_app or Path(__file__).resolve().parent)
        self.enabled = bool(enabled)
        self._provider_factory = provider_factory
        self._client_factory = client_factory
        self._provider = None
        self._client = None
        self._provider_url = ''
        self._provider_error = (
            'Modo local: apenas o banco local.' if not self.enabled else '')
        self._client_error = ''

    @property
    def provider_url(self) -> str:
        return self._provider_url

    @property
    def provider_error(self) -> str:
        return self._provider_error

    @property
    def client_error(self) -> str:
        return self._client_error

    @property
    def provider_active(self) -> bool:
        return bool(self._provider_url)

    def start(self) -> dict:
        """Start both portals when web access is enabled.

        A failure in one portal must not prevent the other from starting, which
        preserves the previous desktop startup behavior.
        """
        if not self.enabled:
            return self.status()
        try:
            self.start_provider()
        except Exception as erro:
            if not self._provider_error:
                self._provider_error = str(erro)
        try:
            self.start_client()
        except Exception as erro:
            if not self._client_error:
                self._client_error = str(erro)
        return self.status()

    def start_provider(self) -> str:
        if not self.enabled:
            raise RuntimeError('Servidor web desativado (modo local).')
        if self._provider is not None and self._provider_url:
            return self._provider_url
        config = runtime_config.provider_server()
        try:
            if self._provider_factory is not None:
                self._provider = self._provider_factory(
                    self.banco, config.host, config.port)
            else:
                from portal_prestador import PortalPrestador
                self._provider = PortalPrestador(
                    self.banco, host=config.host, porta=config.port)
            self._provider_url = str(self._provider.iniciar() or '')
            self._provider_error = ''
        except Exception as erro:
            self._provider_url = ''
            self._provider_error = str(erro)
            raise
        return self._provider_url

    def start_client(self) -> dict:
        if not self.enabled:
            raise RuntimeError('Servidor web desativado (modo local).')
        try:
            if self._client is None:
                self._criar_cliente()
            self._client.iniciar()
            self._client_error = ''
        except Exception as erro:
            self._client_error = str(erro)
            raise
        return self.client_info()

    def stop_client(self) -> None:
        if self._client is not None:
            try:
                self._client.parar()
            finally:
                self._client_error = ''

    def stop_provider(self) -> None:
        if self._provider is not None:
            try:
                self._provider.parar()
            finally:
                self._provider_url = ''

    def stop(self) -> None:
        self.stop_client()
        self.stop_provider()

    def client_info(self) -> dict:
        if self._client is None:
            return self._cliente_offline()
        try:
            info = dict(self._client.info())
        except Exception as erro:
            self._client_error = str(erro)
            return self._cliente_offline()
        if self._client_error and not info.get('erro'):
            info['erro'] = self._client_error
        return info

    def client_on_network(self) -> bool:
        if self._client is None or not self.client_info().get('ativo'):
            return False
        return getattr(self._client, 'host', '') in ('0.0.0.0', '::')

    def consume_events(self) -> list[dict]:
        if self._client is None:
            return []
        return list(self._client.consumir_eventos())

    def status(self) -> dict:
        return {
            'enabled': self.enabled,
            'provider': {
                'ativo': self.provider_active,
                'url': self._provider_url,
                'erro': self._provider_error,
            },
            'client': self.client_info(),
        }

    def _criar_cliente(self) -> None:
        config = runtime_config.client_server()
        if self._client_factory is not None:
            self._client = self._client_factory(
                self.banco, self.pasta_app, config.host, config.port)
            return
        from servidor_web import ServidorPortal
        self._client = ServidorPortal(
            self.banco, self.pasta_app, porta=config.port, host=config.host)

    def _cliente_offline(self) -> dict:
        erro = self._client_error
        if not self.enabled:
            erro = 'Modo local: apenas o banco local.'
        return {
            'ativo': False,
            'porta': None,
            'ip_local': '',
            'url_local': '',
            'url_rede': '',
            'iniciado_em': '',
            'erro': erro,
            'versao': '',
            'site': 'Portal do Cliente',
        }
