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
class OSInput:
    """Values already validated by the desktop form."""

    os_id: int | None
    cliente_id: int
    tecnico: str
    descricao: str
    valor_mao_obra: float
    valor_materiais: float
    custo_materiais: float
    valor_total: float
    forma_pagamento: str
    urgencia: str
    observacoes: str
    texto_adicional: str
    dados_incompletos: int
    tempo_horas: float
    composicao_json: str
    base_percentuais: str
    materiais: tuple[Mapping[str, Any], ...]
    acao: str
    relato: str
    motivo: str
    imagens: tuple[tuple[str, bytes], ...] = ()


@dataclass(frozen=True)
class OSResultado:
    os_id: int
    criada: bool
    encerrada: bool
    status_anterior: str
    dados_incompletos: int


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
class ClienteOpcao:
    """Client id/name option used by YAML import and pickers."""

    id: int
    nome: str


@dataclass(frozen=True)
class Cliente:
    """Client record used by the edit dialog."""

    id: int
    versao: int
    campos: Mapping[str, Any]
    incompleto: bool


@dataclass(frozen=True)
class OSResumo:
    """Active service-order row used by the desktop list."""

    id: int
    numero_os: str
    cliente: str
    data_abertura: str
    valor_total: float
    forma_pagamento: str
    origem: str
    responsavel: str
    status: str
    incompleto: bool


@dataclass(frozen=True)
class OSOpcao:
    """Minimal service-order option used by pickers."""

    id: int
    numero_os: str
    status: str
    cliente: str = ''


@dataclass(frozen=True)
class PrestadorResumo:
    id: int
    nome: str
    documento: str
    email: str
    especialidade: str
    ativo: bool


@dataclass(frozen=True)
class SindicoContato:
    nome: str
    telefone: str


@dataclass(frozen=True)
class HistoricoOS:
    """Finished service-order row used by the history screen."""

    id: int
    numero_os: str
    cliente: str
    data_conclusao: str
    valor_total: float
    forma_pagamento: str
    status: str
    pdf_disponivel: bool


@dataclass(frozen=True)
class ResumoHistorico:
    total: int
    abertas: int
    iniciadas: int
    pendentes: int
    concluidas: int
    valor_concluido: float
    valor_aberto: float


@dataclass(frozen=True)
class ChamadoPJ:
    id: int
    os_id: int | None
    organizacao: str
    solicitante: str
    status: str
    descricao: str


@dataclass(frozen=True)
class OrganizacaoPJ:
    id: int
    nome: str
    tipo: str
    situacao: str
    cliente_id: int | None


@dataclass(frozen=True)
class VinculoPJ:
    id: int
    organizacao: str
    pessoa: str
    papel: str


@dataclass(frozen=True)
class ResumoFinanceiro:
    """Totals for the finance cards."""

    a_receber: float
    recebido: float


@dataclass(frozen=True)
class LancamentoFinanceiro:
    """One finance row used by the desktop table."""

    id: int
    numero_os: str
    cliente: str
    valor: float
    forma_pagamento: str
    status: str
    vencimento: str


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

    def listar_os_ativas(self, termo: str = '') -> list[OSResumo]:
        ...

    def listar_os_para_escolha(self, limite: int = 250) -> list[OSOpcao]:
        ...

    def listar_os_para_atribuicao(self) -> list[OSOpcao]:
        ...

    def contar_os_cliente(self, cliente_id: int) -> int:
        ...

    def contar_clientes_ativos(self) -> int:
        ...

    def listar_prestadores(self) -> list[PrestadorResumo]:
        ...

    def alternar_prestador(self, prestador_id: int) -> None:
        ...

    def arquivar_prestador(self, prestador_id: int) -> None:
        ...

    def obter_contato_sindico(self, organizacao_id: int) -> SindicoContato:
        ...

    def listar_historico(self, termo: str = '') -> list[HistoricoOS]:
        ...

    def resumo_historico(self) -> ResumoHistorico:
        ...

    def painel_pj(self) -> tuple[list[ChamadoPJ], list[OrganizacaoPJ],
                                 list[VinculoPJ]]:
        ...

    def resumo_financeiro(self) -> ResumoFinanceiro:
        ...

    def listar_financeiro(
        self, termo: str = ''
    ) -> list[LancamentoFinanceiro]:
        ...

    def marcar_recebido(self, lancamento_id: int) -> None:
        ...

    def obter_cliente_ativo(self, cliente_id: int) -> ClienteOpcao | None:
        ...

    def obter_cliente_ativo_por_documento(
        self, documento: str
    ) -> ClienteOpcao | None:
        ...

    def listar_clientes(self, termo: str = '') -> list[ClienteResumo]:
        ...

    def obter_cliente(self, cliente_id: int) -> Cliente | None:
        ...

    def salvar_cliente(
        self, cliente_id: int | None, dados: Mapping[str, Any]
    ) -> Cliente:
        ...

    def desativar_cliente(self, cliente_id: int, motivo: str = '') -> None:
        ...

    def excluir_cliente(self, cliente_id: int) -> None:
        ...

    def definir_senha_cliente(self, cliente_id: int,
                              senha: str | None = None) -> str:
        ...

    def atribuir_os(self, os_id: int, prestador_id: int) -> bool:
        ...

    def desatribuir_os(self, os_id: int) -> bool:
        ...

    def iniciar_os(self, os_id: int) -> None:
        ...

    def atribuir_responsavel(self, organizacao_id: int, usuario_id: int) -> str:
        ...

    def remover_responsavel(self, organizacao_id: int) -> None:
        ...

    def criar_prestador(self, dados: Mapping[str, Any]) -> int:
        ...

    def redefinir_senha_prestador(self, prestador_id: int, senha: str) -> None:
        ...

    def obter_config_prestador(self, prestador_id: int) -> dict:
        ...

    def salvar_config_prestador(self, prestador_id: int,
                                dados: Mapping[str, Any]) -> None:
        ...

    def definir_documento_prestador(self, prestador_id: int,
                                    documento: str) -> str:
        ...

    def publicar_pdf(self, os_id: int) -> str:
        ...

    def preparar_email(self, os_id: int) -> str:
        ...

    def preparar_nota(self, os_id: int) -> str:
        ...

    def pdf_publicado(self, os_id: int) -> str:
        ...

    def url_whatsapp_chamado(self, chamado_id: int,
                             link_publico: str = '') -> dict:
        ...

    def analisar_chamado(self, chamado_id: int, decisao: str,
                         observacao: str = '') -> None:
        ...

    def confirmar_chamado(self, chamado_id: int, confirmacao: str) -> None:
        ...

    def gerar_os_chamado(self, chamado_id: int) -> int:
        ...

    def validar_organizacao(self, organizacao_id: int,
                            cliente_id: int) -> None:
        ...

    def atualizar_sindico(self, organizacao_id: int, nome: str,
                          telefone: str) -> None:
        ...

    def mesclar_organizacoes(self, origem: int, destino: int) -> None:
        ...

    def alterar_vinculo(self, vinculo_id: int, aprovar: bool) -> None:
        ...

    def salvar_os(self, dados: OSInput) -> OSResultado:
        ...

    def contexto_os(self, os_id: int | None = None) -> dict:
        ...

    def contar_anexos_os(self, os_id: int) -> int:
        ...

    def contexto_atribuicao(self, os_id: int) -> dict:
        ...

    def documento_prestador(self, prestador_id: int) -> str:
        ...

    def contexto_responsavel(self) -> dict:
        ...

    def contexto_os_rapida(self) -> dict:
        ...

    def contexto_movimento_empresa(self) -> dict:
        ...
