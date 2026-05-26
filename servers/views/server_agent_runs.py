"""
Server agent run history, control, and task editing endpoints.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from servers.agent_dispatch import serialize_agent_dispatch
from servers.agent_service import (
    approve_agent_plan_for_user,
    reply_to_agent_run_for_user,
    stop_agent_run_for_user,
)
from servers.models import AgentRun, AgentRunEvent, ServerAgent
from servers.run_events import serialize_run_event
from servers.views.server_helpers import _accessible_servers_queryset


@login_required
@require_feature("agents")
@require_http_methods(["GET"])
def agent_runs(request, agent_id):
    """History of runs for an agent."""
    agent = ServerAgent.objects.filter(id=agent_id, user=request.user).first()
    if not agent:
        return JsonResponse({"success": False, "error": "Agent not found"}, status=404)

    limit = min(int(request.GET.get("limit", 20)), 100)
    runs = AgentRun.objects.filter(agent=agent).select_related("server").order_by("-started_at")[:limit]

    data = [
        {
            "id": run.id,
            "server_name": run.server.name if run.server_id else "?",
            "server_id": run.server_id,
            "status": run.status,
            "ai_analysis": run.ai_analysis,
            "commands_output": run.commands_output,
            "duration_ms": run.duration_ms,
            "started_at": run.started_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
        for run in runs
    ]

    return JsonResponse({"success": True, "runs": data})


@login_required
@require_feature("agents")
@require_http_methods(["GET"])
def agent_run_detail(request, run_id):
    """Single run detail (supports both mini and full agents)."""
    run = AgentRun.objects.filter(id=run_id, user=request.user).select_related("agent", "server").first()
    if not run:
        run = AgentRun.objects.filter(id=run_id, agent__user=request.user).select_related("agent", "server").first()
    if not run:
        return JsonResponse({"success": False, "error": "Run not found"}, status=404)

    data = {
        "id": run.id,
        "agent_id": run.agent_id,
        "agent_name": run.agent.name,
        "agent_type": run.agent.agent_type,
        "agent_mode": run.agent.mode,
        "server_name": run.server.name if run.server_id else "?",
        "status": run.status,
        "ai_analysis": run.ai_analysis,
        "commands_output": run.commands_output,
        "duration_ms": run.duration_ms,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "iterations_log": run.iterations_log or [],
        "tool_calls": run.tool_calls or [],
        "total_iterations": run.total_iterations,
        "connected_servers": run.connected_servers or [],
        "final_report": run.final_report,
        "pending_question": run.pending_question,
        "plan_tasks": run.plan_tasks or [],
        "orchestrator_log": run.orchestrator_log or [],
        "dispatch": serialize_agent_dispatch(run.dispatches.order_by("-queued_at", "-id").first()),
    }

    return JsonResponse({"success": True, "run": data})


@login_required
@require_feature("agents")
@require_http_methods(["POST"])
def agent_stop(request, agent_id):
    """Stop a running full agent."""
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    result = stop_agent_run_for_user(
        agent_id=agent_id,
        user=request.user,
        run_id=data.get("run_id"),
        source="http",
    )
    return JsonResponse(result["payload"], status=200 if result["ok"] else int(result["status"]))


@login_required
@require_feature("agents")
@require_http_methods(["POST"])
def agent_run_reply(request, run_id):
    """Reply to a question asked by a running agent."""
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    result = reply_to_agent_run_for_user(
        run_id=run_id,
        user=request.user,
        answer=data.get("answer", ""),
        source="http",
    )
    return JsonResponse(result["payload"], status=200 if result["ok"] else int(result["status"]))


@login_required
@require_feature("agents")
@require_http_methods(["GET"])
def agent_run_log(request, run_id):
    """Get the iterations log for a run."""
    run = AgentRun.objects.filter(id=run_id, agent__user=request.user).first()
    if not run:
        run = AgentRun.objects.filter(id=run_id, user=request.user).first()
    if not run:
        return JsonResponse({"success": False, "error": "Run not found"}, status=404)

    return JsonResponse(
        {
            "success": True,
            "iterations_log": run.iterations_log or [],
            "tool_calls": run.tool_calls or [],
            "total_iterations": run.total_iterations,
            "status": run.status,
            "pending_question": run.pending_question,
            "plan_tasks": run.plan_tasks or [],
        }
    )


@login_required
@require_feature("agents")
@require_http_methods(["GET"])
def agent_run_events(request, run_id):
    """Get the persistent event timeline for a run."""
    run = AgentRun.objects.filter(id=run_id, agent__user=request.user).first()
    if not run:
        run = AgentRun.objects.filter(id=run_id, user=request.user).first()
    if not run:
        return JsonResponse({"success": False, "error": "Run not found"}, status=404)

    try:
        limit = max(1, min(int(request.GET.get("limit", 200)), 500))
    except (TypeError, ValueError):
        limit = 200
    event_types = [item.strip() for item in request.GET.getlist("event_type") if item.strip()]
    if not event_types:
        event_type_raw = str(request.GET.get("event_type", "") or "").strip()
        if event_type_raw:
            event_types = [item.strip() for item in event_type_raw.split(",") if item.strip()]

    qs = AgentRunEvent.objects.filter(run=run).order_by("created_at", "id")
    if event_types:
        qs = qs.filter(event_type__in=event_types)
    total = qs.count()
    events = [serialize_run_event(item) for item in qs[:limit]]
    return JsonResponse(
        {
            "success": True,
            "events": events,
            "total": total,
        }
    )


@login_required
@require_feature("agents")
@require_http_methods(["POST"])
def agent_run_approve_plan(request, run_id):
    """Approve the plan and start executing the multi-agent pipeline."""
    result = approve_agent_plan_for_user(
        run_id=run_id,
        user=request.user,
        accessible_servers_queryset=_accessible_servers_queryset(request.user),
        source="http",
    )
    return JsonResponse(result["payload"], status=200 if result["ok"] else int(result["status"]))


@login_required
@require_feature("agents")
@require_http_methods(["POST"])
def agent_run_task_update(request, run_id, task_id):
    """Edit or delete a specific task in a pipeline run's plan_tasks."""
    run = AgentRun.objects.filter(
        id=run_id,
        agent__user=request.user,
    ).first()
    if not run:
        run = AgentRun.objects.filter(id=run_id, user=request.user).first()
    if not run:
        return JsonResponse({"success": False, "error": "Run not found"}, status=404)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    action = data.get("action", "update")
    tasks = list(run.plan_tasks or [])

    target = next((task for task in tasks if task.get("id") == task_id), None)
    if target is None:
        return JsonResponse({"success": False, "error": "Task not found"}, status=404)

    if target.get("status") not in ("pending", "failed", "skipped"):
        return JsonResponse({"success": False, "error": "Only pending/failed/skipped tasks can be edited"}, status=400)

    if action == "delete":
        tasks = [task for task in tasks if task.get("id") != task_id]
    else:
        if "name" in data:
            target["name"] = str(data["name"])[:200]
        if "description" in data:
            target["description"] = str(data["description"])[:1000]

    run.plan_tasks = tasks
    run.save(update_fields=["plan_tasks"])
    return JsonResponse({"success": True, "plan_tasks": tasks})


@login_required
@require_feature("agents")
@require_http_methods(["POST"])
def agent_run_task_ai_refine(request, run_id, task_id):
    """Use LLM to rewrite a task based on user instruction."""
    run = AgentRun.objects.filter(
        id=run_id,
        agent__user=request.user,
    ).first()
    if not run:
        run = AgentRun.objects.filter(id=run_id, user=request.user).first()
    if not run:
        return JsonResponse({"success": False, "error": "Run not found"}, status=404)

    tasks = list(run.plan_tasks or [])
    target = next((task for task in tasks if task.get("id") == task_id), None)
    if target is None:
        return JsonResponse({"success": False, "error": "Task not found"}, status=404)

    if target.get("status") not in ("pending", "failed", "skipped"):
        return JsonResponse({"success": False, "error": "Only pending/failed/skipped tasks can be edited"}, status=400)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    instruction = str(data.get("instruction", "")).strip()
    if not instruction:
        return JsonResponse({"success": False, "error": "instruction required"}, status=400)

    import asyncio
    import re as _re

    from app.core.llm import LLMProvider

    prompt = f"""Ты — ассистент, помогающий редактировать задачи в плане DevOps-агента.

Текущая задача:
Название: {target.get("name", "")}
Описание: {target.get("description", "")}

Инструкция пользователя: {instruction}

Верни ТОЛЬКО JSON-объект с полями name и description (без markdown, без пояснений):
{{"name": "...", "description": "..."}}"""

    async def _call():
        provider = LLMProvider()
        chunks = []
        async for chunk in provider.stream_chat(prompt, model="auto", purpose="chat"):
            chunks.append(chunk)
        return "".join(chunks)

    try:
        loop = asyncio.new_event_loop()
        result_text = loop.run_until_complete(_call())
        loop.close()
    except Exception as exc:
        return JsonResponse({"success": False, "error": f"LLM error: {exc}"}, status=500)

    text = _re.sub(r"```(?:json)?\s*", "", result_text).strip().rstrip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return JsonResponse(
            {"success": False, "error": "LLM did not return valid JSON", "raw": result_text[:500]}, status=500
        )

    try:
        refined = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Failed to parse LLM JSON", "raw": result_text[:500]}, status=500
        )

    if "name" in refined:
        target["name"] = str(refined["name"])[:200]
    if "description" in refined:
        target["description"] = str(refined["description"])[:1000]

    run.plan_tasks = tasks
    run.save(update_fields=["plan_tasks"])

    return JsonResponse({"success": True, "task": target, "plan_tasks": tasks})


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
    active_runs = list(
        AgentRun.objects.filter(agent__user=request.user, status__in=active_statuses)
        .select_related("agent", "server")
        .order_by("-started_at")[:10]
    )
    active_ids = {run.id for run in active_runs}
    recent_runs = list(
        AgentRun.objects.filter(agent__user=request.user)
        .exclude(id__in=active_ids)
        .select_related("agent", "server")
        .order_by("-started_at")[:10]
    )

    def _run_to_dict(run):
        return {
            "id": run.id,
            "agent_id": run.agent_id,
            "agent_name": run.agent.name,
            "agent_mode": run.agent.mode,
            "agent_type": run.agent.agent_type,
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

    return JsonResponse(
        {
            "success": True,
            "active": [_run_to_dict(run) for run in active_runs],
            "recent": [_run_to_dict(run) for run in recent_runs],
        }
    )
