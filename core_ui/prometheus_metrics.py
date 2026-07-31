"""Prometheus metrics owned by the Operator Chat execution plane.

These are point-in-time gauges read from the durable dispatch table rather than
in-process counters, so every backend and worker instance reports the same
numbers and a restart does not reset them.
"""

from django.utils import timezone

from core_ui.models.chat import OperatorTurnDispatch


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

    return [
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
