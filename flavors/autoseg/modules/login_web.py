"""Minimal provider-only unified login adapter; no portal routing is defined here."""
from __future__ import annotations

import html

from flavors.autoseg.modules import auth, login_flags, web_cookie, web_session


def render_login(handler, error: str = "", identifier: str = "") -> None:
    """Render via the portal's existing page writer (which sends the response)."""
    escaped_id = html.escape(str(identifier or "")[:180], quote=True)
    escaped_error = html.escape(str(error or ""), quote=True)
    error_html = f'<p class="bad" role="alert">{escaped_error}</p>' if error else ""
    body = (
        '<section class="card"><h2>Entrar</h2>'
        f'{error_html}'
        '<form action="/entrar" method="post">'
        '<label for="unified_identifier">Identificador</label>'
        f'<input id="unified_identifier" name="identificador" type="text" '
        f'autocomplete="username" value="{escaped_id}" required>'
        '<label for="unified_password">Senha</label>'
        '<input id="unified_password" name="senha" type="password" '
        'autocomplete="current-password" required>'
        '<button type="submit">Entrar</button>'
        '</form><p><a href="/login">Usar login antigo</a></p></section>'
    )
    # handler.pagina already transmits the response; no second responder call.
    return handler.pagina("Entrar", body, None)


def authenticate_and_create(banco, identifier: str, password: str) -> tuple[str, web_session.SessionData]:
    try:
        result = auth.authenticate(banco, identifier, password)
    except auth.LoginError:
        # All public failures look the same; do not confirm account existence,
        # password correctness or identifier policy on the login page.
        raise auth.LoginError("invalid") from None
    if result.identity.kind != "provider" or not result.principal.active:
        raise auth.LoginError("invalid")
    credential = web_session.current_credential(banco, result.source, result.account_id, result.identity)
    if credential is None:
        raise auth.LoginError("invalid")
    try:
        return web_session.create(
            banco, result.account_id, result.identity, result.membership,
            result.principal, credential, result.source,
        )
    except ValueError:
        raise auth.LoginError("invalid") from None


def provider_session(handler, banco) -> dict | None:
    if not login_flags.unified_login_enabled(banco):
        return None
    token = web_cookie.token_from_headers(handler.headers)
    if not token:
        return None
    session = web_session.resolve(banco, token)
    if (session is None or session.identity.kind != "provider"
            or not session.principal.active):
        return None
    return {
        "pid": session.identity.id,
        "nome": session.identity.display_name,
        "admin": session.principal.role == "admin",
        "csrf": session.csrf,
        "telemetry_session": session.telemetry_session,
        "exp": session.expires_at,
        "unified": True,
    }
