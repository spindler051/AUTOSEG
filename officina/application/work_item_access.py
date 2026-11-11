"""The authoritative, fail-closed authorization boundary for AUTOSEG orders.

An order's responsible provider is os_responsaveis, *not* the historic
ordens_servico.prestador_id. Participants must have os_prestadores.ativo=1.
Absent relationships never create an implicit ownership grant.
"""
from __future__ import annotations

import sqlite3

from officina.application.object_policy import ObjectPolicy, Resource, PermissionDenied
from officina.core import prestadores_ext as ext


def _work_row(c, work_id):
    return c.execute("SELECT id,cliente_id FROM ordens_servico WHERE id=?", (work_id,)).fetchone()


def _resource(c, work_id: int) -> Resource:
    record = _work_row(c, work_id)
    if record is None:
        raise PermissionError("Recurso indisponível.")
    responsible = ext.responsavel_atual(c, work_id)
    participants = c.execute("""SELECT prestador_id FROM os_prestadores
        WHERE os_id=? AND ativo=1""", (work_id,)).fetchall()
    # The organization can be established by a customer organization mapping
    # or by the linked v9_chamados; never infer it from a UI-supplied ID.
    orgs = c.execute("""SELECT DISTINCT id FROM v9_organizacoes
        WHERE cliente_id=? AND mesclado_em IS NULL
        UNION SELECT DISTINCT h.organizacao_id FROM v9_chamados h
        JOIN v9_organizacoes o ON o.id=h.organizacao_id AND o.mesclado_em IS NULL
        WHERE h.os_id=?""", (record["cliente_id"],work_id)).fetchall()
    org_id = int(orgs[0][0]) if len(orgs) == 1 else None
    requester = c.execute("""SELECT usuario_id FROM v9_chamados
        WHERE os_id=? LIMIT 2""", (work_id,)).fetchall()
    requester_id = int(requester[0][0]) if len(requester) == 1 else None
    return Resource(
        kind="work_item", id=work_id, organization_id="autoseg",
        owner_id=int(responsible) if responsible is not None else None,
        participant_ids=frozenset(int(row[0]) for row in participants),
        client_id=int(record["cliente_id"]) if record["cliente_id"] is not None else None,
        client_org_id=org_id,
        attributes={"requester_user_id":requester_id},
    )


def resource_for_work_item(banco, work_id: int) -> Resource:
    if type(work_id) is not int or work_id <= 0:
        raise PermissionError("Recurso indisponível.")
    try:
        with ext.db(banco) as c:
            return _resource(c, work_id)
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError):
        raise PermissionError("Recurso indisponível.") from None


def require_work_item(banco, principal, work_id: int, action: str):
    try:
        resource = resource_for_work_item(banco, work_id)
        return ObjectPolicy().require(principal, action, resource)
    except (ValueError, TypeError, KeyError):
        raise PermissionError("Recurso indisponível.") from None


def require_document(banco, principal, work_id: int, document_id: int,
                     action: str = "download"):
    from officina.core import fluxo_os
    if type(document_id) is not int or document_id == 0:
        raise PermissionError("Documento indisponível.")
    # Check object ownership before even looking up existence or metadata.
    resource = resource_for_work_item(banco, work_id)
    doc = Resource("document", document_id, resource.organization_id,
                   resource.owner_id, resource.client_id,
                   resource.participant_ids, resource.attributes,
                   resource.client_org_id)
    decision = ObjectPolicy().require(principal, action, doc)
    try:
        if document_id < 0:
            record = fluxo_os.ultimo_documento(banco, work_id)
            if not record or int(record["id"]) != -document_id:
                raise PermissionError("Documento indisponível.")
        else:
            if not any(int(x["id"]) == document_id
                       for x in ext.listar_notas_fiscais(banco, work_id)):
                raise PermissionError("Documento indisponível.")
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError):
        raise PermissionError("Documento indisponível.") from None
    return decision


def require_create(banco, principal):
    # The application is single-provider at present; unknown tenancy is denied.
    if not principal.active or principal.organization_id != 'autoseg':
        raise PermissionError('Operação indisponível.')
    return ObjectPolicy().require(principal, 'create',
                                  Resource('work_item',organization_id='autoseg'))


def resource_for_call(banco, call_id: int) -> Resource:
    if type(call_id) is not int or call_id <= 0:
        raise PermissionError("Recurso indisponível.")
    try:
        with ext.db(banco) as c:
            row = c.execute("""SELECT h.usuario_id,h.organizacao_id,h.os_id
            FROM v9_chamados h JOIN v9_organizacoes o ON o.id=h.organizacao_id
            WHERE h.id=? AND o.mesclado_em IS NULL""",(call_id,)).fetchone()
            if not row:
                raise PermissionError("Recurso indisponível.")
            return Resource("work_item",call_id,organization_id="autoseg",
                            client_org_id=int(row["organizacao_id"]),
                            attributes={"requester_user_id":int(row["usuario_id"]),
                                        "linked_os_id":row["os_id"]})
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError):
        raise PermissionError("Recurso indisponível.") from None


def require_call(banco, principal, call_id: int, action: str = "view"):
    return ObjectPolicy().require(principal, action, resource_for_call(banco,call_id))
