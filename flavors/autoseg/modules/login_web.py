"""Unified login adapter; route dispatch and presentation remain at the web edge."""
from __future__ import annotations

from flavors.autoseg.modules import auth, login_flags, web_cookie, web_session, officina_web


def render_login(handler, error: str = "", identifier: str = "") -> None:
    return officina_web.login_page(handler, error=error, identifier=identifier)


def authenticate_and_create(
    banco, identifier: str, password: str,
    allowed_kinds: tuple[str, ...] = ("provider", "client"),
) -> tuple[str, web_session.SessionData]:
    try:
        result = auth.authenticate(banco, identifier, password)
        if (result.identity.kind not in ("provider", "client")
                or result.identity.kind not in allowed_kinds
                or not result.principal.active):
            raise auth.LoginError("invalid")
        credential = web_session.current_credential(
            banco, result.source, result.account_id, result.identity)
        if not credential:
            raise auth.LoginError("invalid")
        return web_session.create(
            banco, result.account_id, result.identity, result.membership,
            result.principal, credential, result.source)
    except (auth.LoginError, ValueError):
        # Public errors must not enumerate existence, inactive state or roles.
        raise auth.LoginError("invalid") from None


def unified_session(handler, banco) -> web_session.SessionData | None:
    if not login_flags.unified_login_enabled(banco):
        return None
    token = web_cookie.token_from_headers(handler.headers)
    if not token:
        return None
    return web_session.resolve(banco, token)


def provider_session(handler, banco) -> dict | None:
    session = unified_session(handler, banco)
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


def client_session(handler, banco) -> web_session.SessionData | None:
    session = unified_session(handler, banco)
    if (session is None or session.identity.kind != "client"
            or session.principal.role != "customer"
            or not session.principal.active):
        return None
    return session
