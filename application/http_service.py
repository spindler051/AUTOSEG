"""HTTP implementation of the application contract.

Only health is exposed today. Client operations fail with a stable unavailable
error instead of silently opening a local database, which keeps the boundary
honest until the server API grows in the next slice.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Mapping

from application.contracts import (
    AppService,
    Cliente,
    ClienteResumo,
    Health,
    ResumoInicio,
    ServicoIndisponivelError,
)
from versao_app import versao_local


class HttpService(AppService):
    """Thin JSON client for a headless AUTOSEG server."""

    mode = 'remote'

    def __init__(self, base_url: str, token: str = '', timeout: float = 10.0):
        self.base_url = str(base_url or '').rstrip('/')
        self.token = str(token or '')
        self.timeout = float(timeout)

    def health(self) -> Health:
        try:
            dados = self._get('/api/v1/health')
        except ServicoIndisponivelError as erro:
            return Health(
                status='unavailable',
                version=versao_local(),
                mode=self.mode,
                database='',
                capabilities=self._capabilities(),
                detail=str(erro),
            )
        info = dados.get('data') if isinstance(dados, dict) else {}
        return Health(
            status=str(info.get('status') or 'ok'),
            version=str(info.get('version') or versao_local()),
            mode=self.mode,
            database='',
            capabilities=self._capabilities(),
        )

    def resumo_inicio(self) -> ResumoInicio:
        raise self._not_available('resumo do início')

    def listar_clientes(self, termo: str = '') -> list[ClienteResumo]:
        raise self._not_available('lista de clientes')

    def obter_cliente(self, cliente_id: int) -> Cliente | None:
        raise self._not_available('consulta de cliente')

    def salvar_cliente(
        self, cliente_id: int | None, dados: Mapping[str, Any]
    ) -> Cliente:
        raise self._not_available('gravação de cliente')

    def _get(self, caminho: str) -> dict:
        if not self.base_url:
            raise ServicoIndisponivelError('URL do servidor não configurada.')
        pedido = urllib.request.Request(self.base_url + caminho, method='GET')
        pedido.add_header('Accept', 'application/json')
        if self.token:
            pedido.add_header('Authorization', 'Bearer ' + self.token)
        try:
            with urllib.request.urlopen(pedido, timeout=self.timeout) as resposta:
                bruto = resposta.read().decode('utf-8')
        except urllib.error.HTTPError as erro:
            raise ServicoIndisponivelError(
                f'Servidor respondeu HTTP {erro.code}.') from erro
        except (urllib.error.URLError, OSError) as erro:
            raise ServicoIndisponivelError(
                f'Servidor indisponível: {erro}') from erro
        try:
            dados = json.loads(bruto)
        except ValueError as erro:
            raise ServicoIndisponivelError(
                'Servidor respondeu um JSON inválido.') from erro
        if not isinstance(dados, dict):
            raise ServicoIndisponivelError('Resposta do servidor inválida.')
        return dados

    @staticmethod
    def _not_available(recurso: str) -> ServicoIndisponivelError:
        return ServicoIndisponivelError(
            f'A API remota de {recurso} ainda não está disponível.',
            'Servidor remoto')

    @staticmethod
    def _capabilities() -> tuple[str, ...]:
        return ('health',)
