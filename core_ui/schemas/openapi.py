"""Generate the published OpenAPI document from Django routes and Pydantic schemas."""

from __future__ import annotations

import inspect
import re
from collections.abc import Iterable
from typing import Any, Literal

from django.urls import URLPattern, URLResolver, get_resolver
from pydantic import BaseModel, ConfigDict

from core_ui.schemas.http import ROUTE_SCHEMAS, MutationSchema

OPENAPI_VERSION = "3.1.0"
DOCUMENT_VERSION = "0.1.0"
_CONVERTER_RE = re.compile(r"<(?:(?P<converter>[a-zA-Z_][\w]*):)?(?P<name>[a-zA-Z_][\w]*)>")
_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


class ApiSuccessResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: Literal[True] = True
    code: str = "ok"
    data: Any = None
    request_id: str | None = None


class ApiErrorDetail(BaseModel):
    field: str = "$"
    message: str
    type: str = "value_error"


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: Literal[False] = False
    error: str
    code: str
    details: list[ApiErrorDetail] | dict[str, Any] | None = None
    fields: dict[str, list[str]] | None = None
    request_id: str | None = None


class ReadinessComponent(BaseModel):
    required: bool
    status: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    timestamp: str
    services: dict[str, str]
    components: dict[str, ReadinessComponent]


def _iter_patterns(
    patterns: Iterable[URLPattern | URLResolver],
    *,
    prefix: str = "",
    namespaces: tuple[str, ...] = (),
):
    for pattern in patterns:
        route = f"{prefix}{pattern.pattern}"
        if isinstance(pattern, URLResolver):
            next_namespaces = namespaces + ((pattern.namespace,) if pattern.namespace else ())
            yield from _iter_patterns(pattern.url_patterns, prefix=route, namespaces=next_namespaces)
            continue
        name = str(pattern.name or getattr(pattern.callback, "__name__", "endpoint"))
        view_name = ":".join((*namespaces, name)) if namespaces else name
        yield route, view_name, pattern.callback


def _openapi_path(route: str) -> tuple[str, list[dict[str, Any]]] | None:
    if route.startswith("^") or "(?P<" in route:
        return None
    parameters: list[dict[str, Any]] = []

    def replace(match: re.Match[str]) -> str:
        converter = match.group("converter") or "str"
        name = match.group("name")
        schema: dict[str, Any] = {"type": "string"}
        if converter == "int":
            schema = {"type": "integer", "minimum": 0}
        elif converter == "uuid":
            schema = {"type": "string", "format": "uuid"}
        parameters.append({"name": name, "in": "path", "required": True, "schema": schema})
        return f"{{{name}}}"

    path = "/" + _CONVERTER_RE.sub(replace, route).lstrip("/")
    path = path.replace("\\Z", "").rstrip("$")
    if not (path.startswith("/api/") or path.startswith("/servers/api/")):
        return None
    return path, parameters


def _declared_http_methods(callback) -> set[str]:
    methods: set[str] = set()
    current = callback
    original = callback
    while current is not None:
        original = current
        try:
            nonlocals = inspect.getclosurevars(current).nonlocals
        except (TypeError, ValueError):
            nonlocals = {}
        declared = nonlocals.get("request_method_list")
        if isinstance(declared, (list, tuple, set)):
            methods.update(str(value).upper() for value in declared if str(value).upper() in _HTTP_METHODS)
        current = getattr(current, "__wrapped__", None)
    if methods:
        return methods
    try:
        source = inspect.getsource(original)
    except (OSError, TypeError):
        source = ""
    for block in re.findall(r"require_http_methods\s*\(\s*\[([^]]+)]", source):
        methods.update(re.findall(r"['\"](GET|POST|PUT|PATCH|DELETE)['\"]", block))
    methods.update(re.findall(r"request\.method\s*==\s*['\"](GET|POST|PUT|PATCH|DELETE)['\"]", source))
    for block in re.findall(r"request\.method\s+in\s+\(([^)]+)\)", source):
        methods.update(re.findall(r"['\"](GET|POST|PUT|PATCH|DELETE)['\"]", block))
    return methods or {"GET"}


def _summary(callback, view_name: str) -> str:
    current = callback
    while getattr(current, "__wrapped__", None) is not None:
        current = current.__wrapped__
    doc = inspect.getdoc(current) or ""
    first_line = doc.splitlines()[0].strip() if doc else ""
    return first_line[:160] or view_name.replace(":", " ").replace("_", " ").title()


def _schema_components() -> dict[str, Any]:
    models: set[type[BaseModel]] = {
        MutationSchema,
        ApiSuccessResponse,
        ApiErrorDetail,
        ApiErrorResponse,
        ReadinessComponent,
        ReadinessResponse,
        *ROUTE_SCHEMAS.values(),
    }
    components: dict[str, Any] = {}
    for model in sorted(models, key=lambda item: item.__name__):
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        for name, definition in schema.pop("$defs", {}).items():
            components[name] = definition
        components[model.__name__] = schema
    return dict(sorted(components.items()))


def django_api_route_inventory() -> dict[str, set[str]]:
    inventory: dict[str, set[str]] = {}
    for route, _view_name, callback in _iter_patterns(get_resolver().url_patterns):
        converted = _openapi_path(route)
        if converted is None:
            continue
        path, _parameters = converted
        inventory.setdefault(path, set()).update(method.lower() for method in _declared_http_methods(callback))
    return inventory


def build_openapi_document() -> dict[str, Any]:
    paths: dict[str, dict[str, Any]] = {}
    operation_ids: set[str] = set()
    for route, view_name, callback in _iter_patterns(get_resolver().url_patterns):
        converted = _openapi_path(route)
        if converted is None:
            continue
        path, parameters = converted
        request_model = ROUTE_SCHEMAS.get(view_name, MutationSchema)
        request_schema = request_model.model_json_schema()
        examples = request_schema.get("examples") or []
        for method in sorted(_declared_http_methods(callback)):
            lowered = method.lower()
            operation_id = re.sub(r"[^a-zA-Z0-9_]+", "_", f"{view_name}_{lowered}").strip("_")
            if operation_id in operation_ids:
                operation_id = f"{operation_id}_{len(operation_ids)}"
            operation_ids.add(operation_id)
            operation: dict[str, Any] = {
                "operationId": operation_id,
                "summary": _summary(callback, view_name),
                "tags": [path.split("/")[1] if path.startswith("/servers/") else path.split("/")[2]],
                "x-django-view-name": view_name,
                "responses": {
                    "200": {
                        "description": "Successful response",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/ApiSuccessResponse"}}
                        },
                    },
                    "400": {
                        "description": "Invalid request",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}}},
                    },
                    "401": {"$ref": "#/components/responses/AuthenticationRequired"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "500": {"$ref": "#/components/responses/InternalError"},
                },
            }
            current = callback
            while current is not None:
                for status, response in dict(getattr(current, "openapi_responses", {}) or {}).items():
                    if response is None:
                        operation["responses"].pop(str(status), None)
                    else:
                        operation["responses"][str(status)] = dict(response)
                current = getattr(current, "__wrapped__", None)
            if parameters:
                operation["parameters"] = parameters
            if method in {"POST", "PUT", "PATCH"}:
                media: dict[str, Any] = {"schema": {"$ref": f"#/components/schemas/{request_model.__name__}"}}
                if examples:
                    media["example"] = examples[0]
                operation["requestBody"] = {
                    "required": method in {"POST", "PUT"},
                    "content": {"application/json": media},
                }
            paths.setdefault(path, {})[lowered] = operation

    error_content = {"application/json": {"schema": {"$ref": "#/components/schemas/ApiErrorResponse"}}}
    document = {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "WebTerm HTTP API",
            "version": DOCUMENT_VERSION,
            "description": "Generated from the live Django route graph and Pydantic HTTP boundary models.",
        },
        "servers": [{"url": "/", "description": "Current WebTerm installation"}],
        "paths": dict(sorted(paths.items())),
        "components": {
            "schemas": _schema_components(),
            "securitySchemes": {
                "sessionCookie": {"type": "apiKey", "in": "cookie", "name": "sessionid"},
                "csrfToken": {"type": "apiKey", "in": "header", "name": "X-CSRFToken"},
            },
            "responses": {
                "AuthenticationRequired": {"description": "Authentication required", "content": error_content},
                "Forbidden": {"description": "Permission denied", "content": error_content},
                "InternalError": {"description": "Internal error", "content": error_content},
            },
        },
        "security": [{"sessionCookie": []}],
    }
    validate_openapi_routes(document)
    return document


def validate_openapi_routes(document: dict[str, Any]) -> None:
    inventory = django_api_route_inventory()
    known_methods = {value.lower() for value in _HTTP_METHODS}
    documented = {
        path: {method for method in operations if method in known_methods}
        for path, operations in (document.get("paths") or {}).items()
    }
    missing_paths = sorted(set(inventory) - set(documented))
    stale_paths = sorted(set(documented) - set(inventory))
    method_mismatches = {
        path: {"django": sorted(inventory[path]), "openapi": sorted(documented[path])}
        for path in sorted(set(inventory) & set(documented))
        if inventory[path] != documented[path]
    }
    if missing_paths or stale_paths or method_mismatches:
        raise ValueError(
            f"OpenAPI route mismatch: missing={missing_paths} stale={stale_paths} methods={method_mismatches}"
        )
