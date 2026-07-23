from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from kubernetes_ops.models import K8sAuditEvent

DEFAULT_AUDIT_RETENTION_DAYS = 365
MAX_AUDIT_RETENTION_DAYS = 3650


def configured_audit_retention_days(value: int | str | None = None) -> int:
    raw_value = (
        value
        if value is not None
        else getattr(settings, "KUBERNETES_OPS_AUDIT_RETENTION_DAYS", DEFAULT_AUDIT_RETENTION_DAYS)
    )
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = DEFAULT_AUDIT_RETENTION_DAYS
    return max(1, min(parsed, MAX_AUDIT_RETENTION_DAYS))


def audit_retention_inventory(*, retention_days: int | str | None = None) -> dict[str, Any]:
    days = configured_audit_retention_days(retention_days)
    cutoff = timezone.now() - timedelta(days=days)
    expired = K8sAuditEvent.objects.filter(created_at__lt=cutoff)
    recent = K8sAuditEvent.objects.filter(created_at__gte=cutoff)
    return {
        "retention_days": days,
        "cutoff": cutoff.isoformat(),
        "summary": {
            "expired_count": expired.count(),
            "retained_count": recent.count(),
            "total_count": K8sAuditEvent.objects.count(),
        },
        "expired_by_action": _counts_by_action(expired),
    }


def cleanup_kubernetes_audit_events(
    *,
    retention_days: int | str | None = None,
    dry_run: bool = True,
    batch_size: int = 1000,
) -> dict[str, Any]:
    days = configured_audit_retention_days(retention_days)
    cutoff = timezone.now() - timedelta(days=days)
    expired = K8sAuditEvent.objects.filter(created_at__lt=cutoff).order_by("id")
    expired_count = expired.count()
    expired_by_action = _counts_by_action(expired)
    deleted_count = 0

    if not dry_run and expired_count:
        size = max(1, min(int(batch_size or 1000), 5000))
        while True:
            ids = list(expired.values_list("id", flat=True)[:size])
            if not ids:
                break
            batch_deleted, _ = K8sAuditEvent.objects.filter(id__in=ids).delete()
            deleted_count += int(batch_deleted or 0)

    retained_count = K8sAuditEvent.objects.filter(created_at__gte=cutoff).count()
    return {
        "dry_run": dry_run,
        "retention_days": days,
        "cutoff": cutoff.isoformat(),
        "expired_count": expired_count,
        "deleted_count": deleted_count,
        "retained_count": retained_count,
        "expired_by_action": expired_by_action,
    }


def _counts_by_action(queryset) -> list[dict[str, Any]]:
    return [
        {"action": str(row["action"] or ""), "count": int(row["count"] or 0)}
        for row in queryset.values("action").annotate(count=Count("id")).order_by("action")
    ]
