"""Safe, request-correlated responses for unexpected API failures."""

from __future__ import annotations

import json
from typing import Any

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404, JsonResponse
from django.urls import Resolver404, resolve

from core_ui.api_failure import (
    INTERNAL_ERROR_CODE,
    INTERNAL_ERROR_MESSAGE,
    internal_error_response,
    log_internal_api_exception,
    request_id_for,
)

__all__ = [
    "APIContractMiddleware",
    "APIErrorMiddleware",
    "INTERNAL_ERROR_CODE",
    "INTERNAL_ERROR_MESSAGE",
    "internal_error_response",
    "is_api_request",
    "log_internal_api_exception",
    "normalize_api_response",
    "request_id_for",
]


def is_api_request(request: Any) -> bool:
    path = str(getattr(request, "path", "") or "")
    return path.startswith("/api/") or path.startswith("/servers/api/") or "/api/" in path


class APIErrorMiddleware:
    """Convert uncaught API exceptions to the same non-disclosing contract."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if not is_api_request(request):
            return None
        if isinstance(exception, (Http404, PermissionDenied, SuspiciousOperation)):
            return None
        return internal_error_response(request, exception)


def _api_error_code(status: int) -> str:
    return {
        400: "invalid_request",
        401: "authentication_required",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        429: "rate_limited",
    }.get(int(status), INTERNAL_ERROR_CODE if int(status) >= 500 else "request_failed")


def _error_message(payload: dict[str, Any], status: int) -> tuple[str, Any | None]:
    raw = payload.get("error")
    if isinstance(raw, str) and raw.strip():
        return raw, None
    if isinstance(raw, dict):
        message = raw.get("message") or raw.get("detail")
        if isinstance(message, str) and message.strip():
            return message, raw
    for key in ("error_message", "message", "detail"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value, raw
    return f"HTTP {status}", raw


def _preserve_response_metadata(source, target):
    """Keep security/session cookies and non-entity headers when rebuilding JSON."""
    for key, value in source.items():
        if key.lower() not in {"content-type", "content-length"}:
            target[key] = value
    target.cookies.update(source.cookies)
    return target


def normalize_api_response(request, response):
    if not is_api_request(request) or getattr(response, "streaming", False):
        return response
    if str(getattr(request, "path", "") or "") == "/api/openapi.json":
        return response
    status = int(getattr(response, "status_code", 200) or 200)
    if 300 <= status < 400 and response.get("Location"):
        return _preserve_response_metadata(
            response,
            JsonResponse(
                {
                    "success": False,
                    "error": "Authentication required",
                    "code": "authentication_required",
                },
                status=401,
            ),
        )
    content_type = str(response.get("Content-Type") or "").lower()
    if "json" not in content_type:
        if status >= 400:
            message = {
                400: "Invalid request",
                401: "Authentication required",
                403: "Forbidden",
                404: "Not found",
                405: "Method not allowed",
                429: "Too many requests",
            }.get(status, INTERNAL_ERROR_MESSAGE if status >= 500 else f"HTTP {status}")
            return _preserve_response_metadata(
                response,
                JsonResponse(
                    {"success": False, "error": message, "code": _api_error_code(status)},
                    status=status,
                ),
            )
        return response
    try:
        payload = json.loads(response.content or b"null")
    except (TypeError, ValueError, UnicodeDecodeError):
        return response

    if status < 400:
        success = bool(payload.get("success", True)) if isinstance(payload, dict) else True
        if isinstance(payload, dict):
            original = dict(payload)
            payload.setdefault("success", success)
            payload.setdefault("code", "ok" if success else "request_failed")
            if success:
                payload.setdefault("data", original)
            else:
                message, details = _error_message(payload, status)
                payload["error"] = message
                if details is not None:
                    payload.setdefault("details", details)
        else:
            payload = {"success": True, "data": payload, "code": "ok"}
    else:
        original = dict(payload) if isinstance(payload, dict) else {"detail": payload}
        message, details = _error_message(original, status)
        payload = dict(original)
        payload["success"] = False
        payload["error"] = message
        if isinstance(details, dict):
            nested_code = details.get("code")
            if isinstance(nested_code, str) and nested_code.strip():
                payload.setdefault("code", nested_code.strip())
        payload.setdefault("code", _api_error_code(status))
        if details is not None:
            payload.setdefault("details", details)
    normalized = JsonResponse(payload, safe=isinstance(payload, dict), status=status)
    return _preserve_response_metadata(response, normalized)


class APIContractMiddleware:
    """Validate JSON mutations and attach the stable API response envelope."""

    MUTATION_METHODS = {"POST", "PUT", "PATCH"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        invalid = self._validate_request(request)
        response = invalid if invalid is not None else self.get_response(request)
        return normalize_api_response(request, response)

    def _validate_request(self, request):
        if not is_api_request(request) or request.method.upper() not in self.MUTATION_METHODS:
            return None
        content_type = str(getattr(request, "content_type", "") or "").lower()
        if "json" not in content_type:
            return None
        try:
            payload = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse(
                {
                    "success": False,
                    "error": "Request body must contain valid JSON",
                    "code": "invalid_json",
                    "details": [{"field": "$", "message": "Invalid JSON", "type": "json_invalid"}],
                },
                status=400,
            )
        try:
            view_name = resolve(request.path_info).view_name or ""
        except Resolver404:
            view_name = ""
        from core_ui.schemas import validate_mutation_payload

        validated, errors = validate_mutation_payload(view_name, payload)
        if errors:
            field = errors[0]["field"]
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Invalid field: {field}",
                    "code": "invalid_request",
                    "details": errors,
                },
                status=400,
            )
        request.validated_json = validated
        return None
