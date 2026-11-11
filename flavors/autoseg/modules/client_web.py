"""Customer-only HTTP presentation backed by owner-scoped service calls."""
from __future__ import annotations

from html import escape

from flavors.autoseg.modules import client_service, officina_web, web_cookie


def _e(value) -> str:
    return escape(str(value or ""), quote=True)


def _item_link(item) -> str:
    return f'<li><a href="/cliente/os/{item.id}">{_e(item.number)}</a> — {_e(item.status)}</li>'


def _call_link(call) -> str:
    return (f'<li><a href="/cliente/chamado/{call.id}">Chamado #{call.id}</a>'
            f' — {_e(call.status)}</li>')


def home(handler, banco, session) -> None:
    items = client_service.list_work_items(banco, session)
    calls = client_service.list_calls(banco, session)
    body = ('<section class="card"><h2>Minhas ordens de serviço</h2><ul>'
            + ''.join(_item_link(item) for item in items)
            + '</ul><a href="/cliente/solicitar">Solicitar serviço</a></section>'
            '<section class="card"><h2>Meus chamados</h2><ul>'
            + ''.join(_call_link(call) for call in calls) + '</ul></section>')
    officina_web.page(handler, "Painel do cliente", body, session)


def list_items(handler, banco, session) -> None:
    items = client_service.list_work_items(banco, session)
    calls = client_service.list_calls(banco, session)
    body = ('<section class="card"><h2>Ordens particulares</h2><ul>'
            + ''.join(_item_link(item) for item in items) + '</ul></section>'
            '<section class="card"><h2>Chamados próprios</h2><ul>'
            + ''.join(_call_link(call) for call in calls) + '</ul></section>')
    officina_web.page(handler, "Minhas OS", body, session)


def item_detail(handler, banco, session, work_id: int) -> None:
    item = client_service.get_work_item(banco, session, work_id)
    if item is None:
        return handler.erro("Ordem de serviço não encontrada.", 404)
    body = (f'<section class="card"><p>{_e(item.number)} — {_e(item.status)}</p>'
            f'<p>{_e(item.description)}</p></section>')
    docs = client_service.list_documents(banco, session, work_id)
    if docs:
        body += '<section class="card"><h2>Documentos</h2>' + ''.join(
            f'<a href="/cliente/os/{item.id}/documento/{d.id}">{_e(d.name)}</a> '
            for d in docs) + '</section>'
    officina_web.page(handler, "Detalhes da OS", body, session)


def documents(handler, banco, session) -> None:
    groups = []
    for item in client_service.list_work_items(banco, session):
        docs = client_service.list_documents(banco, session, item.id)
        links = ''.join(
            f'<li><a href="/cliente/os/{item.id}/documento/{doc.id}">{_e(doc.name)}</a></li>'
            for doc in docs
        )
        if links:
            groups.append(f'<section class="card"><h2>{_e(item.number)}</h2><ul>{links}</ul></section>')
    for call in client_service.list_calls(banco, session):
        if call.work_id is None:
            continue
        docs = client_service.list_call_documents(banco, session, call.id)
        links = ''.join(
            f'<li><a href="/cliente/chamado/{call.id}/documento/{doc.id}">{_e(doc.name)}</a></li>'
            for doc in docs)
        if links:
            groups.append(f'<section class="card"><h2>Chamado #{call.id}</h2><ul>{links}</ul></section>')
    officina_web.page(handler, "Documentos", ''.join(groups) or
                      '<p>Nenhum documento disponível.</p>', session)


def request_form(handler, banco, session, error: str = "",
                 description: str = "", urgency: str = "") -> None:
    client_service.list_work_items(banco, session)
    msg = '<p role="alert" class="bad">Não foi possível enviar a solicitação.</p>' if error else ''
    options = ''.join(f'<option value="{v}" {"selected" if urgency == v else ""}>{v}</option>'
                      for v in ("Normal", "Alta", "Baixa"))
    body = ('<section class="card">' + msg +
            '<form method="post" action="/cliente/solicitar">'
            f'{web_cookie.csrf_input(session)}'
            '<label for="description">Descrição</label>'
            f'<textarea id="description" name="descricao" minlength="10" maxlength="2000" required>{_e(description)}</textarea>'
            f'<label for="urgency">Urgência</label><select id="urgency" name="urgencia">{options}</select>'
            '<button type="submit">Solicitar serviço</button></form></section>')
    officina_web.page(handler, "Solicitar serviço", body, session)


def _refresh_session_cookie(handler, banco, session) -> str | None:
    """Rotate only when the persisted PF identity/link outgrew this session."""
    from flavors.autoseg.modules import accounts, identity, web_session

    if session.source == "account":
        ident = accounts.identity_for_account(banco, session.account_id)
        membership = accounts.membership_for_account(banco, session.account_id)
    elif session.source == "legacy":
        ident = identity.load_identity(banco, "client", session.identity.id)
        memberships = identity.memberships(banco, ident) if ident else ()
        membership = memberships[0] if len(memberships) == 1 else None
    else:
        raise PermissionError("Client resource unavailable.")

    if (ident is None or membership is None or ident.kind != "client"
            or not ident.active or not membership.active
            or membership.identity_id != session.identity.id):
        raise PermissionError("Client resource unavailable.")
    if (session.membership.client_id == membership.client_id
            and session.identity.client_id == ident.client_id):
        return None
    if membership.client_id is None or ident.client_id is None:
        raise PermissionError("Client resource unavailable.")

    try:
        principal = identity.to_principal(ident, membership)
        credential = web_session.current_credential(
            banco, session.source, session.account_id, ident)
        if not principal.active or not credential:
            raise ValueError("Invalid client session")
        token, _new_session = web_session.create(
            banco, session.account_id, ident, membership, principal,
            credential, session.source)
    except (ValueError, TypeError):
        raise PermissionError("Client resource unavailable.") from None

    old = web_cookie.token_from_headers(handler.headers)
    if old:
        web_session.revoke(old)
    return web_cookie.set_cookie(
        token, secure=web_cookie.secure_request(handler.headers))


def request_submit(handler, banco, session, data) -> None:
    if not isinstance(data, dict) or not web_cookie.csrf_valid(session, data.get('csrf', '')):
        return handler.erro("Formulário expirado ou sessão inválida.", 403)
    try:
        item = client_service.create_request(banco, session,
                                             str(data.get('descricao', '')),
                                             str(data.get('urgencia', 'Normal')))
    except (ValueError, PermissionError) as exc:
        # PF creation/link synchronization may have committed before the OS
        # operation failed. Rotate even on failure to avoid a stale session.
        cookie = _refresh_session_cookie(handler, banco, session)
        if cookie is not None:
            return handler.redir('/cliente/solicitar?erro=1', cookie)
        if isinstance(exc, PermissionError):
            raise
        return request_form(handler, banco, session, error='invalid',
                            description=str(data.get('descricao', ''))[:2000],
                            urgency=str(data.get('urgencia', '')))
    cookie = _refresh_session_cookie(handler, banco, session)
    return handler.redir(f'/cliente/os/{item.id}', cookie)


def download(handler, banco, session, work_id: int, document_id: int) -> None:
    try:
        contents, mime, filename = client_service.open_document(
            banco, session, work_id, document_id)
    except PermissionError:
        return handler.erro("Documento indisponível.", 404)
    return handler.send_bytes(contents, mime, filename=filename)


def call_detail(handler, banco, session, call_id: int) -> None:
    call = client_service.get_call(banco, session, call_id)
    if call is None:
        return handler.erro("Recurso indisponível.", 404)
    body = (f'<section class="card"><h2>Chamado #{call.id}</h2>'
            f'<p>{_e(call.status)}</p><p>{_e(call.organization)}</p>'
            f'<p>{_e(call.description)}</p></section>')
    if call.work_id is not None:
        body += f'<p>OS vinculada: {_e(call.work_number or call.work_id)}</p>'
        docs = client_service.list_call_documents(banco, session, call_id)
        body += '<section class="card"><h2>Documentos do chamado</h2>' + ''.join(
            f'<a href="/cliente/chamado/{call.id}/documento/{d.id}">{_e(d.name)}</a> '
            for d in docs) + '</section>'
    officina_web.page(handler, "Detalhe do chamado", body, session)


def download_call(handler, banco, session, call_id: int, document_id: int) -> None:
    try:
        contents, mime, filename = client_service.open_call_document(
            banco, session, call_id, document_id)
    except PermissionError:
        return handler.erro("Documento indisponível.", 404)
    return handler.send_bytes(contents, mime, filename=filename)


def dispatch_get(handler, banco, session, path: str) -> None:
    """Dispatch only allowlisted customer URLs; unknown URLs fail closed."""
    if path in ("/cliente", "/cliente/painel"):
        return home(handler, banco, session)
    if path == "/cliente/os":
        return list_items(handler, banco, session)
    if path == "/cliente/documentos":
        return documents(handler, banco, session)
    if path == "/cliente/solicitar":
        from urllib.parse import parse_qs, urlparse
        failed = parse_qs(urlparse(handler.path).query).get("erro") == ["1"]
        return request_form(handler, banco, session, error="invalid" if failed else "")
    if path == "/cliente/nova":
        return handler.redir("/cliente/solicitar")
    parts = path.strip("/").split("/")
    if len(parts) == 3 and parts[:2] == ["cliente", "chamado"] and parts[2].isdigit():
        return call_detail(handler, banco, session, int(parts[2]))
    if (len(parts) == 5 and parts[:2] == ["cliente", "chamado"]
            and parts[2].isdigit() and parts[3] == "documento"
            and parts[4].lstrip("-").isdigit()):
        return download_call(handler, banco, session, int(parts[2]), int(parts[4]))
    if len(parts) == 3 and parts[:2] == ["cliente", "os"] and parts[2].isdigit():
        return item_detail(handler, banco, session, int(parts[2]))
    if (len(parts) == 5 and parts[:2] == ["cliente", "os"]
            and parts[2].isdigit() and parts[3] == "documento"
            and parts[4].lstrip("-").isdigit()):
        return download(handler, banco, session, int(parts[2]), int(parts[4]))
    return handler.erro("Página indisponível.", 404)


def dispatch_post(handler, banco, session, path: str, data: dict) -> None:
    if path == "/cliente/solicitar":
        return request_submit(handler, banco, session, data)
    if path == "/cliente/sair":
        if not isinstance(data, dict) or not web_cookie.csrf_valid(session, data.get("csrf", "")):
            return handler.erro("Formulário expirado ou sessão inválida.", 403)
        from flavors.autoseg.modules import web_session
        token = web_cookie.token_from_headers(handler.headers)
        if token:
            web_session.revoke(token)
        return handler.redir("/entrar", (
            web_cookie.clear_cookie(secure=web_cookie.secure_request(handler.headers)),
            handler.cookie("", True),
        ))
    return handler.erro("Página indisponível.", 404)
