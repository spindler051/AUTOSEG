"""Application boundary shared by desktop, HTTP and future clients.

The contract is intentionally use-case oriented. Local and remote
implementations must expose the same operations so the GTK shell does not need
to know whether it is talking to SQLite or to a headless server.
"""
from officina.application.contracts import (
    AppError,
    AppService,
    Cliente,
    ClienteOpcao,
    ClienteResumo,
    ConflitoError,
    ChamadoPJ,
    Health,
    HistoricoOS,
    LancamentoFinanceiro,
    NaoEncontradoError,
    OrganizacaoPJ,
    OSInput,
    OSResultado,
    OSOpcao,
    OSResumo,
    PrestadorResumo,
    ResumoFinanceiro,
    ResumoHistorico,
    ResumoInicio,
    ResumoPortal,
    ServicoIndisponivelError,
    SindicoContato,
    SolicitacaoPortal,
    ValidacaoError,
    VinculoPJ,
)


__all__ = [
    'AppError',
    'AppService',
    'Cliente',
    'ClienteOpcao',
    'ClienteResumo',
    'ConflitoError',
    'ChamadoPJ',
    'Health',
    'HistoricoOS',
    'LancamentoFinanceiro',
    'NaoEncontradoError',
    'OrganizacaoPJ',
    'OSInput',
    'OSResultado',
    'OSOpcao',
    'OSResumo',
    'PrestadorResumo',
    'ResumoFinanceiro',
    'ResumoHistorico',
    'ResumoInicio',
    'ResumoPortal',
    'ServicoIndisponivelError',
    'SindicoContato',
    'SolicitacaoPortal',
    'ValidacaoError',
    'VinculoPJ',
]
