"""
Shared Studio view helpers.
"""

import json

from django.contrib.auth.models import User
from django.http import JsonResponse

from core_ui.access import feature_allowed_for_user
from studio.readiness_issues import runtime_limit_issue, validation_issues
from studio.skill_authoring import parse_csv_items

STUDIO_FEATURE_PIPELINES = "studio_pipelines"
STUDIO_FEATURE_AGENTS = "studio_agents"
STUDIO_FEATURE_SKILLS = "studio_skills"
STUDIO_FEATURE_MCP = "studio_mcp"


def _json_body(request) -> dict:
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _err(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": msg}, status=status)


def _ok(data, status: int = 200) -> JsonResponse:
    return JsonResponse(data, safe=False, status=status)


def _validation_err(errors: list[str], *, prefix: str = "Validation failed", issues: list[dict] | None = None) -> JsonResponse:
    message = f"{prefix}: {'; '.join(errors)}"
    return JsonResponse({"error": message, "details": errors, "issues": issues or validation_issues(errors)}, status=400)


def _limit_err(limit_error: dict) -> JsonResponse:
    payload = dict(limit_error)
    payload["issues"] = [runtime_limit_issue(payload)]
    return JsonResponse(payload, status=429)


def _require_admin(request, *, message: str = "Admin access required") -> JsonResponse | None:
    if getattr(request.user, "is_staff", False):
        return None
    return _err(message, 403)


def _is_admin(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False))


def _user_has_feature(user, feature: str) -> bool:
    return feature_allowed_for_user(user, feature)


def _owner_payload(owner: User | None) -> dict | None:
    if owner is None:
        return None
    return {"id": owner.id, "username": owner.username}


def _shared_user_payloads(shared_users) -> list[dict]:
    return [{"id": user.id, "username": user.username} for user in shared_users]


def _access_mode(*, owner_id: int | None, viewer) -> str:
    if _is_admin(viewer) and owner_id and owner_id != viewer.id:
        return "admin"
    if owner_id and viewer and owner_id == viewer.id:
        return "owner"
    return "shared"


def _apply_shared_users(instance, shared_user_ids: list[int]):
    if instance.owner_id:
        shared_user_ids = [user_id for user_id in shared_user_ids if user_id != instance.owner_id]
    users = User.objects.filter(id__in=shared_user_ids, is_active=True).order_by("username")
    instance.shared_with.set(users)


def _normalise_related_ids(raw_values) -> list[int]:
    if raw_values is None or not isinstance(raw_values, list):
        return []

    ids: list[int] = []
    for item in raw_values:
        value = item.get("id") if isinstance(item, dict) else item
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def _normalise_string_list(raw_values) -> list[str]:
    return parse_csv_items(raw_values)
