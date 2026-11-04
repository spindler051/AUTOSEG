"""Telemetry configuration. Defaults are deliberately inert."""

from dataclasses import dataclass
from typing import Literal

Mode = Literal["off", "local", "otlp"]
IpMode = Literal["truncate", "hash"]


@dataclass(frozen=True)
class TelemetryConfig:
    """Configuration for the future telemetry subsystem.

    ``enabled=False`` and ``mode="off"`` are the only defaults allowed for a
    normal installation. Enabling local collection or OTLP export requires an
    explicit administrator action and a user-facing notice version.
    """

    enabled: bool = False
    mode: Mode = "off"
    collect_ip: bool = False
    ip_mode: IpMode = "truncate"
    ip_hash_key: str = ""
    collect_screen: bool = False
    collect_user_agent: bool = True
    retention_days: int = 30
    otlp_endpoint: str = ""
    notice_version: str = ""

    def __post_init__(self):
        if self.mode not in ("off", "local", "otlp"):
            raise ValueError("mode must be off, local or otlp")
        if self.ip_mode not in ("truncate", "hash"):
            raise ValueError("ip_mode must be truncate or hash")
        if not 1 <= int(self.retention_days) <= 365:
            raise ValueError("retention_days must be between 1 and 365")
        if self.mode == "otlp" and not self.otlp_endpoint.strip():
            raise ValueError("otlp_endpoint is required in otlp mode")
        if self.ip_mode == "hash" and not self.ip_hash_key:
            raise ValueError("ip_hash_key is required when ip_mode=hash")

    @property
    def active(self) -> bool:
        """True only when collection has been explicitly enabled."""
        return bool(self.enabled and self.mode != "off")
