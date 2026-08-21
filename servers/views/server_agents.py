"""
Server agent configuration and launch endpoints.
"""

import contextlib
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from app.agent_kernel import skill_provider_registry
from app.ai_runtime import ExecutionMode
from app.sudo_policy import normalize_sudo_policy
from core_ui.activity import log_user_activity
from core_ui.ai_model_policy import user_can_manage_ai_routing
from core_ui.decorators import require_feature
from core_ui.services.ai_execution_context import active_project_for_execution, build_execution_context
from servers.agents import get_all_templates, get_template
from servers.agents.agent_inputs import normalize_input_artifacts, normalize_report_delivery
from servers.agents.agent_pilot_policy import (
    PILOT_MAX_ITERATIONS,
    PILOT_MAX_SESSION_TIMEOUT_SECONDS,
    pilot_agent_policy_violations,
    user_can_automate,
)
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
from servers.agents.agent_targeting import server_requirement_reasons
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
@require_feature("automation")
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
@require_feature("automation")
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
        FULL_MAX_ITERATIONS_CAP,
        clamp_full_iterations,
        resolve_agent_runtime_budget,
    )

    automation_allowed = user_can_automate(request.user, request=request)
    recommended_budget = resolve_agent_runtime_budget(
        mode=mode,
        goal=goal,
        system_prompt=system_prompt,
        commands=commands,
        skill_slugs=data.get("skill_slugs") or data.get("skills") or [],
        input_artifacts=data.get("input_artifacts") or [],
    )
    default_iterations = recommended_budget.max_iterations if automation_allowed else PILOT_MAX_ITERATIONS
    try:
        raw_iterations = data.get("max_iterations", default_iterations)
        max_iterations = clamp_full_iterations(
            int(raw_iterations if raw_iterations not in (None, "") else default_iterations)
        )
    except (TypeError, ValueError):
        max_iterations = default_iterations
    max_iterations = min(max_iterations, FULL_MAX_ITERATIONS_CAP)
    allow_multi_server = data.get("allow_multi_server", False)
    tools_config = data.get("tools_config", {})
    sudo_policy = normalize_sudo_policy(data.get("sudo_policy"))
    stop_conditions = data.get("stop_conditions", [])
    try:
        default_timeout = recommended_budget.session_timeout_seconds if automation_allowed else PILOT_MAX_SESSION_TIMEOUT_SECONDS
        raw_timeout = data.get("session_timeout_seconds", default_timeout)
        session_timeout = int(raw_timeout if raw_timeout not in (None, "") else default_timeout)
    except (TypeError, ValueError):
        session_timeout = default_timeout
    session_timeout = max(30, min(session_timeout, 3600))
    try:
        max_connections = min(int(data.get("max_connections", recommended_budget.max_connections if automation_allowed else 1)), 10)
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "error": "max_connections must be an integer"}, status=400)
    skill_slugs = skill_provider_registry.sanitize_accessible_skill_slugs(
        request.user,
        skill_provider_registry.normalise_skill_slugs(
            data.get("skill_slugs") if "skill_slugs" in data else data.get("skills")
        ),
    )
    input_artifacts = normalize_input_artifacts(data.get("input_artifacts"))
    report_delivery = normalize_report_delivery(data.get("report_delivery"))
    provider_binding = {}
    if user_can_manage_ai_routing(request.user) and data.get("provider_binding"):
        try:
            project = active_project_for_execution(request.user)
            context = build_execution_context(
                actor_user_id=request.user.pk,
                project_id=project.pk if project else None,
                purpose="ops",
                source_kind="server_agent",
                source_id="new",
                mode=ExecutionMode.UNATTENDED if schedule > 0 else ExecutionMode.INTERACTIVE,
                explicit_binding=data.get("provider_binding"),
            )
            provider_binding = context.binding.to_dict()
        except (TypeError, ValueError, RuntimeError) as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=400)

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
    execution_project_ids = {server.project_id for server in execution_servers}
    if len(execution_project_ids) > 1:
        return JsonResponse(
            {"success": False, "error": "Selected servers cannot be combined in one agent"},
            status=400,
        )
    server_reasons = server_requirement_reasons(
        mode=mode,
        commands=commands,
        tools_config=tools_config,
        sudo_policy=sudo_policy,
        skill_slugs=skill_slugs,
    )
    if not execution_servers and server_reasons:
        return JsonResponse(
            {"success": False, "error": "Selected commands or capabilities require a server", "code": "server_scope_required", "reasons": server_reasons},
            status=400,
        )

    violations = pilot_agent_policy_violations(
        user=request.user,
        servers=execution_servers,
        tools_config=tools_config,
        sudo_policy=sudo_policy,
        schedule_minutes=schedule,
        schedule_config=schedule_config,
        allow_multi_server=allow_multi_server,
        max_connections=max_connections,
        max_iterations=max_iterations,
        session_timeout_seconds=session_timeout,
        request=request,
    )
    if violations:
        return _pilot_policy_denied(request, action="agent_create", violations=violations)

    agent = ServerAgent.objects.create(
        user=request.user,
        project_id=next(iter(execution_project_ids), None),
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
        provider_binding=provider_binding,
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
    if not user_can_manage_ai_routing(request.user):
        agent.provider_binding = {}
    elif "provider_binding" in data:
        if data.get("provider_binding") in ({}, None):
            agent.provider_binding = {}
        else:
            try:
                context = build_execution_context(
                    actor_user_id=request.user.pk,
                    project_id=agent.project_id,
                    purpose="ops",
                    source_kind="server_agent",
                    source_id=agent.pk,
                    mode=(
                        ExecutionMode.UNATTENDED
                        if int(data.get("schedule_minutes", agent.schedule_minutes) or 0) > 0
                        else ExecutionMode.INTERACTIVE
                    ),
                    explicit_binding=data.get("provider_binding"),
                )
                agent.provider_binding = context.binding.to_dict()
            except (TypeError, ValueError, RuntimeError) as exc:
                return JsonResponse({"success": False, "error": str(exc)}, status=400)

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

    effective_servers = list(execution_servers) if execution_servers is not None else list(agent.servers.all())
    server_reasons = server_requirement_reasons(
        mode=agent.mode,
        commands=agent.commands,
        tools_config=agent.tools_config,
        sudo_policy=agent.sudo_policy,
        skill_slugs=agent.skill_slugs,
    )
    if not effective_servers and server_reasons:
        return JsonResponse(
            {"success": False, "error": "Selected commands or capabilities require a server", "code": "server_scope_required", "reasons": server_reasons},
            status=400,
        )
    violations = pilot_agent_policy_violations(
        user=request.user,
        servers=effective_servers,
        tools_config=agent.tools_config,
        sudo_policy=agent.sudo_policy,
        schedule_minutes=agent.schedule_minutes,
        schedule_config=agent.schedule_config,
        allow_multi_server=agent.allow_multi_server,
        max_connections=agent.max_connections,
        max_iterations=agent.max_iterations,
        session_timeout_seconds=agent.session_timeout_seconds,
        request=request,
    )
    if violations:
        return _pilot_policy_denied(
            request,
            action="agent_update",
            violations=violations,
            agent=agent,
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
    agent = (
        ServerAgent.objects.filter(id=agent_id, user=request.user)
        .prefetch_related("servers")
        .first()
    )
    if not agent:
        return JsonResponse({"success": False, "error": "Agent not found"}, status=404)

    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    violations = pilot_agent_policy_violations(
        user=request.user,
        servers=list(agent.servers.all()),
        tools_config=agent.tools_config,
        sudo_policy=agent.sudo_policy,
        schedule_minutes=agent.schedule_minutes,
        schedule_config=agent.schedule_config,
        allow_multi_server=agent.allow_multi_server,
        max_connections=agent.max_connections,
        max_iterations=agent.max_iterations,
        session_timeout_seconds=agent.session_timeout_seconds,
        request=request,
    )
    if violations:
        return _pilot_policy_denied(
            request,
            action="agent_run",
            violations=violations,
            agent=agent,
        )

    launch_result = start_agent_run_for_user(
        agent=agent,
        user=request.user,
        accessible_servers_queryset=_accessible_servers_queryset(request.user),
        server_id=data.get("server_id"),
        source="http",
        provider_binding=(data.get("provider_binding") if user_can_manage_ai_routing(request.user) else None),
    )
    return JsonResponse(launch_result["payload"], status=200 if launch_result["ok"] else int(launch_result["status"]))


def _pilot_policy_denied(request, *, action: str, violations: list[str], agent=None) -> JsonResponse:
    log_user_activity(
        user=request.user,
        request=request,
        category="agent",
        action="pilot_policy_denied",
        entity_type="agent",
        entity_id=str(getattr(agent, "pk", "new")),
        entity_name=str(getattr(agent, "name", action)),
        metadata={"requested_action": action, "violations": violations[:10]},
    )
    return JsonResponse(
        {
            "success": False,
            "error": "Agent configuration violates the restricted pilot policy",
            "code": "pilot_policy_violation",
            "violations": violations,
        },
        status=403,
    )
