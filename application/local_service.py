"""In-process application service backed by the existing SQLite modules.

This is the first migration slice: clients, dashboard and portal summary
reads. The adapter keeps current queries, validation and last-write-wins
behavior untouched while giving the GTK shell a transport-neutral contract.
"""
from __future__ import annotations

from typing import Any, Mapping

import completude
import prestadores_ext as ext
from banco import BANCO
from integracao import clientes as clientes_core
from repositorios import ordens as ordens_repo
from versao_app import versao_local
from workaholic.domain.errors import ConflictError as WorkaholicConflictError
from workaholic.domain.errors import NotFoundError as WorkaholicNotFoundError

from application.contracts import (
    Cliente,
    ClienteResumo,
    ConflitoError,
    Health,
    NaoEncontradoError,
    ResumoInicio,
    ResumoPortal,
    SolicitacaoPortal,
    ValidacaoError,
)


class LocalService:
    """Application service that runs in the desktop process, without HTTP."""

    mode = 'local'

    def __init__(self, banco=None):
        self.banco = str(banco or BANCO)

    def health(self) -> Health:
        try:
            with ext.db(self.banco) as conexao:
                conexao.execute('SELECT 1').fetchone()
        except Exception as erro:
            return Health(
                status='degraded',
                version=versao_local(),
                mode=self.mode,
                database=self.banco,
                capabilities=self._capabilities(),
                detail=str(erro),
            )
        return Health(
            status='ok',
            version=versao_local(),
            mode=self.mode,
            database=self.banco,
            capabilities=self._capabilities(),
        )

    def resumo_inicio(self) -> ResumoInicio:
        clientes = clientes_core.contar_ativos(self.banco)
        os_resumo = ordens_repo.resumo(self.banco)
        financeiro = ordens_repo.financeiro_resumo(self.banco)
        return ResumoInicio(
            clientes_ativos=int(clientes),
            os_abertas=os_resumo['abertas'],
            os_iniciadas=os_resumo['iniciadas'],
            os_pendentes=os_resumo['pendentes'],
            financeiro_recebido=financeiro['recebido'],
            financeiro_a_receber=financeiro['a_receber'],
        )

    def resumo_portal(self) -> ResumoPortal:
        dados = ordens_repo.resumo_portal(self.banco)
        return ResumoPortal(
            total=dados['total'],
            andamento=dados['andamento'],
            concluidas=dados['concluidas'],
        )

    def listar_solicitacoes_portal(
        self, limite: int = 50
    ) -> list[SolicitacaoPortal]:
        return [
            SolicitacaoPortal(
                id=int(linha['id']),
                numero_os=str(linha.get('numero_os') or ''),
                cliente=str(linha.get('cliente') or ''),
                data_abertura=str(linha.get('data_abertura') or ''),
                urgencia=str(linha.get('urgencia') or 'Normal'),
                status=str(linha.get('status') or ''),
            )
            for linha in ordens_repo.listar_solicitacoes_portal(
                self.banco, limite=limite)
        ]

    def listar_clientes(self, termo: str = '') -> list[ClienteResumo]:
        return [self._resumo(registro)
                for registro in clientes_core.listar(termo, banco=self.banco)]

    def obter_cliente(self, cliente_id: int) -> Cliente | None:
        registro = clientes_core.obter(cliente_id, banco=self.banco)
        if registro is None:
            return None
        return self._cliente(registro)

    def salvar_cliente(
        self, cliente_id: int | None, dados: Mapping[str, Any]
    ) -> Cliente:
        try:
            registro = clientes_core.salvar(
                cliente_id, dict(dados), banco=self.banco)
        except clientes_core.ErroCliente as erro:
            raise ValidacaoError(str(erro), erro.titulo) from erro
        except WorkaholicConflictError as erro:
            raise ConflitoError(
                str(erro), 'Cadastro alterado por outra sessão') from erro
        except WorkaholicNotFoundError as erro:
            raise NaoEncontradoError(str(erro), 'Cliente não encontrado') from erro
        except ValueError as erro:
            raise ValidacaoError(str(erro)) from erro
        return self._cliente(registro)

    @staticmethod
    def _capabilities() -> tuple[str, ...]:
        return ('health', 'resumo_inicio', 'resumo_portal',
                'solicitacoes_portal', 'clientes.listar',
                'clientes.obter', 'clientes.salvar')

    @staticmethod
    def _resumo(registro) -> ClienteResumo:
        campos = dict(registro.get('fields') or {})
        return ClienteResumo(
            id=int(registro.get('id') or 0),
            nome=str(campos.get('nome') or ''),
            documento=str(campos.get('documento') or ''),
            cidade=str(campos.get('cidade') or ''),
            telefone=str(campos.get('telefone') or ''),
            status=str(campos.get('status') or ''),
            incompleto=completude.cliente_faltantes(campos),
        )

    @staticmethod
    def _cliente(registro) -> Cliente:
        campos = dict(registro.get('fields') or {})
        return Cliente(
            id=int(registro.get('id') or 0),
            versao=int(registro.get('version') or 1),
            campos=campos,
            incompleto=completude.cliente_faltantes(campos),
        )
