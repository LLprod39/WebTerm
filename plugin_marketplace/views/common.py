from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, JsonResponse


def json_error(message: str, *, status: int = 400, code: str = "bad_request") -> JsonResponse:
    return JsonResponse({"success": False, "error": message, "code": code}, status=status)


def staff_required(request: HttpRequest) -> JsonResponse | None:
    if not getattr(request.user, "is_staff", False):
        return json_error("Admin access is required.", status=403, code="admin_required")
    return None


def parse_json_body(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    payload = json.loads(request.body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    return payload
