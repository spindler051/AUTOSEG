"""Independent rollout switch for provider object-level enforcement.

Disabled by default. The unified-login feature flag is intentionally separate.
"""
from __future__ import annotations
import os

_TRUE_VALUES = frozenset(("1", "true", "on", "yes"))


def enforcement_enabled(banco=None) -> bool:
    return str(os.environ.get("AUTOSEG_OBJECT_POLICY_ENFORCEMENT", "0")).strip().lower() in _TRUE_VALUES
