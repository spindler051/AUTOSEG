"""Owns the single optional Officina Web origin used by the desktop app.

The GTK shell must not import portal classes or know their lifecycle. It asks
this manager for status, URLs and events. In local-only mode no portal module
is imported and no port is opened.
"""
from __future__ import annotations

from pathlib import Path

from officina.core import runtime_config
class WebAccessManager:
    """Manage one provider HTTP server for both account contexts."""

    def __init__(self, banco, pasta_app=None, enabled: bool = True,
                 provider_factory=None):
        self.banco = str(banco)
        self.pasta_app = Path(pasta_app or Path(__file__).resolve().parent)
        self.enabled = bool(enabled)
        self._provider_factory = provider_factory
        self._provider = None
        self._provider_url = ''
        self._provider_error = (
            'Modo local: apenas o banco local.' if not self.enabled else '')

    @property
    def provider_url(self) -> str:
        return self._provider_url

    @property
    def provider_error(self) -> str:
        return self._provider_error

    @property
    def provider_active(self) -> bool:
        return bool(self._provider_url)

    def start(self) -> dict:
        """Start only the shared site; client requests use the same origin."""
        if not self.enabled:
            return self.status()
        try:
            self.start_provider()
        except Exception as error:
            self._provider_error = str(error)
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
                from flavors.autoseg.modules.portal_prestador import PortalPrestador
                self._provider = PortalPrestador(
                    self.banco, host=config.host, porta=config.port)
            self._provider_url = str(self._provider.iniciar() or '')
            self._provider_error = ''
        except Exception as erro:
            self._provider_url = ''
            self._provider_error = str(erro)
            raise
        return self._provider_url

    def stop_provider(self) -> None:
        if self._provider is not None:
            try:
                self._provider.parar()
            finally:
                self._provider_url = ''

    def stop(self) -> None:
        self.stop_provider()

    def site_info(self) -> dict:
        return {
            'ativo': self.provider_active, 'porta': self._provider.porta if self._provider and self.provider_active else None,
            'ip_local': '', 'url_local': self._provider_url,
            'url_rede': self._provider_url, 'iniciado_em': '',
            'erro': self._provider_error, 'versao': '', 'site': 'Officina Web',
        }

    def site_on_network(self) -> bool:
        return bool(self._provider and self.provider_active
                    and getattr(self._provider, 'host', '') in ('0.0.0.0','::'))

    def consume_events(self) -> list[dict]:
        return []

    def status(self) -> dict:
        return {
            'enabled': self.enabled,
            'site': self.site_info(),
        }
