"""
Server agent configuration and launch endpoints.
"""

import contextlib
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from app.agent_kernel import skill_provider_registry
from app.sudo_policy import normalize_sudo_policy
from core_ui.activity import log_user_activity
from core_ui.decorators import require_feature
from core_ui.projects import active_project_for_user
from servers.agents import get_all_templates, get_template
from servers.agents.agent_inputs import normalize_input_artifacts, normalize_report_delivery
from servers.agents.agent_schedule import normalize_schedule_config, schedule_minutes_for_config
from servers.agents.agent_service import (
    cleanup_stale_agent_runs_for_user,
    dispatch_scheduled_agents_for_user,
    get_agent_runtime_overview,
    get_agent_worker_states,
    list_agents_for_user,
    list_scheduled_agents_for_user,
    start_agent_run_for_user,
)
from servers.models import ServerAgent
from servers.services.server_query import CAPABILITY_EXECUTE_COMMAND, resolve_servers_for_user_capability
from servers.views.server_helpers import _accessible_servers_queryset


@login_required
@require_feature("agents")
@require_http_methods(["GET"])
def agent_list(request):
    """List agents for the current user."""
    mode_filter = request.GET.get("mode")
    data = list_agents_for_user(request.user, mode_filter=mode_filter)
    return JsonResponse(
        {
            "success": True,
            "agents": data,
            "worker_states": get_agent_worker_states(),
            "runtime_overview": get_agent_runtime_overview(request.user),
        }
    )


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
    return JsonResponse({"success": True, **payload, "runtime_overview": get_agent_runtime_overview(request.user)})


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
@require_http_methods(["POST"])
def agent_runtime_cleanup_stale(request):
    """Mark stale active agent runs for the current user as failed and cancel dispatches."""
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    try:
        limit = max(1, min(int(data.get("limit", 100)), 200))
    except (TypeError, ValueError):
        limit = 100

    cleanup = cleanup_stale_agent_runs_for_user(request.user, limit=limit)
    log_user_activity(
        user=request.user,
        request=request,
        category="agent",
        action="runtime_cleanup_stale",
        entity_type="agent_runtime",
        entity_id=str(request.user.id),
        entity_name=f"user:{request.user.username}",
        metadata={"cleaned": cleanup.get("cleaned", 0), "canceled_dispatches": cleanup.get("canceled_dispatches", 0)},
    )
    return JsonResponse(
        {
            "success": True,
            "cleanup": cleanup,
            "runtime_overview": get_agent_runtime_overview(request.user),
        }
    )


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
    try:
        requested_schedule_minutes = int(data.get("schedule_minutes", 0) or 0)
    except (TypeError, ValueError):
        requested_schedule_minutes = 0
    schedule_config = normalize_schedule_config(
        data.get("schedule_config"), fallback_minutes=requested_schedule_minutes
    )
    schedule = schedule_minutes_for_config(schedule_config, requested_schedule_minutes)

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
    from servers.agents.agent_budgets import (
        FULL_DEFAULT_MAX_ITERATIONS,
        FULL_DEFAULT_SESSION_TIMEOUT_SEC,
        FULL_MAX_ITERATIONS_CAP,
        clamp_full_iterations,
    )

    try:
        raw_iterations = data.get("max_iterations", FULL_DEFAULT_MAX_ITERATIONS)
        max_iterations = clamp_full_iterations(
            int(raw_iterations if raw_iterations not in (None, "") else FULL_DEFAULT_MAX_ITERATIONS)
        )
    except (TypeError, ValueError):
        max_iterations = FULL_DEFAULT_MAX_ITERATIONS
    max_iterations = min(max_iterations, FULL_MAX_ITERATIONS_CAP)
    allow_multi_server = bool(data.get("allow_multi_server", False))
    tools_config = data.get("tools_config", {})
    sudo_policy = normalize_sudo_policy(data.get("sudo_policy"))
    stop_conditions = data.get("stop_conditions", [])
    try:
        raw_timeout = data.get("session_timeout_seconds", FULL_DEFAULT_SESSION_TIMEOUT_SEC)
        session_timeout = int(raw_timeout if raw_timeout not in (None, "") else FULL_DEFAULT_SESSION_TIMEOUT_SEC)
    except (TypeError, ValueError):
        session_timeout = FULL_DEFAULT_SESSION_TIMEOUT_SEC
    session_timeout = max(30, min(session_timeout, 3600))
    max_connections = min(int(data.get("max_connections", 5)), 10)
    skill_slugs = skill_provider_registry.sanitize_accessible_skill_slugs(
        request.user,
        skill_provider_registry.normalise_skill_slugs(
            data.get("skill_slugs") if "skill_slugs" in data else data.get("skills")
        ),
    )
    input_artifacts = normalize_input_artifacts(data.get("input_artifacts"))
    report_delivery = normalize_report_delivery(data.get("report_delivery"))

    if mode == "full" and tpl:
        if not goal:
            goal = tpl.get("goal", "")
        if not system_prompt:
            system_prompt = tpl.get("system_prompt", "")
        if not stop_conditions:
            stop_conditions = tpl.get("stop_conditions", [])

    execution_servers, denied_server_ids = resolve_servers_for_user_capability(
        server_ids,
        request.user,
        CAPABILITY_EXECUTE_COMMAND,
        base_queryset=_accessible_servers_queryset(request.user),
    )
    if denied_server_ids:
        return JsonResponse(
            {"success": False, "error": "Missing server capability: execute_command"},
            status=403,
        )

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
        sudo_policy=sudo_policy,
        stop_conditions=stop_conditions,
        session_timeout_seconds=session_timeout,
        max_connections=max_connections,
        schedule_minutes=schedule,
        schedule_config=schedule_config,
        skill_slugs=skill_slugs,
        input_artifacts=input_artifacts,
        report_delivery=report_delivery,
    )

    agent.servers.set(execution_servers)

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
    agent = ServerAgent.objects.filter(
        id=agent_id, user=request.user, project=active_project_for_user(request.user)
    ).first()
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
        "sudo_policy": str,
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
            if field == "sudo_policy":
                setattr(agent, field, normalize_sudo_policy(data[field]))
            else:
                setattr(agent, field, typ(data[field]) if typ is not list else data[field])

    for field, (lo, hi) in int_fields.items():
        if field in data:
            setattr(agent, field, max(lo, min(hi, int(data[field]))))

    if "schedule_config" in data:
        fallback_minutes = int(agent.schedule_minutes or 0)
        if "schedule_minutes" in data:
            with contextlib.suppress(TypeError, ValueError):
                fallback_minutes = int(data.get("schedule_minutes") or 0)
        schedule_config = normalize_schedule_config(data.get("schedule_config"), fallback_minutes=fallback_minutes)
        agent.schedule_config = schedule_config
        agent.schedule_minutes = schedule_minutes_for_config(schedule_config, fallback_minutes)
    elif "schedule_minutes" in data:
        minutes = int(agent.schedule_minutes or 0)
        agent.schedule_config = normalize_schedule_config(
            {"mode": "interval", "interval_minutes": minutes} if minutes > 0 else {"mode": "manual"},
            fallback_minutes=minutes,
        )

    if "skill_slugs" in data or "skills" in data:
        agent.skill_slugs = skill_provider_registry.sanitize_accessible_skill_slugs(
            request.user,
            skill_provider_registry.normalise_skill_slugs(
                data.get("skill_slugs") if "skill_slugs" in data else data.get("skills")
            ),
        )
    if "input_artifacts" in data:
        agent.input_artifacts = normalize_input_artifacts(data.get("input_artifacts"))
    if "report_delivery" in data:
        agent.report_delivery = normalize_report_delivery(data.get("report_delivery"))

    execution_servers = None
    if "server_ids" in data:
        execution_servers, denied_server_ids = resolve_servers_for_user_capability(
            data["server_ids"],
            request.user,
            CAPABILITY_EXECUTE_COMMAND,
            base_queryset=_accessible_servers_queryset(request.user),
        )
        if denied_server_ids:
            return JsonResponse(
                {"success": False, "error": "Missing server capability: execute_command"},
                status=403,
            )

    agent.save()
    if execution_servers is not None:
        agent.servers.set(execution_servers)
    return JsonResponse({"success": True})


@login_required
@require_feature("agents")
@require_http_methods(["POST"])
def agent_delete(request, agent_id):
    """Delete an agent."""
    agent = ServerAgent.objects.filter(
        id=agent_id, user=request.user, project=active_project_for_user(request.user)
    ).first()
    if not agent:
        return JsonResponse({"success": False, "error": "Agent not found"}, status=404)
    agent.delete()
    return JsonResponse({"success": True})


@login_required
@require_feature("agents")
@require_http_methods(["POST"])
def agent_run(request, agent_id):
    """Run agent on its configured servers (or a specific one)."""
    agent = (
        ServerAgent.objects.filter(id=agent_id, user=request.user, project=active_project_for_user(request.user))
        .prefetch_related("servers")
        .first()
    )
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
