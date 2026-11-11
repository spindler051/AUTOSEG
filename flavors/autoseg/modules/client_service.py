"""Owner-scoped customer operations using existing legacy service contracts."""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from flavors.autoseg.modules import cliente_fluxo_v94 as fluxo_pf
from flavors.autoseg.modules import accounts
from officina.core import fluxo_os as fluxo, prestadores_ext as ext
from pathlib import Path


@dataclass(frozen=True)
class ClientWorkItem:
    id: int
    number: str
    status: str
    description: str
    organization: str
    updated_at: str
    has_documents: bool


@dataclass(frozen=True)
class ClientCall:
    id: int
    status: str
    description: str
    organization: str
    updated_at: str
    work_id: int | None
    work_number: str


@dataclass(frozen=True)
class ClientDocument:
    id: int
    name: str
    kind: str
    work_id: int


def _client_id(session) -> int:
    """Require an active authenticated legacy client identity."""
    if (session is None or session.identity.kind != "client"
            or not session.identity.active or not session.membership.active
            or session.membership.identity_kind != "client"
            or session.membership.identity_id != session.identity.id
            or session.principal.role != "customer"
            or not session.principal.active):
        raise PermissionError("Client access denied.")
    return int(session.identity.id)


def _item(row, has_documents=False) -> ClientWorkItem:
    return ClientWorkItem(
        id=int(row["id"]), number=str(row["numero_os"] or ""),
        status=str(row["status"] or ""), description=str(row["descricao"] or ""),
        organization="", updated_at=str(row["data_abertura"] or ""),
        has_documents=has_documents,
    )


def _safe(operation):
    try:
        return operation()
    except (sqlite3.Error, OSError, KeyError, TypeError, ValueError):
        raise PermissionError("Client resource unavailable.") from None


def list_work_items(banco, session) -> tuple[ClientWorkItem, ...]:
    uid = _client_id(session)
    return _safe(lambda: tuple(_item(r) for r in fluxo_pf.listar_os_pf(banco, uid)))


def get_work_item(banco, session, work_id: int) -> ClientWorkItem | None:
    try:
        work_id = int(work_id)
    except (ValueError, TypeError, OverflowError):
        return None
    uid = _client_id(session)
    return _safe(lambda: _item(row) if (row := fluxo_pf.obter_os_pf(banco, uid, work_id)) else None)


def _owned_work(banco, session, work_id: int):
    uid = _client_id(session)
    try:
        work_id = int(work_id)
    except (ValueError, TypeError, OverflowError):
        raise PermissionError("Document unavailable.") from None
    if work_id <= 0:
        raise PermissionError("Document unavailable.")
    # Existing legacy service scopes the query to the user's linked PF record.
    row = _safe(lambda: fluxo_pf.obter_os_pf(banco, uid, work_id))
    if row is None:
        raise PermissionError("Document unavailable.")
    return row


def list_documents(banco, session, work_id: int) -> tuple[ClientDocument, ...]:
    row = _owned_work(banco, session, work_id)
    return _safe(lambda: _documents_for_os(banco, row))


def _documents_for_os(banco, row) -> tuple[ClientDocument, ...]:
    documents: list[ClientDocument] = []
    if row["status"] in fluxo.FIM:
        published = fluxo.ultimo_documento(banco, int(row["id"]))
        if published and int(published["id"]) > 0:
            documents.append(ClientDocument(-int(published["id"]),
                                            "Relatório PDF", "report", int(row["id"])))
    for item in ext.listar_notas_fiscais(banco, int(row["id"])):
        documents.append(ClientDocument(int(item["id"]),
                                        str(item["nome_original"]), "invoice", int(row["id"])))
    return tuple(documents)


def open_document(banco, session, work_id: int,
                  document_id: int) -> tuple[bytes, str, str]:
    # The owner check occurs before loading any document metadata or paths.
    row = _owned_work(banco, session, work_id)
    return _open_owned_document(banco, row, document_id)


def _open_owned_document(banco, row, document_id):
    try:
        document_id = int(document_id)
    except (ValueError, TypeError, OverflowError):
        raise PermissionError("Document unavailable.") from None
    if document_id == 0:
        raise PermissionError("Document unavailable.")
    if document_id < 0:
        if row["status"] not in fluxo.FIM:
            raise PermissionError("Document unavailable.")
        record = _safe(lambda: fluxo.ultimo_documento(banco, int(row["id"])))
        if not record or int(record["id"]) != -document_id:
            raise PermissionError("Document unavailable.")
        try:
            filename = Path(fluxo.validar_pdf_publicado(record))
            return filename.read_bytes(), "application/pdf", "relatorio.pdf"
        except (OSError, ValueError, sqlite3.Error):
            raise PermissionError("Document unavailable.") from None
    # Obtain the invoice exclusively through its existing validated service.
    allowed = any(d.id == document_id for d in _safe(lambda: _documents_for_os(banco, row))
                  if d.kind == "invoice")
    if not allowed:
        raise PermissionError("Document unavailable.")
    try:
        record, filename = ext.obter_nota_fiscal(banco, int(row["id"]), document_id)
        if int(record["id"]) != document_id:
            raise PermissionError("Document unavailable.")
        return Path(filename).read_bytes(), "application/pdf", "nota-fiscal.pdf"
    except (OSError, ValueError, sqlite3.Error):
        raise PermissionError("Document unavailable.") from None


def create_request(banco, session, description: str, urgency: str) -> ClientWorkItem:
    uid = _client_id(session)
    # Validate before touching the PF link; the legacy service still validates
    # again when it records the OS.
    if not 10 <= len(str(description).strip()) <= 2000 or urgency not in ("Normal", "Alta", "Baixa"):
        raise ValueError("Invalid request.")
    if session.source == "account":
        if type(session.account_id) is not int:
            raise PermissionError("Client resource unavailable.")
        pf_id = _safe(lambda: fluxo_pf.garantir_perfil_pf(banco, uid))
        _safe(lambda: accounts.sync_client_pf_link(banco, session.account_id, uid))
        if not pf_id:
            raise PermissionError("Client resource unavailable.")
    created = _safe(lambda: fluxo_pf.registrar_os_pf(banco, uid, description, urgency))
    # The underlying operation may return a number or a dict depending on
    # the legacy deployment: never assume a new request belongs to an actor.
    if isinstance(created, dict):
        work_id = created.get("os_id", created.get("id"))
    else:
        work_id = created
    if not isinstance(work_id, int):
        raise RuntimeError("Created request id is unavailable.")
    item = get_work_item(banco, session, work_id)
    if item is None:
        raise RuntimeError("Created request is not visible to its owner.")
    return item


def _call(row) -> ClientCall:
    return ClientCall(int(row["id"]), str(row["status"] or ""),
                      str(row["descricao"] or ""), str(row["organizacao"] or ""),
                      str(row["criado_em"] or ""),
                      int(row["os_id"]) if row["os_id"] is not None else None,
                      str(row["numero_os"] or ""))


def list_calls(banco, session) -> tuple[ClientCall, ...]:
    uid = _client_id(session)
    def query():
        with ext.db(banco) as c:
            rows = c.execute("""SELECT h.id,h.status,h.descricao,h.criado_em,h.os_id,
                o.nome AS organizacao,os.numero_os
                FROM v9_chamados AS h
                JOIN v9_organizacoes AS o ON o.id=h.organizacao_id
                LEFT JOIN ordens_servico AS os ON os.id=h.os_id
                WHERE h.usuario_id=? ORDER BY h.id DESC LIMIT 100""", (uid,)).fetchall()
        return tuple(_call(row) for row in rows)
    return _safe(query)


def get_call(banco, session, call_id: int) -> ClientCall | None:
    uid = _client_id(session)
    if type(call_id) is not int or call_id <= 0:
        return None
    return _safe(lambda: _call(row) if (row := fluxo_pf.obter_chamado(banco, uid, call_id)) else None)


def _owned_call_work(banco, session, call_id: int):
    call = get_call(banco, session, call_id)
    if not call or call.work_id is None:
        raise PermissionError("Document unavailable.")
    # Ownership is the call's immutable requester id, not the associated
    # organization's name or an untrusted work ID from a URL.
    def query():
        with ext.db(banco) as c:
            return c.execute("""SELECT id,status FROM ordens_servico WHERE id=?""",
                             (call.work_id,)).fetchone()
    row = _safe(query)
    if row is None:
        raise PermissionError("Document unavailable.")
    return row


def list_call_documents(banco, session, call_id: int) -> tuple[ClientDocument, ...]:
    row = _owned_call_work(banco, session, call_id)
    return _safe(lambda: _documents_for_os(banco, row))


def open_call_document(banco, session, call_id: int, document_id: int):
    row = _owned_call_work(banco, session, call_id)
    return _open_owned_document(banco, row, document_id)
