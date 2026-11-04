"""No-op-by-default telemetry client.

This client is not imported by the portals or GTK app. A future feature flag
will decide whether to construct it and which sink to use.
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
