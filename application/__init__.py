"""Application boundary shared by desktop, HTTP and future clients.

The contract is intentionally use-case oriented. Local and remote
implementations must expose the same operations so the GTK shell does not need
to know whether it is talking to SQLite or to a headless server.
"""
from application.contracts import (
    AppError,
    AppService,
    Cliente,
    ClienteResumo,
    ConflitoError,
    Health,
    LancamentoFinanceiro,
    NaoEncontradoError,
    OSResumo,
    ResumoFinanceiro,
    ResumoInicio,
    ResumoPortal,
    ServicoIndisponivelError,
    SolicitacaoPortal,
    ValidacaoError,
)


__all__ = [
    'AppError',
    'AppService',
    'Cliente',
    'ClienteResumo',
    'ConflitoError',
    'Health',
    'LancamentoFinanceiro',
    'NaoEncontradoError',
    'OSResumo',
    'ResumoFinanceiro',
    'ResumoInicio',
    'ResumoPortal',
    'ServicoIndisponivelError',
    'SolicitacaoPortal',
    'ValidacaoError',
]
