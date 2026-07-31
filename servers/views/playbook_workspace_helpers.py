"""Shared HTTP helpers for the revisioned playbook workspace API."""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from servers.services.playbooks.access import playbooks_visible_to, require_playbook_capability


def json_body(request) -> dict:
    try:
        payload = json.loads(request.body or "{}")
    except (TypeError, ValueError) as exc:
        raise ValueError("Request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    return payload


def workspace_error(
    *,
    code: str,
    message: str,
    status: int = 400,
    stage: str = "",
    field: str | None = None,
    retryable: bool = False,
    details: dict | None = None,
) -> JsonResponse:
    payload = {
        "success": False,
        "error": message,
        "code": code,
        "details": details or {},
        "retryable": retryable,
    }
    if stage:
        payload["stage"] = stage
    if field:
        payload["field"] = field
    return JsonResponse(payload, status=status)


def get_playbook_for_action(user, playbook_id: int, capability: str):
    playbook = get_object_or_404(playbooks_visible_to(user), id=playbook_id)
    require_playbook_capability(playbook, user, capability)
    return playbook
