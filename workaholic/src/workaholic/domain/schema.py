"""Declarative, profession-agnostic schemas. No dependency on GUI or persistence."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from workaholic.domain.errors import SchemaError, ValidationError

SUPPORTED_TYPES = {"string", "integer", "number", "boolean", "date", "list", "object"}

@dataclass(frozen=True)
class FieldSpec:
    type: str
    required: bool = False
    default: Any = None
    choices: tuple[Any, ...] = ()

@dataclass(frozen=True)
class EntitySpec:
    name: str
    fields: dict[str, FieldSpec]
    states: tuple[str, ...] = ()
    transitions: dict[str, tuple[str, ...]] = field(default_factory=dict)
    deletion: str = "archive"
    audit: bool = True

@dataclass(frozen=True)
class AppSchema:
    name: str
    entities: dict[str, EntitySpec]
    relations: dict[str, dict[str, str]] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "AppSchema":
        if not isinstance(data, dict) or not isinstance(data.get("entities"), dict):
            raise SchemaError("Configuração deve conter 'entities' como mapa.")
        result = {}
        for name, config in data["entities"].items():
            if not isinstance(config, dict):
                raise SchemaError(f"Entidade {name}: configuração inválida")
            fields = {}
            for key, fd in (config.get("fields") or {}).items():
                if isinstance(fd, str):
                    fd = {"type": fd}
                if not isinstance(fd, dict) or fd.get("type") not in SUPPORTED_TYPES:
                    raise SchemaError(f"Campo {name}.{key}: tipo inválido")
                fields[key] = FieldSpec(type=fd["type"], required=bool(fd.get("required", False)),
                                        default=fd.get("default"), choices=tuple(fd.get("choices") or ()))
            workflow = config.get("workflow") or {}
            states = tuple(workflow.get("states") or [])
            transitions = {str(k): tuple(v) for k, v in (workflow.get("transitions") or {}).items()}
            if any(s not in states for k, values in transitions.items() for s in (k, *values)):
                raise SchemaError(f"Entidade {name}: transição aponta para estado não declarado")
            deletion = config.get("deletion", "archive")
            if deletion not in {"archive", "delete", "restrict"}:
                raise SchemaError(f"Entidade {name}: política de exclusão inválida")
            result[name] = EntitySpec(name=name, fields=fields, states=states,
                                      transitions=transitions, deletion=deletion,
                                      audit=bool(config.get("audit", True)))
        relations = data.get("relations") or {}
        if not isinstance(relations, dict):
            raise SchemaError("'relations' deve ser um mapa")
        for relation_name, relation in relations.items():
            if not isinstance(relation, dict) or relation.get("from") not in result or relation.get("to") not in result:
                raise SchemaError(f"Relação {relation_name}: entidades inválidas")
        return AppSchema(name=str(data.get("name") or "application"), entities=result, relations=relations)

    def entity(self, name: str) -> EntitySpec:
        try:
            return self.entities[name]
        except KeyError:
            raise SchemaError(f"Entidade desconhecida: {name}") from None

    def validate_fields(self, entity: str, values: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
        spec = self.entity(entity)
        if not isinstance(values, dict):
            raise ValidationError("Os campos devem formar um objeto/mapa")
        unknown = set(values) - set(spec.fields)
        if unknown:
            raise ValidationError("Campos desconhecidos: " + ", ".join(sorted(unknown)))
        output = dict(values)
        if not partial:
            for key, f in spec.fields.items():
                if key not in output and f.default is not None:
                    output[key] = f.default
                if f.required and (key not in output or output[key] is None or output[key] == ""):
                    raise ValidationError(f"Campo obrigatório ausente: {key}")
        for key, value in output.items():
            f = spec.fields[key]
            if value is None:
                if f.required:
                    raise ValidationError(f"Campo obrigatório: {key}")
                continue
            checks = {
                "string": lambda x: isinstance(x, str),
                "integer": lambda x: isinstance(x, int) and not isinstance(x, bool),
                "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
                "boolean": lambda x: isinstance(x, bool),
                "date": lambda x: isinstance(x, str) and __import__("re").fullmatch(r"\d{4}-\d{2}-\d{2}", x) is not None,
                "list": lambda x: isinstance(x, list),
                "object": lambda x: isinstance(x, dict),
            }
            if not checks[f.type](value):
                raise ValidationError(f"Tipo inválido: {key} (esperado {f.type})")
            if f.choices and value not in f.choices:
                raise ValidationError(f"Valor não permitido: {key}")
        return output
