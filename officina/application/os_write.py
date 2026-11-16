"""Compatibility entry point for OSInput; no service-order SQL.

The same application service writes for Web, GTK and Desktop API. The legacy
function name is kept for the AppService contract and older callers.
"""
from __future__ import annotations

from officina.application.contracts import OSInput, OSResultado
from officina.application.os_write_service import OSCommand, salvar


def salvar_os(banco, dados: OSInput, *, authorize=None, principal=None) -> OSResultado:
    if principal is None or type(principal.provider_id) is not int:
        raise PermissionError('Identidade obrigatória para alterar OS.')
    command = OSCommand.from_desktop(dados, principal.provider_id)
    result = salvar(banco, command, principal, authorize=authorize)
    return OSResultado(result.os_id, result.criada, result.encerrada,
                       result.status_anterior, result.dados_incompletos)
