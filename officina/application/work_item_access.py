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


def require_work_item_locked(connection, principal, work_id: int, action: str):
    """Authorize using the writer's current SQLite transaction.

    The caller must acquire BEGIN IMMEDIATE before this check and must not
    mutate the order or its relationships before it. This helper never starts
    or commits a second transaction.
    """
    if type(work_id) is not int or work_id <= 0:
        raise PermissionError("Recurso indisponível.")
    if not connection.in_transaction:
        raise RuntimeError("Authorization requires an active writer transaction.")
    try:
        resource = _resource(connection, work_id)
        return ObjectPolicy().require(principal, action, resource)
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError):
        raise PermissionError("Recurso indisponível.") from None


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

def can_read_all(principal, kind: str = "work_item") -> bool:
    """Resolve global read permission through the policy, not the web session."""
    return ObjectPolicy().can(
        principal, 'view', Resource(kind, organization_id='autoseg')
    ).allowed


def require_read_work_item(banco, principal, work_id: int, action: str = 'view'):
    """Enforce read authorization regardless of write-enforcement flags."""
    if action not in ('view', 'read'):
        raise ValueError('Unsupported read action.')
    resource = resource_for_work_item(banco, work_id)
    return ObjectPolicy().require(principal, 'view', resource)


def shared_queue_item(banco, principal, work_id: int, *, enforce_assume_policy=False):
    """Read only shareable fields of an active OS without loading its form."""
    if not principal.active or principal.organization_id != 'autoseg' or principal.provider_id is None:
        raise PermissionError('Recurso indisponível.')
    with ext.db(banco) as c:
        item = c.execute('''SELECT o.id,o.numero_os,o.status,o.data_abertura,
                   COALESCE(o.atualizado_em,o.data_abertura) AS atualizado_em,
                   cl.nome AS cliente,p.nome AS responsavel,
                   (SELECT GROUP_CONCAT(nome, ', ') FROM (
                     SELECT DISTINCT p2.nome AS nome FROM os_prestadores op
                     JOIN prestadores p2 ON p2.id=op.prestador_id
                     WHERE op.os_id=o.id AND op.ativo=1 ORDER BY p2.nome
                   )) AS participantes
                FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id
                LEFT JOIN os_responsaveis r ON r.os_id=o.id
                LEFT JOIN prestadores p ON p.id=r.prestador_id
                WHERE o.id=? AND o.status IN ('Aberta','Iniciada','Pendente')
                  AND COALESCE(o.arquivada,0)=0''', (work_id,)).fetchone()
        if item is None:
            raise PermissionError('Recurso indisponível.')
        decision = ObjectPolicy().can(principal, 'view', _resource(c, work_id))
        if decision.relationship != 'other' or decision.reason != 'Sem vínculo com o recurso.':
            raise PermissionError('Recurso indisponível.')
        may_assume = ext.pode_assumir(c, work_id, principal.provider_id)
        if may_assume and enforce_assume_policy:
            may_assume = ObjectPolicy().can(principal, 'assume',
                                            _resource(c, work_id)).allowed
        return dict(item), may_assume


def _customer_resource(connection, principal, customer_id: int) -> Resource:
    if type(customer_id) is not int or customer_id <= 0:
        raise PermissionError('Recurso indisponível.')
    if can_read_all(principal, 'customer'):
        row = connection.execute('SELECT id FROM clientes WHERE id=?', (customer_id,)).fetchone()
        participant_ids = frozenset()
    else:
        pid = principal.provider_id
        if pid is None:
            raise PermissionError('Recurso indisponível.')
        row = connection.execute('''SELECT cl.id FROM clientes cl WHERE cl.id=? AND EXISTS (
            SELECT 1 FROM ordens_servico o WHERE o.cliente_id=cl.id AND (
                EXISTS (SELECT 1 FROM os_responsaveis r
                        WHERE r.os_id=o.id AND r.prestador_id=?) OR
                EXISTS (SELECT 1 FROM os_prestadores op
                        WHERE op.os_id=o.id AND op.prestador_id=? AND op.ativo=1)
            ))''', (customer_id,pid,pid)).fetchone()
        participant_ids = frozenset((pid,)) if row else frozenset()
    if row is None:
        raise PermissionError('Recurso indisponível.')
    return Resource('customer', customer_id, organization_id='autoseg',
                    participant_ids=participant_ids)


def require_customer_read(banco, principal, customer_id: int, action: str = 'view'):
    if action != 'view':
        raise ValueError('Unsupported customer read action.')
    try:
        with ext.db(banco) as connection:
            resource = _customer_resource(connection, principal, customer_id)
        return ObjectPolicy().require(principal, 'view', resource)
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError):
        raise PermissionError('Recurso indisponível.') from None


def customer_field_allowed(banco, principal, customer_id: int, field: str) -> bool:
    try:
        with ext.db(banco) as connection:
            resource = _customer_resource(connection, principal, customer_id)
        return ObjectPolicy().can_view_field(principal, resource, 'customer.' + field).allowed
    except PermissionError:
        return False


def require_customer_contact(banco, principal, customer_id: int):
    try:
        with ext.db(banco) as connection:
            resource = _customer_resource(connection, principal, customer_id)
        return ObjectPolicy().require(
            principal, 'view', Resource('customer.contact', resource.id,
                                       resource.organization_id,
                                       participant_ids=resource.participant_ids))
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError):
        raise PermissionError('Recurso indisponível.') from None

def involved_customer_field_scopes(principal):
    """Field scopes for customers selected by SQL involvement predicates."""
    if not principal.active or principal.organization_id != 'autoseg':
        raise PermissionError('Recurso indisponível.')
    scope = Resource('customer', organization_id='autoseg',
                     participant_ids=frozenset((principal.provider_id,))
                     if principal.provider_id is not None else frozenset())
    policy = ObjectPolicy()
    policy.require(principal, 'view', scope)
    return frozenset(field for field in ('nome','documento','telefone','email','endereco')
                     if policy.can_view_field(principal,scope,'customer.'+field).allowed)


def require_customer_create(principal):
    """Customer creation has no preexisting OS involvement."""
    return ObjectPolicy().require(principal, 'create',
                                  Resource('customer', organization_id='autoseg'))


def require_customer_write(banco, principal, customer_id: int):
    """Edit only a current SQL-involved customer or an authorized administrator."""
    try:
        with ext.db(banco) as connection:
            resource = _customer_resource(connection, principal, customer_id)
        return ObjectPolicy().require(principal, 'edit', resource)
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError):
        raise PermissionError('Recurso indisponível.') from None
