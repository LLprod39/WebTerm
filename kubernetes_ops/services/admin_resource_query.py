from __future__ import annotations

import urllib.parse
from typing import Any

MAX_LIST_ITEMS = 250


def append_query(path: str, params: dict[str, str]) -> str:
    clean_params = {key: value for key, value in params.items() if value not in ("", None)}
    if not clean_params:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{urllib.parse.urlencode(clean_params)}"


def list_query_options(
    *,
    label_selector: str,
    field_selector: str,
    search: str,
    limit: int | str | None,
    continue_token: str,
    include_managed_fields: bool | str,
) -> dict[str, Any]:
    bounded_limit = _bounded_int(limit, default=MAX_LIST_ITEMS, minimum=1, maximum=MAX_LIST_ITEMS)
    label = str(label_selector or "").strip()[:500]
    field = str(field_selector or "").strip()[:500]
    search_term = str(search or "").strip()[:200]
    token = str(continue_token or "").strip()[:500]
    include = _bool_value(include_managed_fields)
    provider_params: dict[str, str] = {}
    if limit not in (None, ""):
        provider_params["limit"] = str(bounded_limit)
    if label:
        provider_params["labelSelector"] = label
    if field:
        provider_params["fieldSelector"] = field
    if token:
        provider_params["continue"] = token
    return {
        "limit": bounded_limit,
        "search": search_term,
        "include_managed_fields": include,
        "provider_params": provider_params,
        "response": {
            "limit": bounded_limit,
            "label_selector_present": bool(label),
            "field_selector_present": bool(field),
            "search_present": bool(search_term),
            "continue_present": bool(token),
            "include_managed_fields": include,
        },
    }


def filter_resource_items_for_search(items: list[dict[str, Any]], search: str) -> list[dict[str, Any]]:
    needle = str(search or "").strip().lower()
    if not needle:
        return items
    return [item for item in items if needle in _search_blob(item)]


def response_continue_token(payload: Any) -> str:
    metadata = payload.get("metadata") if isinstance(payload, dict) else {}
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get("continue") or "")[:500]


def _bounded_int(value: int | str | None, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _bool_value(value: bool | str) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _search_blob(value: Any, *, depth: int = 0) -> str:
    if depth > 4:
        return ""
    if isinstance(value, dict):
        parts: list[str] = []
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if key == "managedFields":
                continue
            parts.append(key)
            parts.append(_search_blob(raw_value, depth=depth + 1))
        return " ".join(parts).lower()
    if isinstance(value, list):
        return " ".join(_search_blob(item, depth=depth + 1) for item in value[:50]).lower()
    if isinstance(value, (str, int, float, bool)):
        return str(value).lower()[:500]
    return ""
