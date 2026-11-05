"""No-op-by-default telemetry client.

Only the Provider Portal feedback channel constructs this client today. A
future feature flag can decide whether to instrument the other portals or the
GTK app.
"""

from __future__ import annotations

from .config import TelemetryConfig
from .events import TelemetryEvent
from .sinks import NoopSink, TelemetrySink


class TelemetryClient:
    def __init__(self, config: TelemetryConfig | None = None, sink: TelemetrySink | None = None):
        self.config = config or TelemetryConfig()
        self.sink = sink or NoopSink()

    @property
    def active(self) -> bool:
        return self.config.active

    def emit(self, event: TelemetryEvent) -> bool:
        """Emit an event only when explicitly enabled. Returns whether it did."""
        if not self.active:
            return False
        if not isinstance(event, TelemetryEvent):
            raise TypeError("event must be a TelemetryEvent")
        self.sink.emit(event.to_dict())
        return True
