"""Shared shell contract. Host applications inject their chrome renderer."""
from dataclasses import dataclass, field
from typing import Callable
from .context import NavItem, PageContext

@dataclass(frozen=True)
class ShellPage:
    title: str
    content: str
    context: PageContext
    navigation: tuple[NavItem, ...]
    active: str = ""
    path: str = "/"
    banco: object = field(default=None, repr=False)
    user: object = field(default=None, repr=False)


def render_shell(page: ShellPage, chrome: Callable[[ShellPage], str]) -> str:
    """Render one page with the explicitly supplied, flavor-owned chrome.

    No dependency on a specific flavor, database schema, portal or CSS.
    """
    if not callable(chrome):
        raise TypeError("A shell chrome renderer is required.")
    return chrome(page)
