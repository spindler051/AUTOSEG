"""Generic presentation route contract, without flavor-specific paths."""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class WebRoute:
    path: str
    permission: str | None
    contexts: tuple[str, ...]
    handler: Callable
