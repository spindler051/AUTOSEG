"""HTTP cookie and CSRF helpers for the opt-in unified web session."""
from __future__ import annotations

import html
import re
import secrets
from http.cookies import CookieError, SimpleCookie

from flavors.autoseg.modules import web_session

COOKIE_NAME = web_session.COOKIE_NAME
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,256}$")


def set_cookie(token: str, secure: bool = False,
               max_age: int = web_session.SESSION_TTL) -> str:
    """Serialize a session cookie with explicit browser isolation attributes."""
    if not isinstance(token, str) or not _TOKEN_PATTERN.fullmatch(token):
        raise ValueError("Invalid cookie token.")
    if not isinstance(max_age, int) or isinstance(max_age, bool) or not 0 <= max_age <= web_session.SESSION_TTL:
        raise ValueError("Invalid cookie lifetime.")
    parts = [f"{COOKIE_NAME}={token}", "Path=/", "HttpOnly", "SameSite=Strict",
             f"Max-Age={max_age}"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def clear_cookie(secure: bool = False) -> str:
    parts = [f"{COOKIE_NAME}=", "Path=/", "HttpOnly", "SameSite=Strict", "Max-Age=0"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def token_from_headers(headers) -> str | None:
    """Read only the opaque session token from an HTTP Cookie header."""
    try:
        value = headers.get("Cookie", "")
        if not isinstance(value, str) or len(value) > 16384:
            return None
        cookies = SimpleCookie()
        cookies.load(value)
        item = cookies.get(COOKIE_NAME)
        if item is None or not _TOKEN_PATTERN.fullmatch(item.value):
            return None
        return item.value
    except (ValueError, TypeError, CookieError, AttributeError):
        return None


def secure_request(headers) -> bool:
    """Match existing provider-portal TLS proxy hints.

    The forwarding headers are trusted only when the origin is restricted to
    loopback or the configured Cloudflare proxy; never expose this origin directly.
    """
    try:
        return bool(headers.get("CF-Ray")) or str(headers.get("X-Forwarded-Proto", "")).strip().lower() == "https"
    except (AttributeError, TypeError):
        return False


def csrf_input(session: web_session.SessionData) -> str:
    """Render a hidden CSRF field for an authenticated form."""
    return f'<input type="hidden" name="csrf" value="{html.escape(session.csrf, quote=True)}">'


def csrf_valid(session: web_session.SessionData | None, supplied: str) -> bool:
    if session is None or not isinstance(supplied, str) or not supplied:
        return False
    expected = getattr(session, "csrf", None)
    return bool(isinstance(expected, str) and expected and secrets.compare_digest(expected, supplied))
