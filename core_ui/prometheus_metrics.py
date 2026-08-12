"""Prometheus metrics owned by the Operator Chat execution plane.

These are point-in-time gauges read from the durable dispatch table rather than
in-process counters, so every backend and worker instance reports the same
numbers and a restart does not reset them.
"""

import os
from collections import defaultdict

from django.db.models import Count, Q
from django.utils import timezone

from core_ui.models.ai_providers import (
    AIConnectionAuthFlow,
    AIProviderConnection,
    AIProviderInvocation,
    AIProviderLease,
)
from core_ui.models.chat import OperatorTurnDispatch
from servers.models_monitoring import BackgroundWorkerState


def _prometheus_label(value: object) -> str:
    return str(value or "unknown").replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _provider_error_class(error_code: object) -> str:
    """Return a bounded, privacy-safe class instead of exporting raw error text."""

    code = str(error_code or "").strip().lower()
    if "auth" in code or "credential" in code:
        return "auth"
    if "quota" in code or "limit" in code or "capacity" in code:
        return "quota"
    if "timeout" in code or "deadline" in code:
        return "timeout"
    if "lease" in code or "owner" in code or "fenc" in code:
        return "lease"
    if "cancel" in code:
        return "cancelled"
    return "provider"


def _ai_provider_prometheus_lines(now) -> list[str]:
    ai_enabled = str(os.getenv("AI_CLI_SUBSCRIPTIONS_ENABLED", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    lines = [
        "# HELP webterm_ai_cli_enabled Whether the isolated subscription CLI profile is enabled.",
        "# TYPE webterm_ai_cli_enabled gauge",
        f"webterm_ai_cli_enabled {1 if ai_enabled else 0}",
        "# HELP webterm_ai_provider_connections Provider connections grouped by target and status.",
        "# TYPE webterm_ai_provider_connections gauge",
    ]
    for row in (
        AIProviderConnection.objects.values("target_id", "status")
        .annotate(total=Count("id"))
        .order_by("target_id", "status")
    ):
        target = _prometheus_label(row["target_id"])
        status = _prometheus_label(row["status"])
        lines.append(f'webterm_ai_provider_connections{{target="{target}",status="{status}"}} {int(row["total"])}')

    lines.extend(
        [
            "# HELP webterm_ai_provider_invocations Durable provider invocations grouped by target and state.",
            "# TYPE webterm_ai_provider_invocations gauge",
        ]
    )
    for row in (
        AIProviderInvocation.objects.values("target_id", "status")
        .annotate(total=Count("id"))
        .order_by("target_id", "status")
    ):
        target = _prometheus_label(row["target_id"])
        status = _prometheus_label(row["status"])
        lines.append(f'webterm_ai_provider_invocations{{target="{target}",status="{status}"}} {int(row["total"])}')

    failed_by_class: dict[tuple[str, str], int] = defaultdict(int)
    for row in (
        AIProviderInvocation.objects.filter(status="failed")
        .values("target_id", "error_code")
        .annotate(total=Count("id"))
    ):
        key = (str(row["target_id"] or "unknown"), _provider_error_class(row["error_code"]))
        failed_by_class[key] += int(row["total"])
    lines.extend(
        [
            "# HELP webterm_ai_provider_failures Durable failed invocations by provider and bounded reason class.",
            "# TYPE webterm_ai_provider_failures gauge",
        ]
    )
    for (target, reason), total in sorted(failed_by_class.items()):
        target_label = _prometheus_label(target)
        reason_label = _prometheus_label(reason)
        lines.append(f'webterm_ai_provider_failures{{target="{target_label}",reason="{reason_label}"}} {total}')

    pending_auth = AIConnectionAuthFlow.objects.filter(status="pending")
    auth_backlog = pending_auth.count()
    auth_claimed = pending_auth.filter(
        claimed_at__isnull=False,
        lease_expires_at__gt=now,
    ).count()
    live_auth_workers = BackgroundWorkerState.objects.filter(
        worker_kind=BackgroundWorkerState.KIND_AI_PROVIDER_AUTH,
        status=BackgroundWorkerState.STATUS_RUNNING,
        heartbeat_at__isnull=False,
        lease_expires_at__gt=now,
    ).count()
    lines.extend(
        [
            "# HELP webterm_ai_auth_backlog Pending provider device-login jobs.",
            "# TYPE webterm_ai_auth_backlog gauge",
            f"webterm_ai_auth_backlog {auth_backlog}",
            "# HELP webterm_ai_auth_claimed Pending device-login jobs with a live worker lease.",
            "# TYPE webterm_ai_auth_claimed gauge",
            f"webterm_ai_auth_claimed {auth_claimed}",
            "# HELP webterm_ai_auth_workers Auth worker processes with a current heartbeat.",
            "# TYPE webterm_ai_auth_workers gauge",
            f"webterm_ai_auth_workers {live_auth_workers}",
            "# HELP webterm_ai_active_leases Provider execution leases that retain current ownership.",
            "# TYPE webterm_ai_active_leases gauge",
            f"webterm_ai_active_leases {AIProviderLease.objects.filter(status='active', expires_at__gt=now).count()}",
            "# HELP webterm_ai_stale_leases Active provider leases whose ownership deadline has passed.",
            "# TYPE webterm_ai_stale_leases gauge",
            f"webterm_ai_stale_leases {AIProviderLease.objects.filter(status='active', expires_at__lte=now).count()}",
        ]
    )

    lost_by_target: dict[str, int] = defaultdict(int)
    for row in (
        AIProviderLease.objects.filter(Q(status="expired") | Q(status="active", expires_at__lte=now))
        .values("connection__target_id")
        .annotate(total=Count("id"))
    ):
        lost_by_target[str(row["connection__target_id"] or "unknown")] += int(row["total"])
    lines.extend(
        [
            "# HELP webterm_ai_lease_losses Expired or stale provider leases by target.",
            "# TYPE webterm_ai_lease_losses gauge",
        ]
    )
    for target, total in sorted(lost_by_target.items()):
        target_label = _prometheus_label(target)
        lines.append(f'webterm_ai_lease_losses{{target="{target_label}"}} {total}')

    lines.extend(
        [
            "# HELP webterm_ai_quota_limited_connections Connections currently marked quota-limited.",
            "# TYPE webterm_ai_quota_limited_connections gauge",
        ]
    )
    for row in (
        AIProviderConnection.objects.filter(status="limited")
        .values("target_id")
        .annotate(total=Count("id"))
        .order_by("target_id")
    ):
        target = _prometheus_label(row["target_id"])
        lines.append(f'webterm_ai_quota_limited_connections{{target="{target}"}} {int(row["total"])}')
    return lines


def operator_prometheus_lines() -> list[str]:
    now = timezone.now()
    queued = OperatorTurnDispatch.objects.filter(status=OperatorTurnDispatch.STATUS_QUEUED)
    oldest = queued.order_by("queued_at").values_list("queued_at", flat=True).first()
    inflight = OperatorTurnDispatch.objects.filter(
        status=OperatorTurnDispatch.STATUS_CLAIMED,
        lease_expires_at__gt=now,
    ).count()
    stalled = OperatorTurnDispatch.objects.filter(
        status=OperatorTurnDispatch.STATUS_CLAIMED,
        lease_expires_at__lte=now,
    ).count()
    retrying = OperatorTurnDispatch.objects.filter(
        status__in=[OperatorTurnDispatch.STATUS_QUEUED, OperatorTurnDispatch.STATUS_CLAIMED],
        attempt_count__gt=1,
    ).count()
    failed = OperatorTurnDispatch.objects.filter(status=OperatorTurnDispatch.STATUS_FAILED).count()

    lines = [
        "# HELP webterm_operator_queue_depth Operator turns waiting for a worker.",
        "# TYPE webterm_operator_queue_depth gauge",
        f"webterm_operator_queue_depth {queued.count()}",
        "# HELP webterm_operator_queue_oldest_age_seconds Age of the oldest waiting operator turn.",
        "# TYPE webterm_operator_queue_oldest_age_seconds gauge",
        f"webterm_operator_queue_oldest_age_seconds {max((now - oldest).total_seconds(), 0.0) if oldest else 0.0:.6f}",
        "# HELP webterm_operator_inflight_dispatches Operator turns held by a worker with a live lease.",
        "# TYPE webterm_operator_inflight_dispatches gauge",
        f"webterm_operator_inflight_dispatches {inflight}",
        "# HELP webterm_operator_stalled_dispatches Claimed operator turns whose lease expired without a heartbeat.",
        "# TYPE webterm_operator_stalled_dispatches gauge",
        f"webterm_operator_stalled_dispatches {stalled}",
        "# HELP webterm_operator_retrying_dispatches Operator turns queued or claimed on a second or later attempt.",
        "# TYPE webterm_operator_retrying_dispatches gauge",
        f"webterm_operator_retrying_dispatches {retrying}",
        "# HELP webterm_operator_failed_dispatches Operator turns that exhausted their attempts.",
        "# TYPE webterm_operator_failed_dispatches gauge",
        f"webterm_operator_failed_dispatches {failed}",
    ]
    lines.extend(_ai_provider_prometheus_lines(now))
    return lines
