"""Small, dependency-light boundary for safe internal API failures."""

from __future__ import annotations

import uuid
from typing import Any

from django.http import JsonResponse
from loguru import logger

from core_ui.audit import get_audit_context

INTERNAL_ERROR_CODE = "internal_error"
INTERNAL_ERROR_MESSAGE = "An internal error occurred. Please retry or contact support."


def request_id_for(request: Any | None) -> str:
    request_id = str(getattr(request, "request_id", "") or "").strip()
    if not request_id:
        request_id = str(get_audit_context().get("request_id") or "").strip()
    if not request_id:
        request_id = uuid.uuid4().hex
        if request is not None:
            request.request_id = request_id
    return request_id[:128]


def log_internal_api_exception(request: Any | None, exc: BaseException) -> str:
    request_id = request_id_for(request)
    user = getattr(request, "user", None)
    logger.bind(
        request_id=request_id,
        channel="http",
        user_id=str(getattr(user, "id", "") or "-"),
        path=str(getattr(request, "path", "") or get_audit_context().get("path") or "-"),
    ).opt(exception=exc).error("Internal API request failed")
    return request_id


def internal_error_response(
    request: Any | None,
    exc: BaseException,
    *,
    status: int = 500,
) -> JsonResponse:
    request_id = log_internal_api_exception(request, exc)
    response = JsonResponse(
        {
            "success": False,
            "error": INTERNAL_ERROR_MESSAGE,
            "code": INTERNAL_ERROR_CODE,
            "request_id": request_id,
        },
        status=max(500, int(status)),
    )
    response["X-Request-ID"] = request_id
    return response
