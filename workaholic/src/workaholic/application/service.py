"""Generic use cases. No AUTOSEG or arts dependencies."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from workaholic.domain.errors import ValidationError, NotFoundError, ConflictError
from workaholic.domain.schema import AppSchema
from workaholic.infrastructure.repositories import Repository

def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()

class RecordService:
    def __init__(self, schema: AppSchema, repository: Repository):
        self.schema = schema
        self.repo = repository

    def create(self, entity: str, fields: dict, *, state: str | None = None, record_id: str | None = None) -> dict:
        spec = self.schema.entity(entity)
        fields = self.schema.validate_fields(entity, fields)
        if spec.states:
            state = state or spec.states[0]
            if state not in spec.states:
                raise ValidationError(f"Estado inválido: {state}")
        elif state is not None:
            raise ValidationError("Entidade sem estados configurados")
        now = timestamp()
        rec = {"id": record_id or str(uuid4()), "entity": entity, "version": 1, "state": state,
               "fields": fields, "archived": False, "created_at": now, "updated_at": now}
        self.repo.put(entity, rec, None)
        return rec

    def get(self, entity: str, id: str) -> dict:
        self.schema.entity(entity)
        record = self.repo.get(entity, id)
        if record is None:
            raise NotFoundError(f"Registro não encontrado: {id}")
        return record

    def list(self, entity: str, *, include_archived: bool = False) -> list[dict]:
        self.schema.entity(entity)
        return [r for r in self.repo.list(entity) if include_archived or not r.get("archived")]

    def update(self, entity: str, id: str, changes: dict, *, expected_version: int) -> dict:
        rec = self.get(entity, id)
        if rec["version"] != expected_version:
            raise ConflictError("Versão desatualizada")
        self.schema.validate_fields(entity, changes, partial=True)
        fields = dict(rec["fields"])
        fields.update(changes)
        rec["fields"] = self.schema.validate_fields(entity, fields)
        self._persist(entity, rec)
        return rec

    def transition(self, entity: str, id: str, new_state: str, *, expected_version: int) -> dict:
        rec = self.get(entity, id)
        if rec["version"] != expected_version:
            raise ConflictError("Versão desatualizada")
        spec = self.schema.entity(entity)
        if new_state not in spec.transitions.get(rec["state"], ()):
            raise ValidationError(f"Transição não permitida: {rec['state']} -> {new_state}")
        rec["state"] = new_state
        self._persist(entity, rec)
        return rec

    def remove(self, entity: str, id: str, *, expected_version: int) -> dict | None:
        rec = self.get(entity, id)
        if rec["version"] != expected_version:
            raise ConflictError("Versão desatualizada")
        policy = self.schema.entity(entity).deletion
        if policy == "restrict":
            raise ValidationError(f"Exclusão proibida para {entity}")
        if self._incoming_links(entity, id):
            raise ValidationError("Registro referenciado por outro; remova os vínculos primeiro")
        if policy == "delete":
            self.repo.delete(entity, id, expected_version)
            return None
        rec["archived"] = True
        self._persist(entity, rec)
        return rec

    def _incoming_links(self, entity: str, id: str) -> bool:
        # Relations are represented by a configured 'link' field holding an ID or list of IDs.
        for rel in self.schema.relations.values():
            if rel["to"] != entity:
                continue
            for record in self.repo.list(rel["from"]):
                if record.get("archived"):
                    continue
                value = record["fields"].get(rel.get("field"))
                if value == id or (isinstance(value, list) and id in value):
                    return True
        return False

    def _persist(self, entity: str, rec: dict) -> None:
        prev = rec["version"]
        rec["version"] += 1
        rec["updated_at"] = timestamp()
        self.repo.put(entity, rec, prev)
