from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from kubernetes_ops.models import K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.permissions import kubernetes_permission_policy


class AdminSessionValidationError(ValueError):
    def __init__(self, message: str, *, code: str, status: int = 400, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.payload = payload or {}


DEFAULT_TTL_MINUTES = {
    K8sAdminSession.MODE_READ: 60,
    K8sAdminSession.MODE_WRITE: 30,
    K8sAdminSession.MODE_BREAK_GLASS: 15,
}
MAX_TTL_MINUTES = {
    K8sAdminSession.MODE_READ: 240,
    K8sAdminSession.MODE_WRITE: 60,
    K8sAdminSession.MODE_BREAK_GLASS: 30,
}
MODE_ALLOWED_VERBS = {
    K8sAdminSession.MODE_READ: ["get", "list", "watch", "logs", "yaml"],
    K8sAdminSession.MODE_WRITE: [
        "get",
        "list",
        "watch",
        "logs",
        "yaml",
        "dry_run_apply",
        "apply",
        "patch",
        "scale",
        "restart",
        "delete",
    ],
    K8sAdminSession.MODE_BREAK_GLASS: [
        "get",
        "list",
        "watch",
        "logs",
        "yaml",
        "exec",
        "port_forward",
        "cordon",
        "uncordon",
        "drain",
    ],
}
MODE_ALLOWED_KINDS = {
    K8sAdminSession.MODE_READ: ["*"],
    K8sAdminSession.MODE_WRITE: ["deployment", "statefulset", "daemonset", "job", "cronjob", "service", "ingress"],
    K8sAdminSession.MODE_BREAK_GLASS: ["pod", "node"],
}


def _clean_text(value: Any, *, max_length: int | None = None) -> str:
    result = str(value or "").strip()
    if max_length is not None:
        result = result[:max_length]
    return result


def _clean_string_list(value: Any, *, max_length: int = 120) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = _clean_text(item, max_length=max_length)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _ttl_minutes_for_mode(mode: str, value: Any) -> int:
    default = DEFAULT_TTL_MINUTES[mode]
    maximum = MAX_TTL_MINUTES[mode]
    if value in (None, ""):
        return default
    try:
        ttl = int(value)
    except (TypeError, ValueError) as exc:
        raise AdminSessionValidationError("ttl_minutes must be an integer.", code="ttl_invalid") from exc
    if ttl <= 0:
        raise AdminSessionValidationError("ttl_minutes must be positive.", code="ttl_invalid")
    return min(ttl, maximum)


def _allowed_verbs_for_mode(mode: str) -> list[str]:
    verbs = list(MODE_ALLOWED_VERBS[mode])
    if (
        mode == K8sAdminSession.MODE_BREAK_GLASS
        and bool(getattr(settings, "KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED", False))
        and "apply" not in verbs
    ):
        verbs.append("apply")
    return verbs


def _cluster_from_value(value: Any) -> K8sCluster | None:
    text = _clean_text(value)
    if not text:
        return None
    numeric = text.removeprefix("cluster_")
    query = Q(name=text) | Q(rancher_cluster_id=text) | Q(devtron_cluster_id=text)
    if numeric.isdigit():
        query |= Q(id=int(numeric))
    return K8sCluster.objects.filter(query).first()


def _provider_from_value(value: Any) -> K8sProvider | None:
    text = _clean_text(value)
    if not text:
        return None
    if text.isdigit():
        return K8sProvider.objects.filter(id=int(text)).first()
    return K8sProvider.objects.filter(Q(name=text) | Q(kind=text)).order_by("id").first()


def _require_mode_access(user, mode: str) -> dict[str, Any]:
    policy = kubernetes_permission_policy(user)
    if not policy["can_read"]:
        raise AdminSessionValidationError(
            "Kubernetes feature access is required.",
            code="kubernetes_feature_required",
            status=403,
        )
    if not policy["admin_mode_enabled"]:
        raise AdminSessionValidationError(
            "Kubernetes Admin Mode is disabled.",
            code="admin_mode_disabled",
            status=403,
        )
    if mode == K8sAdminSession.MODE_READ and not policy["can_admin_read"]:
        raise AdminSessionValidationError(
            "Kubernetes admin read access is required.",
            code="admin_read_required",
            status=403,
        )
    if mode == K8sAdminSession.MODE_WRITE and not policy["can_admin_write"]:
        raise AdminSessionValidationError(
            "Kubernetes admin write access is required.",
            code="admin_write_required",
            status=403,
        )
    if mode == K8sAdminSession.MODE_BREAK_GLASS and not policy["can_break_glass"]:
        raise AdminSessionValidationError(
            "Kubernetes break-glass access is required.",
            code="break_glass_required",
            status=403,
        )
    return policy


def _require_reason(mode: str, reason: str) -> None:
    if mode in {K8sAdminSession.MODE_WRITE, K8sAdminSession.MODE_BREAK_GLASS} and not reason:
        raise AdminSessionValidationError(
            "reason is required for write and break-glass admin sessions.",
            code="reason_required",
        )


def refresh_admin_session_state(session: K8sAdminSession, *, now=None) -> K8sAdminSession:
    current_time = now or timezone.now()
    expirable_statuses = {K8sAdminSession.STATUS_PENDING_APPROVAL, K8sAdminSession.STATUS_ACTIVE}
    if session.status in expirable_statuses and session.expires_at <= current_time:
        session.status = K8sAdminSession.STATUS_EXPIRED
        metadata = dict(session.metadata or {})
        metadata["expired_at"] = current_time.isoformat()
        session.metadata = metadata
        session.save(update_fields=["status", "metadata", "updated_at"])
    return session


def create_admin_session(*, user, data: dict[str, Any]) -> K8sAdminSession:
    mode = _clean_text(data.get("mode") or K8sAdminSession.MODE_READ)
    if mode not in dict(K8sAdminSession.MODE_CHOICES):
        raise AdminSessionValidationError("mode must be read, write, or break_glass.", code="mode_invalid")
    policy = _require_mode_access(user, mode)
    reason = _clean_text(data.get("reason"), max_length=2000)
    _require_reason(mode, reason)

    cluster = _cluster_from_value(data.get("cluster_id") or data.get("cluster"))
    if (data.get("cluster_id") or data.get("cluster")) and cluster is None:
        raise AdminSessionValidationError("Cluster not found.", code="cluster_not_found", status=404)
    provider = _provider_from_value(data.get("provider_id") or data.get("provider"))
    if (data.get("provider_id") or data.get("provider")) and provider is None:
        raise AdminSessionValidationError("Provider not found.", code="provider_not_found", status=404)

    namespace = _clean_text(data.get("namespace"), max_length=120)
    ttl_minutes = _ttl_minutes_for_mode(mode, data.get("ttl_minutes"))
    allowed_namespaces = _clean_string_list(data.get("allowed_namespaces"))
    if namespace and namespace not in allowed_namespaces:
        allowed_namespaces.insert(0, namespace)
    if not allowed_namespaces:
        allowed_namespaces = [namespace] if namespace else ["*"]
    allowed_kinds = _clean_string_list(data.get("allowed_kinds"), max_length=80) or MODE_ALLOWED_KINDS[mode]

    status = (
        K8sAdminSession.STATUS_ACTIVE if mode == K8sAdminSession.MODE_READ else K8sAdminSession.STATUS_PENDING_APPROVAL
    )
    risk_tier = {
        K8sAdminSession.MODE_READ: K8sAdminSession.RISK_LOW,
        K8sAdminSession.MODE_WRITE: K8sAdminSession.RISK_HIGH,
        K8sAdminSession.MODE_BREAK_GLASS: K8sAdminSession.RISK_CRITICAL,
    }[mode]

    metadata = {
        "created_policy": {
            "can_admin_read": policy["can_admin_read"],
            "can_admin_write": policy["can_admin_write"],
            "can_break_glass": policy["can_break_glass"],
        },
        "requested_ttl_minutes": ttl_minutes,
    }
    if mode == K8sAdminSession.MODE_BREAK_GLASS:
        metadata["post_review_required"] = True
        metadata["post_review_status"] = "pending"

    return K8sAdminSession.objects.create(
        user=user,
        username_snapshot=getattr(user, "username", ""),
        provider=provider,
        cluster=cluster,
        namespace=namespace,
        mode=mode,
        status=status,
        risk_tier=risk_tier,
        reason=reason,
        expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
        allowed_verbs=_allowed_verbs_for_mode(mode),
        allowed_kinds=allowed_kinds,
        allowed_namespaces=allowed_namespaces,
        metadata=metadata,
    )


def approve_admin_session(*, session: K8sAdminSession, user, data: dict[str, Any]) -> K8sAdminSession:
    session = refresh_admin_session_state(session)
    if session.status != K8sAdminSession.STATUS_PENDING_APPROVAL:
        raise AdminSessionValidationError(
            "Only pending admin sessions can be approved.",
            code="admin_session_not_pending",
            status=409,
        )
    if session.mode == K8sAdminSession.MODE_READ:
        raise AdminSessionValidationError(
            "Read admin sessions do not require approval.",
            code="read_session_approval_not_required",
            status=409,
        )
    if not getattr(user, "is_staff", False):
        raise AdminSessionValidationError("Staff approval is required.", code="staff_required", status=403)
    _require_mode_access(user, session.mode)

    approval_ref = _clean_text(data.get("approval_ref"), max_length=160)
    if not approval_ref:
        raise AdminSessionValidationError("approval_ref is required.", code="approval_ref_required")

    session.status = K8sAdminSession.STATUS_ACTIVE
    session.approval_ref = approval_ref
    session.approved_by = user
    session.approved_at = timezone.now()
    session.save(update_fields=["status", "approval_ref", "approved_by", "approved_at", "updated_at"])
    return session


def revoke_admin_session(*, session: K8sAdminSession, user, reason: str = "") -> K8sAdminSession:
    session = refresh_admin_session_state(session)
    can_revoke = session.user_id == getattr(user, "id", None) or getattr(user, "is_staff", False)
    if not can_revoke:
        raise AdminSessionValidationError("Admin session not found.", code="admin_session_not_found", status=404)
    if session.status not in {K8sAdminSession.STATUS_PENDING_APPROVAL, K8sAdminSession.STATUS_ACTIVE}:
        raise AdminSessionValidationError(
            "Only pending or active admin sessions can be revoked.",
            code="admin_session_not_open",
            status=409,
        )
    metadata = dict(session.metadata or {})
    metadata["revoked_by"] = getattr(user, "username", "")
    metadata["revoked_reason"] = _clean_text(reason, max_length=500)
    metadata["revoked_at"] = timezone.now().isoformat()
    session.status = K8sAdminSession.STATUS_REVOKED
    session.metadata = metadata
    session.save(update_fields=["status", "metadata", "updated_at"])
    return session


def close_admin_session(*, session: K8sAdminSession, user, reason: str = "") -> K8sAdminSession:
    session = refresh_admin_session_state(session)
    can_close = session.user_id == getattr(user, "id", None) or getattr(user, "is_staff", False)
    if not can_close:
        raise AdminSessionValidationError("Admin session not found.", code="admin_session_not_found", status=404)
    if session.status != K8sAdminSession.STATUS_ACTIVE:
        raise AdminSessionValidationError(
            "Only active admin sessions can be closed.",
            code="admin_session_not_active",
            status=409,
        )
    current_time = timezone.now()
    metadata = dict(session.metadata or {})
    metadata["closed_by"] = getattr(user, "username", "")
    metadata["closed_reason"] = _clean_text(reason, max_length=500)
    metadata["closed_at"] = current_time.isoformat()
    session.status = K8sAdminSession.STATUS_CLOSED
    session.closed_at = current_time
    session.metadata = metadata
    session.save(update_fields=["status", "closed_at", "metadata", "updated_at"])
    return session


def review_break_glass_session(*, session: K8sAdminSession, user, data: dict[str, Any]) -> K8sAdminSession:
    session = refresh_admin_session_state(session)
    if session.mode != K8sAdminSession.MODE_BREAK_GLASS:
        raise AdminSessionValidationError(
            "Post-review is only required for break-glass sessions.", code="post_review_not_required", status=409
        )
    if not getattr(user, "is_staff", False):
        raise AdminSessionValidationError("Staff review is required.", code="staff_required", status=403)
    _require_mode_access(user, K8sAdminSession.MODE_BREAK_GLASS)
    if session.status in {K8sAdminSession.STATUS_PENDING_APPROVAL, K8sAdminSession.STATUS_ACTIVE}:
        raise AdminSessionValidationError(
            "Break-glass session can be reviewed only after it is closed, revoked, or expired.",
            code="post_review_not_ready",
            status=409,
        )
    outcome = _clean_text(data.get("outcome"), max_length=80)
    if outcome not in {"accepted", "needs_followup", "incident_created"}:
        raise AdminSessionValidationError(
            "outcome must be accepted, needs_followup, or incident_created.", code="post_review_outcome_invalid"
        )
    summary = _clean_text(data.get("summary") or data.get("notes"), max_length=2000)
    if not summary:
        raise AdminSessionValidationError(
            "summary is required for break-glass post-review.", code="post_review_summary_required"
        )
    current_time = timezone.now()
    metadata = dict(session.metadata or {})
    metadata["post_review_required"] = False
    metadata["post_review_status"] = "completed"
    metadata["post_review"] = {
        "outcome": outcome,
        "summary": summary,
        "evidence_ref": _clean_text(data.get("evidence_ref"), max_length=240),
        "reviewed_by": getattr(user, "username", ""),
        "reviewed_at": current_time.isoformat(),
    }
    session.metadata = metadata
    session.save(update_fields=["metadata", "updated_at"])
    return session


def visible_admin_sessions_for_user(user, *, include_all: bool = False):
    queryset = K8sAdminSession.objects.select_related("user", "approved_by", "provider", "cluster")
    if include_all and getattr(user, "is_staff", False):
        return queryset
    return queryset.filter(user=user)
