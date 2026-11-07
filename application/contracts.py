"""Application contract and transport-neutral DTOs.

The desktop shell should depend on this module, not on SQLite rows or portal
classes. Money fields keep the current float representation for compatibility;
a later slice can move them to integer cents without changing the UI contract
at the same time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class Health:
    """Small readiness payload shared by local and remote transports."""

    status: str
    version: str
    mode: str
    database: str = ''
    capabilities: Sequence[str] = field(default_factory=tuple)
    detail: str = ''


@dataclass(frozen=True)
class ClienteResumo:
    """Client row used by list screens."""

    id: int
    nome: str
    documento: str
    cidade: str
    telefone: str
    status: str
    incompleto: bool


@dataclass(frozen=True)
class Cliente:
    """Client record used by the edit dialog."""

    id: int
    versao: int
    campos: Mapping[str, Any]
    incompleto: bool


@dataclass(frozen=True)
class ResumoPortal:
    """Counts for requests created by the client portal."""

    total: int
    andamento: int
    concluidas: int


@dataclass(frozen=True)
class SolicitacaoPortal:
    """Read-only row for the portal request list in the desktop app."""

    id: int
    numero_os: str
    cliente: str
    data_abertura: str
    urgencia: str
    status: str


@dataclass(frozen=True)
class ResumoInicio:
    """Dashboard numbers that used to be queried directly by the GTK shell."""

    clientes_ativos: int
    os_abertas: int
    os_iniciadas: int
    os_pendentes: int
    financeiro_recebido: float
    financeiro_a_receber: float


class AppError(Exception):
    """Stable application error consumed by every client."""

    codigo = 'erro'

    def __init__(self, mensagem: str, titulo: str | None = None):
        super().__init__(mensagem)
        self.mensagem = str(mensagem)
        self.titulo = titulo or 'Operação não concluída'


class ValidacaoError(AppError):
    codigo = 'validacao'


class NaoEncontradoError(AppError):
    codigo = 'nao_encontrado'


class ConflitoError(AppError):
    codigo = 'conflito'


class ServicoIndisponivelError(AppError):
    codigo = 'indisponivel'


class AppService(Protocol):
    """Use cases available to every client.

    Implementations must not leak ``sqlite3.Row``, portal objects or HTTP
    response objects through this boundary.
    """

    def health(self) -> Health:
        ...

    def resumo_inicio(self) -> ResumoInicio:
        ...

    def resumo_portal(self) -> ResumoPortal:
        ...

    def listar_solicitacoes_portal(
        self, limite: int = 50
    ) -> list[SolicitacaoPortal]:
        ...

    def listar_clientes(self, termo: str = '') -> list[ClienteResumo]:
        ...

    def obter_cliente(self, cliente_id: int) -> Cliente | None:
        ...

    def salvar_cliente(
        self, cliente_id: int | None, dados: Mapping[str, Any]
    ) -> Cliente:
        ...
