from __future__ import annotations

from typing import Any


def empty_object_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "additionalProperties": True}


def schema(properties: dict[str, Any] | None = None, *, required: tuple[str, ...] = ()) -> dict[str, Any]:
    item: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": True,
    }
    if required:
        item["required"] = list(required)
    return item


def str_schema(*, description: str = "", enum: tuple[str, ...] = (), default: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"type": "string"}
    if description:
        item["description"] = description
    if enum:
        item["enum"] = list(enum)
    if default is not None:
        item["default"] = default
    return item


def int_schema(
    *,
    description: str = "",
    minimum: int | None = None,
    maximum: int | None = None,
    default: int | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {"type": "integer"}
    if description:
        item["description"] = description
    if minimum is not None:
        item["minimum"] = minimum
    if maximum is not None:
        item["maximum"] = maximum
    if default is not None:
        item["default"] = default
    return item


def bool_schema(*, description: str = "", default: bool | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"type": "boolean"}
    if description:
        item["description"] = description
    if default is not None:
        item["default"] = default
    return item


def array_schema(items: dict[str, Any], *, description: str = "", default: list[Any] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"type": "array", "items": items}
    if description:
        item["description"] = description
    if default is not None:
        item["default"] = default
    return item


def object_schema(*, description: str = "") -> dict[str, Any]:
    item = empty_object_schema()
    if description:
        item["description"] = description
    return item
