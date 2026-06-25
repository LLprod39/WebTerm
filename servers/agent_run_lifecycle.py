from __future__ import annotations

from django.utils import timezone

from servers.models import AgentRun


def compute_run_duration_ms(run: AgentRun, *, completed_at=None) -> int:
    finished_at = completed_at or timezone.now()
    current_duration = max(0, int(getattr(run, "duration_ms", 0) or 0))
    started_at = getattr(run, "started_at", None)
    if not started_at:
        return current_duration

    elapsed_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
    return max(current_duration, elapsed_ms)


def mark_agent_run_stopped(run: AgentRun, *, completed_at=None) -> AgentRun:
    finished_at = completed_at or timezone.now()
    run.status = AgentRun.STATUS_STOPPED
    run.completed_at = finished_at
    run.duration_ms = compute_run_duration_ms(run, completed_at=finished_at)
    run.save(update_fields=["status", "completed_at", "duration_ms"])
    return run
