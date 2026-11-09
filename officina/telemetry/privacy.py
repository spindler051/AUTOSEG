"""Privacy helpers for telemetry and the feedback channel.

These helpers are deliberately small and auditable. They are used by the
feedback channel; general telemetry remains off by default.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from urllib.parse import urlsplit


def page_path(value: str, limit: int = 300) -> str:
    """Return only the path of a URL, never query strings or fragments.

    Query strings can contain CPF/CNPJ, emails, tokens or search terms, so they
    are discarded before any event is created.
    """
    raw = str(value or "").strip()
    if not raw:
        return "/"
    parsed = urlsplit(raw)
    path = parsed.path or "/"
    return path[:limit]


def truncate_ip(value: str) -> str:
    """Coarsen an IP address for diagnostics.

    IPv4 becomes a /24 network address; IPv6 becomes a /48 network address.
    This keeps regional/security context without storing a full address.
    """
    address = ipaddress.ip_address(str(value or "").strip())
    prefix = 24 if address.version == 4 else 48
    network = ipaddress.ip_network(f"{address}/{prefix}", strict=False)
    return str(network.network_address)


def hash_ip(value: str, key: str) -> str:
    """Return a keyed, non-reversible IP pseudonym.

    The key belongs to the installation and must not be committed or logged.
    """
    if not key:
        raise ValueError("an installation-specific hash key is required")
    digest = hmac.new(
        key.encode("utf-8"),
        str(value or "").strip().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest[:32]
