"""Page context contains presentation data, never authorization decisions."""
from dataclasses import dataclass

from .brand import Brand


@dataclass(frozen=True)
class NavItem:
    id: str
    label: str
    href: str
    permission: str | None = None


@dataclass(frozen=True)
class PageContext:
    brand: Brand
    kind: str
    display_name: str
    context_label: str
    navigation: tuple[NavItem, ...] = ()
    csrf: str = ""
