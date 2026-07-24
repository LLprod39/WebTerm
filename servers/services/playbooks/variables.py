"""Typed, bounded runtime variable handling without plaintext run persistence."""

from __future__ import annotations

import json
import re
from typing import Any

MAX_RUNTIME_VARIABLES = 100
MAX_RUNTIME_VARIABLE_BYTES = 64_000
MAX_VALUE_DEPTH = 8
SECRET_NAME_PATTERN = re.compile(r"(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|vault)", re.I)


class RuntimeVariableError(ValueError):
    pass


def _validate_value(value: Any, *, depth: int = 0) -> Any:
    if depth > MAX_VALUE_DEPTH:
        raise RuntimeVariableError("Runtime variable nesting is too deep")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_validate_value(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        return {str(key): _validate_value(item, depth=depth + 1) for key, item in value.items()}
    raise RuntimeVariableError("Runtime variable values must be valid JSON values")


def normalize_runtime_variables(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise RuntimeVariableError("extra_vars must be an object")
    if len(raw) > MAX_RUNTIME_VARIABLES:
        raise RuntimeVariableError(f"extra_vars cannot contain more than {MAX_RUNTIME_VARIABLES} items")
    result: dict[str, Any] = {}
    for raw_name, raw_value in raw.items():
        name = str(raw_name).strip()
        if not name or len(name) > 128:
            raise RuntimeVariableError("Runtime variable names must contain 1-128 characters")
        result[name] = _validate_value(raw_value)
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_RUNTIME_VARIABLE_BYTES:
        raise RuntimeVariableError("extra_vars payload is too large")
    return result


def variable_manifest(values: dict[str, Any], *, binding_profile=None) -> dict[str, Any]:
    managed_names = set((binding_profile.secret_references or {}).keys()) if binding_profile else set()
    secret_names = sorted(name for name in values if name in managed_names or SECRET_NAME_PATTERN.search(name))
    return {
        "names": sorted(values),
        "secret_names": secret_names,
        "managed_secret_names": sorted(managed_names),
        "binding_profile_id": binding_profile.id if binding_profile else None,
        "values_redacted": True,
    }
