"""Immutable presentation contracts; authorization stays in application services."""
from dataclasses import dataclass
from .brand import Brand

@dataclass(frozen=True)
class NavItem:
    id: str
    label: str
    href: str
    permission: str | None = None
    contexts: tuple[str, ...] = ("provider", "client")
    group: str = ""
    icon: str = "info"
    top: bool = False
    top_order: int = 100

@dataclass(frozen=True)
class PageContext:
    brand: Brand
    kind: str
    display_name: str
    context_label: str
    navigation: tuple[NavItem, ...] = ()
    csrf: str = ""
    role: str = ""
    permissions: frozenset[str] = frozenset()
