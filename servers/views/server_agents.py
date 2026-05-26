"""
Server agent configuration and launch endpoints.
"""

import contextlib
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from core_ui.activity import log_user_activity
from core_ui.decorators import require_feature
from servers.agent_service import (
    dispatch_scheduled_agents_for_user,
    list_agents_for_user,
    list_scheduled_agents_for_user,
    start_agent_run_for_user,
)
from servers.agents import get_all_templates, get_template
from servers.models import ServerAgent
from servers.views.server_helpers import _accessible_servers_queryset


@login_required
@require_feature("agents")
@require_http_methods(["GET"])
def agent_list(request):
    """List agents for the current user."""
    mode_filter = request.GET.get("mode")
    data = list_agents_for_user(request.user, mode_filter=mode_filter)
    return JsonResponse({"success": True, "agents": data})


@login_required
@require_feature("agents")
@require_http_methods(["GET"])
def agent_schedule_overview(request):
    """List scheduled agents and their due state for the current user."""
    try:
        limit = max(1, min(int(request.GET.get("limit", 50)), 200))
    except (TypeError, ValueError):
        limit = 50

    payload = list_scheduled_agents_for_user(request.user, limit=limit)
    return JsonResponse({"success": True, **payload})


@login_required
@require_feature("agents")
@require_http_methods(["POST"])
def agent_schedule_dispatch(request):
    """Dispatch due scheduled agents for the current user."""
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    raw_agent_ids = data.get("agent_ids") or []
    agent_ids = []
    for value in raw_agent_ids:
        with contextlib.suppress(TypeError, ValueError):
            agent_ids.append(int(value))

    try:
        limit = max(1, min(int(data.get("limit", 100)), 500))
    except (TypeError, ValueError):
        limit = 100

    payload = dispatch_scheduled_agents_for_user(
        request.user,
        limit=limit,
        agent_ids=agent_ids or None,
    )
    log_user_activity(
        user=request.user,
        request=request,
        category="agent",
        action="schedule_dispatch",
        entity_type="agent_schedule",
        entity_id=str(request.user.id),
        entity_name=f"user:{request.user.username}",
    )
    return JsonResponse({"success": True, **payload})


@login_required
@require_feature("agents")
@require_http_methods(["GET"])
def agent_templates(request):
    """Return available agent templates."""
    return JsonResponse({"success": True, "templates": get_all_templates()})


@login_required
@require_feature("agents")
@require_http_methods(["POST"])
def agent_create(request):
    """Create a new agent (mini or full) from template or custom."""
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    mode = data.get("mode", "mini")
    agent_type = data.get("agent_type", "custom")
    name = data.get("name", "").strip()
    server_ids = data.get("server_ids", [])
    custom_commands = data.get("commands", [])
    ai_prompt = data.get("ai_prompt", "")
    schedule = int(data.get("schedule_minutes", 0))

    tpl = get_template(agent_type)
    if not name:
        name = tpl["name"] if tpl else "Custom Agent"

    if mode == "mini":
        commands = custom_commands if custom_commands else (tpl["commands"] if tpl else [])
        if not commands:
            return JsonResponse({"success": False, "error": "No commands specified"}, status=400)
        if not ai_prompt and tpl:
            ai_prompt = tpl.get("ai_prompt", "")
    else:
        commands = custom_commands or []
        if not ai_prompt and tpl:
            ai_prompt = tpl.get("ai_prompt", "")

    goal = data.get("goal", "")
    system_prompt = data.get("system_prompt", "")
    max_iterations = min(int(data.get("max_iterations", 20)), 100)
    allow_multi_server = bool(data.get("allow_multi_server", False))
    tools_config = data.get("tools_config", {})
    stop_conditions = data.get("stop_conditions", [])
    session_timeout = int(data.get("session_timeout_seconds", 600))
    max_connections = min(int(data.get("max_connections", 5)), 10)

    if mode == "full" and tpl:
        if not goal:
            goal = tpl.get("goal", "")
        if not system_prompt:
            system_prompt = tpl.get("system_prompt", "")
        if not stop_conditions:
            stop_conditions = tpl.get("stop_conditions", [])

    agent = ServerAgent.objects.create(
        user=request.user,
        name=name,
        mode=mode,
        agent_type=agent_type,
        commands=commands,
        ai_prompt=ai_prompt,
        goal=goal,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        allow_multi_server=allow_multi_server,
        tools_config=tools_config,
        stop_conditions=stop_conditions,
        session_timeout_seconds=session_timeout,
        max_connections=max_connections,
        schedule_minutes=schedule,
    )

    accessible = _accessible_servers_queryset(request.user).filter(id__in=server_ids)
    agent.servers.set(accessible)

    log_user_activity(
        user=request.user,
        request=request,
        category="agent",
        action="agent_create",
        entity_type="agent",
        entity_id=str(agent.id),
        entity_name=agent.name,
    )

    return JsonResponse({"success": True, "id": agent.id})


@login_required
@require_feature("agents")
@require_http_methods(["POST"])
def agent_update(request, agent_id):
    """Update agent configuration."""
    agent = ServerAgent.objects.filter(id=agent_id, user=request.user).first()
    if not agent:
        return JsonResponse({"success": False, "error": "Agent not found"}, status=404)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    simple_fields = {
        "name": str,
        "commands": list,
        "ai_prompt": str,
        "is_enabled": bool,
        "goal": str,
        "system_prompt": str,
        "allow_multi_server": bool,
        "tools_config": dict,
        "stop_conditions": list,
    }
    int_fields = {
        "schedule_minutes": (0, 10080),
        "max_iterations": (1, 100),
        "session_timeout_seconds": (30, 3600),
        "max_connections": (1, 10),
    }

    for field, typ in simple_fields.items():
        if field in data:
            setattr(agent, field, typ(data[field]) if typ is not list else data[field])

    for field, (lo, hi) in int_fields.items():
        if field in data:
            setattr(agent, field, max(lo, min(hi, int(data[field]))))

    if "server_ids" in data:
        accessible = _accessible_servers_queryset(request.user).filter(id__in=data["server_ids"])
        agent.servers.set(accessible)

    agent.save()
    return JsonResponse({"success": True})


@login_required
@require_feature("agents")
@require_http_methods(["POST"])
def agent_delete(request, agent_id):
    """Delete an agent."""
    agent = ServerAgent.objects.filter(id=agent_id, user=request.user).first()
    if not agent:
        return JsonResponse({"success": False, "error": "Agent not found"}, status=404)
    agent.delete()
    return JsonResponse({"success": True})


@login_required
@require_feature("agents")
@require_http_methods(["POST"])
def agent_run(request, agent_id):
    """Run agent on its configured servers (or a specific one)."""
    agent = ServerAgent.objects.filter(id=agent_id, user=request.user).prefetch_related("servers").first()
    if not agent:
        return JsonResponse({"success": False, "error": "Agent not found"}, status=404)

    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    launch_result = start_agent_run_for_user(
        agent=agent,
        user=request.user,
        accessible_servers_queryset=_accessible_servers_queryset(request.user),
        server_id=data.get("server_id"),
        source="http",
    )
    return JsonResponse(launch_result["payload"], status=200 if launch_result["ok"] else int(launch_result["status"]))
