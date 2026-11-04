"""Telemetry sinks. No sink is wired into the application yet."""

from __future__ import annotations

from typing import Any, Protocol


class TelemetrySink(Protocol):
    def emit(self, payload: dict[str, Any]) -> None:
        """Persist or export one already-validated event."""


class NoopSink:
    """Default sink: discard everything."""

    def emit(self, payload: dict[str, Any]) -> None:
        return None


class MemorySink:
    """Test-only sink. Never use in production."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, payload: dict[str, Any]) -> None:
        self.events.append(dict(payload))
