from __future__ import annotations

from asgiref.sync import async_to_sync

from app.agent_kernel import skill_provider_registry
from app.assistant_actions import AssistantActionContext, AssistantActionError, AssistantActionSpec, register_action
from app.sudo_policy import normalize_sudo_policy
from servers.agent_inputs import normalize_input_artifacts, normalize_report_delivery
from servers.agent_run_report import build_agent_run_report_response
from servers.agent_schedule import normalize_schedule_config, schedule_minutes_for_config
from servers.agent_service import (
    approve_agent_plan_for_user,
    list_agents_for_user,
    reply_to_agent_run_for_user,
    start_agent_run_for_user,
    stop_agent_run_for_user,
)
from servers.agents import get_template
from servers.linux_ui import get_linux_ui_overview
from servers.models import AgentRun, ServerAgent
from servers.views.server_helpers import (
    _accessible_servers_queryset,
    _require_ssh_server,
    _resolve_server_secret,
    _server_has_capability,
)


def _int_payload(ctx: AssistantActionContext, key: str) -> int:
    value = ctx.input_payload.get(key)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AssistantActionError(f"{key} must be an integer") from exc
    if parsed <= 0:
        raise AssistantActionError(f"{key} must be positive")
    return parsed


def _agent_for_user(user, agent_id: int) -> ServerAgent:
    agent = ServerAgent.objects.filter(id=agent_id, user=user).prefetch_related("servers").first()
    if agent is None:
        raise AssistantActionError("Agent not found", status=404)
    return agent


def _run_for_user(user, run_id: int) -> AgentRun:
    run = AgentRun.objects.filter(id=run_id, user=user).select_related("agent", "server").first()
    if run:
        return run
    run = AgentRun.objects.filter(id=run_id, agent__user=user).select_related("agent", "server").first()
    if run is None:
        raise AssistantActionError("Agent run not found", status=404)
    return run


def list_agents(ctx: AssistantActionContext) -> dict:
    mode = str(ctx.input_payload.get("mode") or "").strip() or None
    agents = list_agents_for_user(ctx.user, mode_filter=mode)
    return {"agents": agents, "count": len(agents), "target_url": "/agents"}


def create_agent(ctx: AssistantActionContext) -> dict:
    data = ctx.input_payload
    mode = str(data.get("mode") or "full").strip()
    if mode not in {ServerAgent.MODE_MINI, ServerAgent.MODE_FULL, ServerAgent.MODE_MULTI}:
        mode = ServerAgent.MODE_FULL
    agent_type = str(data.get("agent_type") or "custom").strip() or "custom"
    tpl = get_template(agent_type)
    name = str(data.get("name") or (tpl or {}).get("name") or "Chat Agent").strip()[:200]
    server_ids = data.get("server_ids") if isinstance(data.get("server_ids"), list) else []
    commands = data.get("commands") if isinstance(data.get("commands"), list) else []
    ai_prompt = str(data.get("ai_prompt") or (tpl or {}).get("ai_prompt") or "")
    goal = str(data.get("goal") or (tpl or {}).get("goal") or data.get("description") or "")
    system_prompt = str(data.get("system_prompt") or (tpl or {}).get("system_prompt") or "")
    max_iterations = max(1, min(int(data.get("max_iterations") or 20), 100))
    schedule_minutes = int(data.get("schedule_minutes") or 0)
    schedule_config = normalize_schedule_config(data.get("schedule_config"), fallback_minutes=schedule_minutes)
    schedule = schedule_minutes_for_config(schedule_config, schedule_minutes)
    skill_slugs = skill_provider_registry.sanitize_accessible_skill_slugs(
        ctx.user,
        skill_provider_registry.normalise_skill_slugs(data.get("skill_slugs") if "skill_slugs" in data else data.get("skills")),
    )

    if mode == ServerAgent.MODE_MINI and not commands:
        commands = list((tpl or {}).get("commands") or [])
    if mode == ServerAgent.MODE_MINI and not commands:
        raise AssistantActionError("Mini agent requires commands")

    agent = ServerAgent.objects.create(
        user=ctx.user,
        name=name,
        mode=mode,
        agent_type=agent_type,
        commands=commands,
        ai_prompt=ai_prompt,
        goal=goal,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        allow_multi_server=bool(data.get("allow_multi_server", mode == ServerAgent.MODE_MULTI)),
        tools_config=data.get("tools_config") if isinstance(data.get("tools_config"), dict) else {},
        sudo_policy=normalize_sudo_policy(data.get("sudo_policy")),
        stop_conditions=data.get("stop_conditions") if isinstance(data.get("stop_conditions"), list) else [],
        session_timeout_seconds=int(data.get("session_timeout_seconds") or 600),
        max_connections=max(1, min(int(data.get("max_connections") or 5), 10)),
        schedule_minutes=schedule,
        schedule_config=schedule_config,
        skill_slugs=skill_slugs,
        input_artifacts=normalize_input_artifacts(data.get("input_artifacts")),
        report_delivery=normalize_report_delivery(data.get("report_delivery")),
    )
    accessible = _accessible_servers_queryset(ctx.user).filter(id__in=server_ids)
    agent.servers.set(accessible)
    return {"agent": {"id": agent.id, "name": agent.name, "mode": agent.mode}, "target_url": "/agents"}


def run_agent(ctx: AssistantActionContext) -> dict:
    agent = _agent_for_user(ctx.user, _int_payload(ctx, "agent_id"))
    server_id = ctx.input_payload.get("server_id")
    parsed_server_id = None
    if server_id not in (None, ""):
        try:
            parsed_server_id = int(server_id)
        except (TypeError, ValueError) as exc:
            raise AssistantActionError("server_id must be an integer") from exc
    result = start_agent_run_for_user(
        agent=agent,
        user=ctx.user,
        accessible_servers_queryset=_accessible_servers_queryset(ctx.user),
        server_id=parsed_server_id,
        source="assistant_chat",
    )
    if not result["ok"]:
        raise AssistantActionError(result["payload"].get("error") or "Agent run failed", status=int(result["status"]), details=result["payload"])
    payload = dict(result["payload"])
    run_id = payload.get("run_id")
    if run_id:
        payload["target_url"] = f"/agents/run/{run_id}"
    return payload


def stop_agent(ctx: AssistantActionContext) -> dict:
    agent_id = _int_payload(ctx, "agent_id")
    run_id = ctx.input_payload.get("run_id")
    parsed_run_id = None
    if run_id not in (None, ""):
        try:
            parsed_run_id = int(run_id)
        except (TypeError, ValueError) as exc:
            raise AssistantActionError("run_id must be an integer") from exc
    result = stop_agent_run_for_user(agent_id=agent_id, user=ctx.user, run_id=parsed_run_id, source="assistant_chat")
    if not result["ok"]:
        raise AssistantActionError(result["payload"].get("error") or "Agent stop failed", status=int(result["status"]), details=result["payload"])
    payload = dict(result["payload"])
    if payload.get("run_id"):
        payload["target_url"] = f"/agents/run/{payload['run_id']}"
    return payload


def reply_to_agent(ctx: AssistantActionContext) -> dict:
    run_id = _int_payload(ctx, "run_id")
    answer = str(ctx.input_payload.get("answer") or "").strip()
    if not answer:
        raise AssistantActionError("answer is required")
    result = reply_to_agent_run_for_user(run_id=run_id, user=ctx.user, answer=answer, source="assistant_chat")
    if not result["ok"]:
        raise AssistantActionError(result["payload"].get("error") or "Agent reply failed", status=int(result["status"]), details=result["payload"])
    return {**result["payload"], "target_url": f"/agents/run/{run_id}"}


def approve_agent_plan(ctx: AssistantActionContext) -> dict:
    run_id = _int_payload(ctx, "run_id")
    result = approve_agent_plan_for_user(
        run_id=run_id,
        user=ctx.user,
        accessible_servers_queryset=_accessible_servers_queryset(ctx.user),
        source="assistant_chat",
    )
    if not result["ok"]:
        raise AssistantActionError(result["payload"].get("error") or "Agent plan approval failed", status=int(result["status"]), details=result["payload"])
    return {**result["payload"], "target_url": f"/agents/run/{run_id}"}


def agent_report(ctx: AssistantActionContext) -> dict:
    run = _run_for_user(ctx.user, _int_payload(ctx, "run_id"))
    return {**build_agent_run_report_response(run), "target_url": f"/agents/run/{run.pk}"}


def server_overview(ctx: AssistantActionContext) -> dict:
    server_id = _int_payload(ctx, "server_id")
    server = _accessible_servers_queryset(ctx.user).filter(pk=server_id).first()
    if server is None:
        raise AssistantActionError("Server not found", status=404)
    if not _server_has_capability(server, ctx.user, "connect_terminal"):
        raise AssistantActionError("Missing server capability: connect_terminal", status=403)
    _require_ssh_server(server)
    request = ctx.request
    if request is None:
        raise AssistantActionError("Request context is required to resolve server credentials")
    secret = _resolve_server_secret(server, request, ctx.input_payload)
    overview = async_to_sync(get_linux_ui_overview)(server, secret=secret or "")
    return {
        "server": {"id": server.pk, "name": server.name, "host": server.host, "username": server.username},
        "overview": overview,
        "target_url": f"/servers/{server.pk}/terminal",
    }


def register_assistant_actions() -> None:
    specs = [
        AssistantActionSpec(
            action_type="agents.list",
            label="List agents",
            description="List configured agents and runtime overview.",
            required_feature="agents",
            risk="read",
            handler=list_agents,
        ),
        AssistantActionSpec(
            action_type="agent.create",
            label="Create agent",
            description="Create a mini/full/multi agent from a chat-approved payload.",
            required_feature="agents",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={"required": ["name", "mode"]},
            handler=create_agent,
        ),
        AssistantActionSpec(
            action_type="agent.run",
            label="Run agent",
            description="Launch an existing agent.",
            required_feature="agents",
            risk="mutating",
            requires_confirmation=True,
            input_schema={"required": ["agent_id"]},
            handler=run_agent,
        ),
        AssistantActionSpec(
            action_type="agent.stop",
            label="Stop agent",
            description="Stop an active agent run.",
            required_feature="agents",
            risk="mutating",
            requires_confirmation=True,
            input_schema={"required": ["agent_id"]},
            handler=stop_agent,
        ),
        AssistantActionSpec(
            action_type="agent.reply",
            label="Reply to agent",
            description="Reply to a waiting agent run.",
            required_feature="agents",
            risk="mutating",
            requires_confirmation=True,
            input_schema={"required": ["run_id", "answer"]},
            handler=reply_to_agent,
        ),
        AssistantActionSpec(
            action_type="agent.approve_plan",
            label="Approve agent plan",
            description="Approve a multi-agent plan review and start plan execution.",
            required_feature="agents",
            risk="mutating",
            requires_confirmation=True,
            input_schema={"required": ["run_id"]},
            handler=approve_agent_plan,
        ),
        AssistantActionSpec(
            action_type="agent.report",
            label="Get agent report",
            description="Read the canonical report for an agent run.",
            required_feature="agents",
            risk="read",
            input_schema={"required": ["run_id"]},
            handler=agent_report,
        ),
        AssistantActionSpec(
            action_type="server.diagnostics.overview",
            label="Server overview",
            description="Run the read-only Linux UI overview for an accessible SSH server.",
            required_feature="servers",
            risk="read",
            input_schema={"required": ["server_id"]},
            handler=server_overview,
        ),
    ]
    for spec in specs:
        register_action(spec)
