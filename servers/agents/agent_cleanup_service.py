from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from app.runtime_limits import ACTIVE_AGENT_RUN_STATUSES
from servers.agents.agent_dispatch import cancel_agent_dispatches_for_run
from servers.agents.agent_run_report import refresh_agent_run_report_payload
from servers.agents.agent_runtime_overview import _age_seconds, _agent_run_stale_seconds_setting
from servers.models import AgentRun
from servers.run_events import record_run_event


def cleanup_stale_agent_runs_for_user(user, *, limit: int = 100) -> dict:
    stale_seconds = _agent_run_stale_seconds_setting()
    current_time = timezone.now()
    if stale_seconds <= 0:
        return {
            "stale_seconds": stale_seconds,
            "scanned": 0,
            "cleaned": 0,
            "canceled_dispatches": 0,
            "runs": [],
            "generated_at": current_time.isoformat(),
        }

    cutoff = current_time - timedelta(seconds=stale_seconds)
    queryset = (
        AgentRun.objects.filter(
            Q(user=user) | Q(agent__user=user),
            status__in=ACTIVE_AGENT_RUN_STATUSES,
            completed_at__isnull=True,
            started_at__lt=cutoff,
        )
        .select_related("agent", "server")
        .order_by("started_at", "id")
    )
    runs = list(queryset[: max(1, min(int(limit or 100), 200))])
    items = []
    canceled_total = 0
    for run in runs:
        age_seconds = _age_seconds(current_time, run.started_at)
        message = (
            f"Agent run exceeded stale runtime threshold ({stale_seconds}s) and was marked failed by operator cleanup."
        )
        record_run_event(
            run.id,
            "agent_stale_cleanup",
            {
                "stale_seconds": stale_seconds,
                "age_seconds": age_seconds,
                "source": "http",
                "message": message,
                "severity": "warning",
            },
        )
        canceled = cancel_agent_dispatches_for_run(run.id, reason="operator_stale_cleanup")
        canceled_total += int(canceled or 0)
        run.status = AgentRun.STATUS_FAILED
        run.ai_analysis = message
        run.completed_at = current_time
        if run.started_at:
            run.duration_ms = max(0, int((current_time - run.started_at).total_seconds() * 1000))
        run.save(update_fields=["status", "ai_analysis", "completed_at", "duration_ms"])
        refresh_agent_run_report_payload(run)
        items.append(
            {
                "run_id": run.id,
                "agent_id": run.agent_id,
                "agent_name": run.agent.name if run.agent_id and run.agent else "Agent",
                "status": run.status,
                "age_seconds": age_seconds,
                "canceled_dispatches": int(canceled or 0),
            }
        )

    return {
        "stale_seconds": stale_seconds,
        "scanned": len(runs),
        "cleaned": len(items),
        "canceled_dispatches": canceled_total,
        "runs": items,
        "generated_at": current_time.isoformat(),
    }
