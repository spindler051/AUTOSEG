"""Same repository contract for YAML and SQLite (portable JSON values)."""
from __future__ import annotations
from abc import ABC, abstractmethod
from copy import deepcopy
from pathlib import Path
import json
import os
import sqlite3
import tempfile
import yaml
from workaholic.domain.errors import ConflictError, NotFoundError

class Repository(ABC):
    @abstractmethod
    def get(self, entity: str, id: str) -> dict | None: ...
    @abstractmethod
    def list(self, entity: str) -> list[dict]: ...
    @abstractmethod
    def put(self, entity: str, record: dict, expected_version: int | None) -> None: ...
    @abstractmethod
    def delete(self, entity: str, id: str, expected_version: int) -> None: ...

class YamlRepository(Repository):
    """Single-process, atomic-file replacement; not suitable for concurrent writers."""
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        if not self.path.exists():
            return {"format_version": 1, "records": {}}
        with self.path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict) or data.get("format_version") != 1:
            raise ValueError("Formato YAML desconhecido")
        return data

    def _save(self, data: dict) -> None:
        fd, temp = tempfile.mkstemp(prefix=".workaholic-", suffix=".yaml", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def get(self, entity: str, id: str) -> dict | None:
        rec = self._load().get("records", {}).get(entity, {}).get(id)
        return deepcopy(rec) if rec is not None else None

    def list(self, entity: str) -> list[dict]:
        values = self._load().get("records", {}).get(entity, {}).values()
        return sorted((deepcopy(x) for x in values), key=lambda x: x["id"])

    def put(self, entity: str, record: dict, expected_version: int | None) -> None:
        data = self._load()
        section = data.setdefault("records", {}).setdefault(entity, {})
        existing = section.get(record["id"])
        if (existing is None and expected_version is not None) or (existing is not None and (expected_version is None or existing["version"] != expected_version)):
            raise ConflictError("Registro alterado ou já existente")
        section[record["id"]] = deepcopy(record)
        self._save(data)

    def delete(self, entity: str, id: str, expected_version: int) -> None:
        data = self._load()
        section = data.setdefault("records", {}).setdefault(entity, {})
        existing = section.get(id)
        if existing is None:
            raise NotFoundError(f"Registro não encontrado: {id}")
        if existing["version"] != expected_version:
            raise ConflictError("Registro alterado")
        del section[id]
        self._save(data)

class SQLiteRepository(Repository):
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS records (entity TEXT NOT NULL, id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (entity, id))")

    def _connect(self):
        con = sqlite3.connect(str(self.path), timeout=10)
        con.execute("PRAGMA busy_timeout=10000")
        return con

    def get(self, entity: str, id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute("SELECT payload FROM records WHERE entity=? AND id=?", (entity, id)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, entity: str) -> list[dict]:
        with self._connect() as con:
            rows = con.execute("SELECT payload FROM records WHERE entity=? ORDER BY id", (entity,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def put(self, entity: str, record: dict, expected_version: int | None) -> None:
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self._connect() as con:
            if expected_version is None:
                try:
                    con.execute("INSERT INTO records VALUES (?, ?, ?, ?)", (entity, record["id"], record["version"], payload))
                except sqlite3.IntegrityError:
                    raise ConflictError("Registro já existente") from None
            else:
                cur = con.execute("UPDATE records SET version=?, payload=? WHERE entity=? AND id=? AND version=?",
                                  (record["version"], payload, entity, record["id"], expected_version))
                if cur.rowcount != 1:
                    raise ConflictError("Registro alterado ou inexistente")

    def delete(self, entity: str, id: str, expected_version: int) -> None:
        with self._connect() as con:
            cur = con.execute("DELETE FROM records WHERE entity=? AND id=? AND version=?", (entity, id, expected_version))
            if cur.rowcount != 1:
                raise ConflictError("Registro alterado ou inexistente")
