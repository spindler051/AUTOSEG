"""Event contract for the future telemetry subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .privacy import page_path

ALLOWED_EVENTS = frozenset({
    "page_view",
    "login_success",
    "login_failure",
    "logout",
    "error",
    "security_event",
    "admin_action",
    "feedback_open",
    "feedback_submit",
    "feedback_ai_reply",
    "feedback_ai_error",
    "feedback_triage",
})

ALLOWED_ACTOR_TYPES = frozenset({"anonymous", "user", "admin", "system"})

ALLOWED_ATTRIBUTES = frozenset({
    "request_id",
    "status_code",
    "duration_ms",
    "error_code",
    "method",
    "route",
    "notice_version",
    "prestador_id",
    "feedback_id",
    "abertura_id",
    "category",
    "urgency",
    "ai_requested",
    "ai_status",
    "triage_status",
    "status",
    "ui_mode",
    "tab",
})

SENSITIVE_ATTRIBUTES = frozenset({
    "password",
    "senha",
    "token",
    "cookie",
    "authorization",
    "cpf",
    "cnpj",
    "email",
    "telefone",
    "phone",
    "nome",
    "name",
    "documento",
    "document",
    "form",
    "query",
    "search",
    "clipboard",
    "keystroke",
})

_MAX_ATTRIBUTE_LENGTH = 200


@dataclass(frozen=True)
class TelemetryEvent:
    """A single, minimized telemetry event.

    The caller is responsible for pseudonymizing IPs before constructing the
    event. The event contract itself never accepts form values, page content or
    free-form metadata.
    """

    name: str
    occurred_at: str
    session_id: str
    page: str
    authenticated: bool
    actor_type: str = "anonymous"
    ip: str | None = None
    browser_family: str = ""
    browser_major: str = ""
    os_family: str = ""
    device_type: str = ""
    screen_width: int | None = None
    screen_height: int | None = None
    viewport_width: int | None = None
    viewport_height: int | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.name not in ALLOWED_EVENTS:
            raise ValueError(f"event not allowed: {self.name}")
        if self.actor_type not in ALLOWED_ACTOR_TYPES:
            raise ValueError(f"actor_type not allowed: {self.actor_type}")
        if not str(self.session_id or "").strip():
            raise ValueError("session_id is required")
        if not str(self.occurred_at or "").strip():
            raise ValueError("occurred_at is required")
        object.__setattr__(self, "page", page_path(self.page))
        clean = {}
        for key, value in dict(self.attributes).items():
            key = str(key).strip().lower()
            if key in SENSITIVE_ATTRIBUTES:
                raise ValueError(f"sensitive attribute not allowed: {key}")
            if key not in ALLOWED_ATTRIBUTES:
                raise ValueError(f"attribute not allowed: {key}")
            if isinstance(value, bool) or isinstance(value, (int, float)):
                clean[key] = value
            elif isinstance(value, str):
                if len(value) > _MAX_ATTRIBUTE_LENGTH:
                    raise ValueError(f"attribute too long: {key}")
                clean[key] = value
            else:
                raise ValueError(f"unsupported attribute type: {key}")
        object.__setattr__(self, "attributes", clean)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "event": self.name,
            "occurred_at": self.occurred_at,
            "session_id": self.session_id,
            "page": self.page,
            "authenticated": bool(self.authenticated),
            "actor_type": self.actor_type,
        }
        for key in (
            "ip",
            "browser_family",
            "browser_major",
            "os_family",
            "device_type",
            "screen_width",
            "screen_height",
            "viewport_width",
            "viewport_height",
        ):
            value = getattr(self, key)
            if value not in (None, ""):
                payload[key] = value
        if self.attributes:
            payload["attributes"] = dict(self.attributes)
        return payload
