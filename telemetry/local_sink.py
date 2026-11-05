"""Local SQLite sink used by the feedback channel.

The general telemetry subsystem remains off by default. When the operator
explicitly enables ``AUTOSEG_TELEMETRY=local``, feedback events can be stored
in the same installation for correlation with support reports. The sink stores
only the already-validated, minimized payload produced by ``TelemetryEvent``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetria_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    session_id TEXT NOT NULL,
    page TEXT NOT NULL,
    authenticated INTEGER NOT NULL,
    actor_type TEXT NOT NULL,
    prestador_id INTEGER,
    feedback_id INTEGER,
    payload_json TEXT NOT NULL,
    criado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_telemetria_evento ON telemetria_eventos(event, id);
CREATE INDEX IF NOT EXISTS idx_telemetria_sessao ON telemetria_eventos(session_id, id);
CREATE INDEX IF NOT EXISTS idx_telemetria_feedback ON telemetria_eventos(feedback_id);
"""


def instalar(banco: str | Path) -> None:
    """Create the local telemetry table if it does not exist."""
    with sqlite3.connect(str(banco), timeout=20) as conexao:
        conexao.executescript(SCHEMA)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SQLiteSink:
    """Store validated telemetry events locally, with no external export."""

    def __init__(self, banco: str | Path):
        self.banco = str(banco)
        instalar(self.banco)

    def emit(self, payload: dict[str, Any]) -> None:
        atributos = dict(payload.get("attributes") or {})
        with sqlite3.connect(self.banco, timeout=20) as conexao:
            conexao.execute(
                """INSERT INTO telemetria_eventos(
                       event, occurred_at, session_id, page, authenticated,
                       actor_type, prestador_id, feedback_id, payload_json, criado_em)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(payload.get("event") or ""),
                    str(payload.get("occurred_at") or _agora()),
                    str(payload.get("session_id") or ""),
                    str(payload.get("page") or "/"),
                    1 if payload.get("authenticated") else 0,
                    str(payload.get("actor_type") or "anonymous"),
                    atributos.get("prestador_id"),
                    atributos.get("feedback_id"),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    _agora(),
                ),
            )
