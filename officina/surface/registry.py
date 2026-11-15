"""Static surface registry schema for phase 0B.

This module is not imported by AUTOSEG runtime, services, web handlers or GTK.
Loading is opt-in; it performs no routing, authorization or policy enforcement.
It reads one YAML file and verifies that referenced services/tests still exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import inspect
from pathlib import Path
import re
from typing import Optional

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "flavors/autoseg/config/surface_registry.yaml"
ID_PATTERN = re.compile(r"^[a-z_]+\.[a-z_]+$")
SERVICE_PATTERN = re.compile(r"^[a-z_]\w*(?:\.[a-z_]\w*){2,}$")
RISKS = frozenset({"normal", "financial", "destructive", "read"})
AFFORDANCES = frozenset({"absent", "disabled", "confirm"})
STATES = frozenset({"active", "known_gap", "implemented_not_deployed"})
WRITER_GUARDS = frozenset({"locked", "edge_only_gap"})


class RegistryError(ValueError):
    """Invalid registry YAML or a reference that cannot be validated."""


@dataclass(frozen=True)
class SourceMarker:
    file: str
    contains: str


@dataclass(frozen=True)
class SurfaceAction:
    id: str
    family: str
    risk: str
    affordance: str
    state: str
    service: str
    required_params: tuple[str, ...]
    capability: Optional[str]
    admin_only: bool
    object_action: Optional[str]
    web_markers: tuple[str, ...]
    api_markers: tuple[str, ...]
    negative_tests: tuple[str, ...]
    source_markers: tuple[SourceMarker, ...]
    negative_markers: tuple[SourceMarker, ...]
    variant: Optional[str]
    writer_guard: Optional[str]


@dataclass(frozen=True)
class SurfaceRegistry:
    version: int
    actions: tuple[SurfaceAction, ...]

    def by_id(self, action_id: str) -> SurfaceAction:
        for action in self.actions:
            if action.id == action_id:
                return action
        raise KeyError(action_id)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{label}: expected non-empty string")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RegistryError(f"{label}: expected list")
    return tuple(_text(item, label) for item in value)


def _relative_file(root: Path, value: str, label: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise RegistryError(f"{label}: must be a repository-relative path")
    candidate = (root / path).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise RegistryError(f"{label}: missing or outside repository: {value}")
    return candidate


def _markers(value: object, label: str, root: Path) -> tuple[SourceMarker, ...]:
    if not isinstance(value, list):
        raise RegistryError(f"{label}: expected list of file/contains markers")
    result = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"file", "contains"}:
            raise RegistryError(f"{label}: marker requires only file and contains")
        path = _text(item["file"], f"{label}.file")
        needle = _text(item["contains"], f"{label}.contains")
        _relative_file(root, path, f"{label}.file")
        result.append(SourceMarker(path, needle))
    return tuple(result)


def _service_function(dotted: str):
    module_name, separator, function_name = dotted.rpartition(".")
    if not separator or not SERVICE_PATTERN.fullmatch(dotted):
        raise RegistryError(f"invalid service dotted path: {dotted}")
    try:
        target = getattr(import_module(module_name), function_name)
    except (ImportError, AttributeError) as exc:
        raise RegistryError(f"service is not importable: {dotted}: {exc}") from exc
    if not callable(target):
        raise RegistryError(f"service is not callable: {dotted}")
    return target


def _parse_action(raw: object, root: Path) -> SurfaceAction:
    if not isinstance(raw, dict):
        raise RegistryError("action must be a YAML mapping")
    required = {
        "id", "family", "risk", "affordance", "state", "service",
        "required_params", "capability", "admin_only", "object_action",
        "web_markers", "api_markers", "negative_tests", "source_markers",
        "negative_markers", "writer_guard",
    }
    allowed = required | {"variant"}
    if set(raw) - allowed or required - set(raw):
        raise RegistryError(
            f"action fields mismatch: missing={sorted(required-set(raw))}; "
            f"unknown={sorted(set(raw)-allowed)}")
    action_id = _text(raw["id"], "id")
    if not ID_PATTERN.fullmatch(action_id):
        raise RegistryError(f"invalid id: {action_id}")
    family = _text(raw["family"], f"{action_id}.family")
    if family != action_id.split(".", 1)[0]:
        raise RegistryError(f"{action_id}: family must match id prefix")
    for name, options in (("risk", RISKS), ("affordance", AFFORDANCES),
                          ("state", STATES)):
        if not isinstance(raw[name], str) or raw[name] not in options:
            raise RegistryError(f"{action_id}: invalid {name}: {raw[name]}")
    capability = raw["capability"]
    if capability is not None:
        capability = _text(capability, f"{action_id}.capability")
    admin_only = raw["admin_only"]
    if type(admin_only) is not bool or (capability is None) != admin_only:
        raise RegistryError(f"{action_id}: set exactly one of capability or admin_only:true")
    parameters = _strings(raw["required_params"], f"{action_id}.required_params")
    if not parameters or "banco" not in parameters or len(set(parameters)) != len(parameters):
        raise RegistryError(f"{action_id}: required_params must include banco without duplicates")
    target = _service_function(_text(raw["service"], f"{action_id}.service"))
    signature = inspect.signature(target)
    if any(name not in signature.parameters for name in parameters):
        raise RegistryError(f"{action_id}: required_params do not match {raw['service']} {signature}")
    negative_tests = _strings(raw["negative_tests"], f"{action_id}.negative_tests")
    for filename in negative_tests:
        if not filename.startswith("tests/") or not filename.endswith(".py"):
            raise RegistryError(f"{action_id}: negative_tests must be tests/*.py")
        _relative_file(root, filename, f"{action_id}.negative_tests")
    source_markers = _markers(raw["source_markers"], f"{action_id}.source_markers", root)
    negative_markers = _markers(raw["negative_markers"], f"{action_id}.negative_markers", root)
    if any(marker.file not in negative_tests for marker in negative_markers):
        raise RegistryError(f"{action_id}: negative_markers must refer to negative_tests")
    if bool(negative_tests) != bool(negative_markers):
        raise RegistryError(f"{action_id}: every evidenced test needs an explicit negative marker")
    if not negative_tests and raw["state"] != "known_gap":
        raise RegistryError(f"{action_id}: untested action must have state known_gap")
    variant = raw.get("variant")
    if variant is not None and variant not in ("create", "edit"):
        raise RegistryError(f"{action_id}: invalid variant")
    guard = raw["writer_guard"]
    if guard is not None and guard not in WRITER_GUARDS:
        raise RegistryError(f"{action_id}: invalid writer_guard")
    if admin_only and guard is None:
        raise RegistryError(f"{action_id}: admin_only needs an explicit writer_guard state")
    if guard == "edge_only_gap" and raw["state"] != "known_gap":
        raise RegistryError(f"{action_id}: missing writer guard cannot be active")
    if not admin_only and guard is not None:
        raise RegistryError(f"{action_id}: writer_guard is for admin-only actions")
    object_action = raw["object_action"]
    if object_action is not None:
        object_action = _text(object_action, f"{action_id}.object_action")
    return SurfaceAction(
        id=action_id,
        family=family,
        risk=raw["risk"],
        affordance=raw["affordance"],
        state=raw["state"],
        service=raw["service"],
        required_params=parameters,
        capability=capability,
        admin_only=admin_only,
        object_action=object_action,
        web_markers=_strings(raw["web_markers"], f"{action_id}.web_markers"),
        api_markers=_strings(raw["api_markers"], f"{action_id}.api_markers"),
        negative_tests=negative_tests,
        source_markers=source_markers,
        negative_markers=negative_markers,
        variant=variant,
        writer_guard=guard,
    )


def load_registry(path: str | Path | None = None, *, repo_root: str | Path | None = None) -> SurfaceRegistry:
    """Load/validate static YAML; does not install handlers or enforce access.

    An explicit ``repo_root`` supports validation of an isolated checkout.
    Service paths must resolve to real callables and include required arguments.
    """
    root = Path(repo_root).resolve() if repo_root is not None else ROOT
    yaml_path = Path(path) if path is not None else root / "flavors/autoseg/config/surface_registry.yaml"
    with yaml_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict) or set(raw) != {"version", "actions"}:
        raise RegistryError("registry must have version and actions only")
    if type(raw["version"]) is not int or raw["version"] != 1:
        raise RegistryError("unsupported registry version")
    if not isinstance(raw["actions"], list) or not raw["actions"]:
        raise RegistryError("actions must be a nonempty list")
    actions = tuple(_parse_action(row, root) for row in raw["actions"])
    ids = [row.id for row in actions]
    if len(set(ids)) != len(ids):
        raise RegistryError("duplicate surface action id")
    return SurfaceRegistry(version=1, actions=actions)
