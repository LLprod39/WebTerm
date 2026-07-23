from __future__ import annotations

from typing import Any

from kubernetes_ops.permissions import kubernetes_permission_policy


class SecretValueAccessError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.payload = payload or {}


def secret_values_allowed_for_user(user) -> bool:
    return bool(kubernetes_permission_policy(user).get("can_view_secret_values"))


def secret_values_visible_for_request(user, ref, requested: bool | str) -> bool:
    requested_bool = bool_value(requested)
    if not requested_bool:
        return False
    if str(getattr(ref, "kind", "")).lower() != "secret":
        return False
    if not str(getattr(ref, "name", "") or "").strip():
        raise SecretValueAccessError(
            "Secret values require a named Secret.", code="secret_read_requires_name", status=400
        )
    if not secret_values_allowed_for_user(user):
        raise SecretValueAccessError(
            "Secret value read access is required.",
            code="secret_read_required",
            status=403,
            payload={"requires": ["kubernetes_secret_read", "KUBERNETES_ADMIN_SECRET_READ_ENABLED"]},
        )
    return True


def secret_values_payload(requested: bool | str, visible: bool, *, mode: str = "named_secret") -> dict[str, Any]:
    return {
        "requested": bool_value(requested),
        "visible": bool(visible),
        "redacted_by_default": True,
        "mode": str(mode or "named_secret"),
    }


def bool_value(value: bool | str) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
