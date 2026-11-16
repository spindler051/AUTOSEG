"""Transport-neutral service-order command boundary.

``portal_negocios.os_salvar`` is the only SQL writer for headers, materials,
composition, stock, report drafts and domain closing. Neither a GTK widget
nor an HTTP request may implement those writes a second time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from officina.core import portal_negocios as business


@dataclass(frozen=True)
class OSCommand:
    """Canonical write request; accepts the full existing Web form vocabulary.

    Attachment bytes, recipient references and rateio inputs deliberately stay
    in ``fields``: the domain writer validates them, not each transport.
    """

    actor_id: int
    fields: Mapping[str, Any]
    os_id: int | None = None

    @classmethod
    def from_web(cls, values: Mapping[str, Any], actor_id: int,
                 os_id: int | None = None) -> 'OSCommand':
        return cls(actor_id=int(actor_id), fields=dict(values), os_id=os_id)


def write_data(banco, command: OSCommand, *, connection=None,
               authorize=None, silent=False, staged_attachments=False) -> int:
    """Write domain data using the existing, authoritative transaction.

    If a connection is supplied, its caller must hold BEGIN IMMEDIATE and
    complete or roll back the transaction. The optional authorization callback
    runs in the same transaction as the SQL changes.
    """
    if command.actor_id <= 0:
        raise PermissionError('Identidade obrigatória para alterar OS.')
    return business.os_salvar(
        banco, command.fields, command.actor_id, command.os_id,
        silent=silent, connection=connection, authorize=authorize,
        staged_attachments=staged_attachments)
