from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from servers.models import AgentRun


def _run_agent_name(run: AgentRun) -> str:
    return run.agent.name if run.agent_id and run.agent else "Agent"


def _run_agent_type(run: AgentRun) -> str:
    return run.agent.agent_type if run.agent_id and run.agent else ""


def _run_agent_mode(run: AgentRun) -> str:
    return run.agent.mode if run.agent_id and run.agent else ""


def _run_to_dict(run: AgentRun) -> dict:
    return {
        "id": run.id,
        "agent_id": run.agent_id,
        "agent_name": _run_agent_name(run),
        "agent_mode": _run_agent_mode(run),
        "agent_type": _run_agent_type(run),
        "server_name": run.server.name if run.server_id else "?",
        "server_id": run.server_id,
        "status": run.status,
        "total_iterations": run.total_iterations,
        "duration_ms": run.duration_ms,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "pending_question": run.pending_question or "",
        "connected_servers": run.connected_servers or [],
        "ai_analysis": (run.ai_analysis or "")[:500],
        "final_report": (run.final_report or "")[:2000],
        "commands_output": run.commands_output[:5] if run.commands_output else [],
    }


@login_required
@require_feature("agents")
@require_http_methods(["GET"])
def agent_dashboard_runs(request):
    """Active + recent runs for the dashboard widget."""
    active_statuses = [
        AgentRun.STATUS_PENDING,
        AgentRun.STATUS_RUNNING,
        AgentRun.STATUS_PAUSED,
        AgentRun.STATUS_WAITING,
        AgentRun.STATUS_PLAN_REVIEW,
    ]
    owned_runs = AgentRun.objects.filter(Q(user=request.user) | Q(agent__user=request.user)).distinct()
    active_runs = list(
        owned_runs.filter(status__in=active_statuses)
        .select_related("agent", "server")
        .order_by("-started_at")[:10]
    )
    active_ids = {run.id for run in active_runs}
    recent_runs = list(
        owned_runs
        .exclude(id__in=active_ids)
        .select_related("agent", "server")
        .order_by("-started_at")[:10]
    )
    return JsonResponse(
        {
            "success": True,
            "active": [_run_to_dict(run) for run in active_runs],
            "recent": [_run_to_dict(run) for run in recent_runs],
        }
    )
