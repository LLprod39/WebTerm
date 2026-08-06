from __future__ import annotations

import logging
from collections import Counter
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from opentelemetry.trace import SpanKind

from app.observability import capture_trace_context, start_span
from servers.models import AgentDispatchControl, AgentRun, AgentRunDispatch
from servers.run_events import record_run_event

logger = logging.getLogger(__name__)


class AgentDispatchLeaseLost(RuntimeError):
    """The worker no longer owns the claimed dispatch attempt."""


def _refresh_run_report_payload(run_id: int) -> None:
    try:
        from servers.agents.agent_run_report import refresh_agent_run_report_payload

        run = AgentRun.objects.select_related("agent", "server").filter(pk=run_id).first()
        if run is not None:
            refresh_agent_run_report_payload(run)
    except Exception as exc:
        logger.debug("Agent dispatch report refresh failed for run %s: %s", run_id, exc)


def enqueue_agent_run_dispatch(
    *,
    run: AgentRun,
    agent_id: int,
    user_id: int,
    server_ids: list[int],
    plan_only: bool,
    dispatch_kind: str = AgentRunDispatch.KIND_LAUNCH,
    metadata: dict[str, Any] | None = None,
) -> AgentRunDispatch:
    dispatch_metadata = dict(metadata or {})
    payload = {
        "server_ids": [int(server_id) for server_id in server_ids],
        "plan_only": bool(plan_only),
        "dispatch_kind": dispatch_kind,
        "status": AgentRunDispatch.STATUS_QUEUED,
        "metadata": dispatch_metadata,
        "claimed_at": None,
        "heartbeat_at": None,
        "lease_expires_at": None,
        "completed_at": None,
        "claimed_by": "",
        "error": "",
    }
    with start_span(
        "agent.dispatch.enqueue",
        kind=SpanKind.PRODUCER,
        attributes={
            "agent.run.id": run.id,
            "agent.id": agent_id,
            "dispatch.kind": dispatch_kind,
        },
    ) as span:
        trace_context = capture_trace_context()
        if trace_context:
            dispatch_metadata["otel_context"] = trace_context
        dispatch = AgentRunDispatch.objects.create(
            run=run,
            agent_id=agent_id,
            user_id=user_id,
            **payload,
        )
        span.set_attribute("agent.dispatch.id", dispatch.id)
        record_run_event(
            run.id,
            "agent_dispatch_enqueued",
            {
                "dispatch_id": dispatch.id,
                "dispatch_kind": dispatch_kind,
                "plan_only": bool(plan_only),
                "server_ids": list(server_ids),
                "message": f"Queued for {dispatch_kind.replace('_', ' ')} worker execution",
            },
        )
        _refresh_run_report_payload(run.id)
        return dispatch


def _fail_one_exhausted_dispatch(now) -> AgentRunDispatch | None:
    exhausted = (
        AgentRunDispatch.objects.select_for_update(skip_locked=True, of=("self",))
        .select_related("run")
        .filter(
            Q(status=AgentRunDispatch.STATUS_QUEUED)
            | Q(status=AgentRunDispatch.STATUS_CLAIMED, lease_expires_at__lte=now),
            attempt_count__gte=F("max_attempts"),
            run__status__in=[
                AgentRun.STATUS_PENDING,
                AgentRun.STATUS_RUNNING,
                AgentRun.STATUS_PLAN_REVIEW,
            ],
        )
        .order_by("queued_at", "id")
        .first()
    )
    if exhausted is None:
        return None
    error = f"Agent dispatch exhausted its {int(exhausted.max_attempts)} permitted attempts"
    exhausted.status = AgentRunDispatch.STATUS_FAILED
    exhausted.completed_at = now
    exhausted.lease_expires_at = now
    exhausted.error = error
    exhausted.save(update_fields=["status", "completed_at", "lease_expires_at", "error"])
    AgentRun.objects.filter(
        pk=exhausted.run_id,
        status__in=[AgentRun.STATUS_PENDING, AgentRun.STATUS_RUNNING, AgentRun.STATUS_PLAN_REVIEW],
    ).update(status=AgentRun.STATUS_FAILED, completed_at=now, ai_analysis=error)
    record_run_event(
        exhausted.run_id,
        "agent_dispatch_attempts_exhausted",
        {
            "dispatch_id": exhausted.id,
            "attempt_count": int(exhausted.attempt_count),
            "max_attempts": int(exhausted.max_attempts),
            "message": error,
        },
    )
    _refresh_run_report_payload(exhausted.run_id)
    return exhausted


def claim_next_agent_dispatch(
    *,
    worker_name: str,
    lease_seconds: int = 180,
    global_concurrency: int = 10,
    per_user_concurrency: int = 2,
) -> AgentRunDispatch | None:
    """Claim one dispatch under database-enforced global and per-user caps.

    The named control row serializes only the short capacity decision. Execution
    remains fully parallel across worker processes, while ``skip_locked`` and
    attempt fencing prevent duplicate ownership.
    """

    now = timezone.now()
    lease_delta = timedelta(seconds=max(int(lease_seconds), 30))
    global_limit = max(1, int(global_concurrency))
    user_limit = max(1, int(per_user_concurrency))
    claimed_dispatch: AgentRunDispatch | None = None
    with transaction.atomic():
        control, _created = AgentDispatchControl.objects.get_or_create(name="claim-capacity")
        AgentDispatchControl.objects.select_for_update().get(pk=control.pk)
        _fail_one_exhausted_dispatch(now)
        active_user_ids = list(
            AgentRunDispatch.objects.filter(
                status=AgentRunDispatch.STATUS_CLAIMED,
                lease_expires_at__gt=now,
            ).values_list("user_id", flat=True)
        )
        if len(active_user_ids) >= global_limit:
            return None

        claims_by_user = Counter(active_user_ids)
        blocked_user_ids = [user_id for user_id, count in claims_by_user.items() if count >= user_limit]
        candidate_queryset = (
            AgentRunDispatch.objects.select_for_update(skip_locked=True, of=("self",))
            .select_related("run", "agent", "user")
            .filter(
                Q(status=AgentRunDispatch.STATUS_QUEUED)
                | Q(status=AgentRunDispatch.STATUS_CLAIMED, lease_expires_at__lte=now),
                run__status__in=[
                    AgentRun.STATUS_PENDING,
                    AgentRun.STATUS_RUNNING,
                    AgentRun.STATUS_PLAN_REVIEW,
                ],
                attempt_count__lt=F("max_attempts"),
            )
        )
        if blocked_user_ids:
            candidate_queryset = candidate_queryset.exclude(user_id__in=blocked_user_ids)
        candidates = list(candidate_queryset.order_by("queued_at", "id")[:500])
        dispatch = min(
            candidates,
            key=lambda candidate: (claims_by_user[candidate.user_id], candidate.queued_at, candidate.id),
            default=None,
        )
        if dispatch is None:
            return None

        if (
            dispatch.status == AgentRunDispatch.STATUS_CLAIMED
            and dispatch.lease_expires_at
            and dispatch.lease_expires_at > now
        ):
            return None

        dispatch.status = AgentRunDispatch.STATUS_CLAIMED
        dispatch.claimed_at = now
        dispatch.heartbeat_at = now
        dispatch.lease_expires_at = now + lease_delta
        dispatch.claimed_by = worker_name[:120]
        dispatch.attempt_count = int(dispatch.attempt_count or 0) + 1
        dispatch.error = ""
        dispatch.save(
            update_fields=[
                "status",
                "claimed_at",
                "heartbeat_at",
                "lease_expires_at",
                "claimed_by",
                "attempt_count",
                "error",
            ]
        )

        claimed_dispatch = dispatch

    # Keep audit/report work outside the capacity lock so slow observers do not
    # serialize otherwise independent workers.
    if claimed_dispatch is not None:
        record_run_event(
            claimed_dispatch.run_id,
            "agent_dispatch_claimed",
            {
                "dispatch_id": claimed_dispatch.id,
                "dispatch_kind": claimed_dispatch.dispatch_kind,
                "worker_key": worker_name[:120],
                "attempt_count": int(claimed_dispatch.attempt_count or 0),
                "message": f"Dispatch claimed by worker {worker_name[:120]}",
            },
        )
        _refresh_run_report_payload(claimed_dispatch.run_id)
    return claimed_dispatch


def heartbeat_agent_dispatch(
    dispatch_id: int,
    *,
    worker_name: str,
    attempt_count: int,
    lease_seconds: int = 180,
) -> bool:
    now = timezone.now()
    updated = AgentRunDispatch.objects.filter(
        pk=dispatch_id,
        status=AgentRunDispatch.STATUS_CLAIMED,
        claimed_by=str(worker_name or "default")[:120],
        attempt_count=int(attempt_count),
        lease_expires_at__gt=now,
    ).update(
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=max(int(lease_seconds), 30)),
    )
    return bool(updated)


def complete_agent_dispatch(
    dispatch_id: int,
    *,
    worker_name: str,
    attempt_count: int,
    summary: dict[str, Any] | None = None,
) -> AgentRunDispatch | None:
    now = timezone.now()
    with transaction.atomic():
        dispatch = (
            AgentRunDispatch.objects.select_for_update()
            .select_related("run")
            .filter(
                pk=dispatch_id,
                status=AgentRunDispatch.STATUS_CLAIMED,
                claimed_by=str(worker_name or "default")[:120],
                attempt_count=int(attempt_count),
                lease_expires_at__gt=now,
            )
            .first()
        )
        if dispatch is None:
            return None
        dispatch.status = AgentRunDispatch.STATUS_COMPLETED
        dispatch.completed_at = now
        metadata = dict(dispatch.metadata or {})
        if summary:
            metadata["completion_summary"] = summary
        dispatch.metadata = metadata
        dispatch.save(update_fields=["status", "completed_at", "metadata"])
    record_run_event(
        dispatch.run_id,
        "agent_dispatch_completed",
        {
            "dispatch_id": dispatch.id,
            "dispatch_kind": dispatch.dispatch_kind,
            "message": f"Worker completed {dispatch.dispatch_kind.replace('_', ' ')} dispatch",
        },
    )
    _refresh_run_report_payload(dispatch.run_id)
    return dispatch


def fail_agent_dispatch(
    dispatch_id: int,
    *,
    worker_name: str,
    attempt_count: int,
    error: str,
) -> AgentRunDispatch | None:
    now = timezone.now()
    with transaction.atomic():
        dispatch = (
            AgentRunDispatch.objects.select_for_update()
            .select_related("run")
            .filter(
                pk=dispatch_id,
                status=AgentRunDispatch.STATUS_CLAIMED,
                claimed_by=str(worker_name or "default")[:120],
                attempt_count=int(attempt_count),
                lease_expires_at__gt=now,
            )
            .first()
        )
        if dispatch is None:
            return None
        dispatch.status = AgentRunDispatch.STATUS_FAILED
        dispatch.completed_at = now
        dispatch.error = str(error)[:4000]
        dispatch.save(update_fields=["status", "completed_at", "error"])
    record_run_event(
        dispatch.run_id,
        "agent_dispatch_failed",
        {
            "dispatch_id": dispatch.id,
            "dispatch_kind": dispatch.dispatch_kind,
            "error": dispatch.error,
            "message": f"Worker dispatch failed: {dispatch.error}",
        },
    )
    _refresh_run_report_payload(dispatch.run_id)
    return dispatch


def cancel_agent_dispatches_for_run(run_id: int, *, reason: str = "run_stopped") -> int:
    now = timezone.now()
    queued = AgentRunDispatch.objects.filter(
        run_id=run_id,
        status__in=[AgentRunDispatch.STATUS_QUEUED, AgentRunDispatch.STATUS_CLAIMED],
    )
    count = queued.count()
    if not count:
        return 0
    queued.update(
        status=AgentRunDispatch.STATUS_CANCELED,
        completed_at=now,
        error=reason[:4000],
    )
    record_run_event(
        run_id,
        "agent_dispatch_canceled",
        {
            "reason": reason,
            "message": f"Canceled queued dispatches: {reason}",
        },
    )
    _refresh_run_report_payload(run_id)
    return count


def serialize_agent_dispatch(dispatch: AgentRunDispatch | None) -> dict[str, Any] | None:
    if dispatch is None:
        return None
    return {
        "id": dispatch.id,
        "run_id": dispatch.run_id,
        "dispatch_kind": dispatch.dispatch_kind,
        "status": dispatch.status,
        "server_ids": list(dispatch.server_ids or []),
        "plan_only": bool(dispatch.plan_only),
        "queued_at": dispatch.queued_at.isoformat() if dispatch.queued_at else None,
        "claimed_at": dispatch.claimed_at.isoformat() if dispatch.claimed_at else None,
        "heartbeat_at": dispatch.heartbeat_at.isoformat() if dispatch.heartbeat_at else None,
        "lease_expires_at": dispatch.lease_expires_at.isoformat() if dispatch.lease_expires_at else None,
        "completed_at": dispatch.completed_at.isoformat() if dispatch.completed_at else None,
        "claimed_by": dispatch.claimed_by,
        "attempt_count": int(dispatch.attempt_count or 0),
        "max_attempts": int(dispatch.max_attempts or 0),
        "error": dispatch.error or "",
        "metadata": dispatch.metadata or {},
    }
