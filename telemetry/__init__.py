"""Optional, off-by-default telemetry skeleton.

This package is intentionally not imported by the application. It defines the
contracts and privacy helpers for a future feature; it does not collect, store
or transmit anything until explicitly wired behind an administrator opt-in.
"""

from .client import TelemetryClient
from .config import TelemetryConfig
from .events import TelemetryEvent
from .sinks import MemorySink, NoopSink, TelemetrySink

__all__ = [
    "TelemetryClient",
    "TelemetryConfig",
    "TelemetryEvent",
    "TelemetrySink",
    "NoopSink",
    "MemorySink",
]
