"""Current provider identity for server-projected actions and customer fields.

This read-side helper is not permission to mutate: writers must reauthorize
inside their own BEGIN IMMEDIATE using the returned current principal.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace

from officina.core import prestadores_ext as ext


def resolve(banco, principal, *, connection=None):
    if (principal is None or not principal.active
            or principal.organization_id != 'autoseg'
            or type(principal.provider_id) is not int
            or principal.provider_id <= 0):
        raise PermissionError('Sessão indisponível.')
    with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
        row = c.execute('SELECT ativo,excluido FROM prestadores WHERE id=?',
                        (principal.provider_id,)).fetchone()
        if row is None or not row['ativo'] or row['excluido']:
            raise PermissionError('Sessão indisponível.')
        role = 'admin' if ext.administrador(c, principal.provider_id) else 'employee'
    return replace(principal, role=role)
