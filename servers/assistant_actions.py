from __future__ import annotations

from asgiref.sync import async_to_sync

from app.agent_kernel import skill_provider_registry
from app.assistant_actions import (
    AssistantActionContext,
    AssistantActionError,
    AssistantActionSpec,
    register_action,
    register_runtime_context_provider,
)
from app.runtime_limits import ACTIVE_AGENT_RUN_STATUSES
from app.sudo_policy import normalize_sudo_policy
from core_ui.access import feature_allowed_for_user
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


def _human_agent_name(name: str, goal: str, description: str = "") -> str:
    raw = (name or "").strip()
    # Reject snake_case / machine names from LLMs
    if raw and ("_" in raw or (raw.islower() and " " not in raw and len(raw) > 18)):
        raw = ""
    if raw and raw.lower() in {"agent", "chat agent", "custom", "git-deployer", "git deployer"}:
        raw = ""
    if raw:
        return raw[:200]
    seed = (goal or description or "").strip()
    if seed:
        first = seed.split(".")[0].strip()
        # Short title
        if len(first) > 60:
            first = first[:57].rstrip() + "…"
        return first or "Агент"
    return "Агент"


def _scaffold_from_task(*, name: str, task: str, goal: str) -> tuple[str, str, str]:
    """Build goal / system / ai from free-text task when the model under-fills fields."""
    task = (task or goal or "").strip()
    goal_out = (goal or task or f"Выполнить задачу агента «{name}»").strip()
    if len(goal_out) < 40 and task and task not in goal_out:
        goal_out = f"{goal_out.rstrip('.')}. {task}".strip()

    system = (
        f"Ты — операционный агент «{name}» на WebTerm.\n"
        f"Задача: {goal_out}\n\n"
        "Как работать:\n"
        "1) Прими входные данные от пользователя (ссылки, параметры). Не выдумывай секреты.\n"
        "2) На целевом сервере проверь окружение нужными командами (ssh_execute).\n"
        "3) Выполни шаги задачи последовательно; после каждого шага проверяй результат.\n"
        "4) Спрашивай пользователя (ask_user) только если без этого нельзя продолжить "
        "(нет доступа, неоднозначный выбор, нужны credentials).\n"
        "5) В конце — короткий report: что сделано, как проверить, как откатить.\n"
        "Безопасность: не выполняй разрушительные команды без явной необходимости; "
        "не печатай пароли/токены. Отвечай на русском."
    )
    ai = goal_out[:500]
    return goal_out, system, ai


def create_agent(ctx: AssistantActionContext) -> dict:
    """Create agent from free-form chat payload — no forced templates.

    The Operator LLM must supply name/goal/system_prompt (or description/task).
    We only scaffold missing text and attach servers; we do not force canned templates.
    """
    data = ctx.input_payload if isinstance(ctx.input_payload, dict) else {}
    description = str(
        data.get("description") or data.get("brief") or data.get("task") or data.get("user_request") or ""
    ).strip()
    mode = str(data.get("mode") or "full").strip()
    if mode not in {ServerAgent.MODE_MINI, ServerAgent.MODE_FULL, ServerAgent.MODE_MULTI}:
        mode = ServerAgent.MODE_FULL

    # Always custom unless caller explicitly passes a known type for UI catalogs
    agent_type = str(data.get("agent_type") or "custom").strip() or "custom"
    if agent_type in {"auto", "git_docker_deploy", "security_patrol", "log_investigator", "infra_scout", "deploy_watcher"}:
        # Ignore canned types from chat — user wants free-form agents
        agent_type = "custom"

    goal = str(data.get("goal") or "").strip() or description
    system_prompt = str(data.get("system_prompt") or "").strip()
    ai_prompt = str(data.get("ai_prompt") or "").strip()
    name = _human_agent_name(str(data.get("name") or ""), goal, description)

    # If model under-filled prompts, scaffold from the task text (not from templates)
    if mode in {ServerAgent.MODE_FULL, ServerAgent.MODE_MULTI}:
        if not goal or len(system_prompt) < 80:
            g2, s2, a2 = _scaffold_from_task(name=name, task=description or goal, goal=goal)
            if not goal:
                goal = g2
            if len(system_prompt) < 80:
                system_prompt = s2
            if len(ai_prompt) < 40:
                ai_prompt = a2
        if not ai_prompt:
            ai_prompt = goal[:500]

    # server_ids: list, single server_id, or auto from user's accessible inventory
    server_ids = data.get("server_ids") if isinstance(data.get("server_ids"), list) else []
    if not server_ids and data.get("server_id") not in (None, ""):
        try:
            server_ids = [int(data.get("server_id"))]
        except (TypeError, ValueError):
            server_ids = []
    # Tolerate string ids and dicts {id: N}
    cleaned_ids: list[int] = []
    for x in server_ids:
        if isinstance(x, dict) and x.get("id") is not None:
            try:
                cleaned_ids.append(int(x["id"]))
            except (TypeError, ValueError):
                continue
        else:
            try:
                cleaned_ids.append(int(x))
            except (TypeError, ValueError):
                continue
    server_ids = cleaned_ids

    accessible_qs = _accessible_servers_queryset(ctx.user)
    if not server_ids:
        # Auto-pick: sole server, or match by name tokens in goal/description/name
        accessible = list(accessible_qs.order_by("name")[:50])
        if len(accessible) == 1:
            server_ids = [accessible[0].id]
        else:
            hay = " ".join(
                str(p or "") for p in (name, goal, description, data.get("ai_prompt"), data.get("system_prompt"))
            ).lower()
            matched = [s for s in accessible if s.name and s.name.lower() in hay]
            if len(matched) == 1:
                server_ids = [matched[0].id]
            elif len(accessible) <= 3 and accessible:
                # Small fleet: attach all so agent is usable; user can edit later
                server_ids = [s.id for s in accessible]
            elif accessible:
                # Prefer the most recently updated server rather than failing empty
                recent = list(accessible_qs.order_by("-updated_at", "-id")[:1])
                if recent:
                    server_ids = [recent[0].id]

    commands = data.get("commands") if isinstance(data.get("commands"), list) else []
    from servers.agent_budgets import (
        FULL_DEFAULT_MAX_ITERATIONS,
        FULL_DEFAULT_SESSION_TIMEOUT_SEC,
        clamp_full_iterations,
    )

    try:
        max_iterations = clamp_full_iterations(int(data.get("max_iterations") or FULL_DEFAULT_MAX_ITERATIONS))
    except (TypeError, ValueError):
        max_iterations = FULL_DEFAULT_MAX_ITERATIONS
    schedule_minutes = int(data.get("schedule_minutes") or 0)
    schedule_config = normalize_schedule_config(data.get("schedule_config"), fallback_minutes=schedule_minutes)
    schedule = schedule_minutes_for_config(schedule_config, schedule_minutes)
    skill_slugs = skill_provider_registry.sanitize_accessible_skill_slugs(
        ctx.user,
        skill_provider_registry.normalise_skill_slugs(data.get("skill_slugs") if "skill_slugs" in data else data.get("skills")),
    )

    if mode == ServerAgent.MODE_MINI and not commands:
        raise AssistantActionError("Mini agent requires commands")

    if mode in {ServerAgent.MODE_FULL, ServerAgent.MODE_MULTI}:
        if not goal.strip() and not description.strip():
            raise AssistantActionError(
                "goal or description is required — what should the agent do?"
            )
        if not goal.strip():
            goal, system_prompt, ai_prompt = _scaffold_from_task(
                name=name, task=description, goal=description
            )
        if not system_prompt.strip():
            _, system_prompt, a2 = _scaffold_from_task(name=name, task=description or goal, goal=goal)
            if not ai_prompt:
                ai_prompt = a2
        if not ai_prompt.strip():
            ai_prompt = goal[:500]

    if not server_ids:
        raise AssistantActionError(
            "Нет доступных серверов для агента. Добавь сервер в инвентарь или укажи @имя / server_ids."
        )

    try:
        session_timeout_seconds = int(data.get("session_timeout_seconds") or FULL_DEFAULT_SESSION_TIMEOUT_SEC)
    except (TypeError, ValueError):
        session_timeout_seconds = FULL_DEFAULT_SESSION_TIMEOUT_SEC
    session_timeout_seconds = max(30, min(session_timeout_seconds, 3600))

    tools_config = data.get("tools_config") if isinstance(data.get("tools_config"), dict) else {}
    # Empty = all tools enabled in the engine
    stop_conditions = data.get("stop_conditions") if isinstance(data.get("stop_conditions"), list) else []
    sudo_policy = data.get("sudo_policy")

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
        tools_config=tools_config if tools_config else {},
        sudo_policy=normalize_sudo_policy(sudo_policy),
        stop_conditions=stop_conditions,
        session_timeout_seconds=session_timeout_seconds,
        max_connections=max(1, min(int(data.get("max_connections") or 5), 10)),
        schedule_minutes=schedule,
        schedule_config=schedule_config,
        skill_slugs=skill_slugs,
        input_artifacts=normalize_input_artifacts(data.get("input_artifacts")),
        report_delivery=normalize_report_delivery(data.get("report_delivery")),
        is_enabled=True,
    )
    accessible = list(accessible_qs.filter(id__in=server_ids))
    if not accessible:
        agent.delete()
        raise AssistantActionError("No accessible servers matched server_ids", status=403)
    agent.servers.set(accessible)

    from servers.agent_service import serialize_agent_item

    item = serialize_agent_item(agent)
    return {
        "agent": item,
        "id": agent.id,
        "name": agent.name,
        "mode": agent.mode,
        "agent_type": agent.agent_type,
        "server_ids": [s.id for s in accessible],
        "server_names": [s.name for s in accessible],
        "goal": agent.goal,
        "ready": bool(agent.goal and agent.system_prompt and accessible),
        "target_url": f"/agents",
        "run_hint": f"agent.run with agent_id={agent.id} after user provides a Git URL (if deploy agent).",
    }


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
        payload["async"] = True
        payload["async_kind"] = "agent_run"
        payload.setdefault("status", "running")
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


def build_assistant_runtime_context(user) -> dict:
    context: dict = {"agents": [], "servers": []}
    if feature_allowed_for_user(user, "agents"):
        agents = list(ServerAgent.objects.filter(user=user).prefetch_related("servers").order_by("-updated_at", "-id")[:30])
        active_runs = {}
        for run in (
            AgentRun.objects.filter(agent__in=agents, status__in=ACTIVE_AGENT_RUN_STATUSES)
            .order_by("agent_id", "-started_at", "-id")
        ):
            active_runs.setdefault(run.agent_id, run)
        context["agents"] = [
            {
                "id": agent.id,
                "name": agent.name,
                "mode": agent.mode,
                "agent_type": agent.agent_type,
                "goal": (agent.goal or agent.ai_prompt or "")[:500],
                "server_ids": list(agent.servers.values_list("id", flat=True)[:8]),
                "server_names": list(agent.servers.values_list("name", flat=True)[:8]),
                "is_enabled": bool(agent.is_enabled),
                "active_run_id": active_runs[agent.id].id if agent.id in active_runs else None,
                "active_run_status": active_runs[agent.id].status if agent.id in active_runs else "",
            }
            for agent in agents
        ]

    if feature_allowed_for_user(user, "servers"):
        servers = list(_accessible_servers_queryset(user).order_by("-updated_at", "-id")[:30])
        context["servers"] = [
            {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
                "server_type": server.server_type,
                "is_active": bool(server.is_active),
                "detected_os": server.detected_os,
            }
            for server in servers
        ]
    return context


def register_assistant_actions() -> None:
    register_runtime_context_provider("servers", build_assistant_runtime_context)
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
            description=(
                "Create a custom agent from scratch (no templates). Pass name, mode=full, goal, "
                "system_prompt (detailed), ai_prompt, optional server_ids. Backend scaffolds missing "
                "text and auto-picks servers when omitted."
            ),
            required_feature="agents",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "required": ["mode", "goal"],
                "properties": {
                    "name": {"type": "string", "description": "Human title in Russian"},
                    "mode": {"type": "string", "enum": ["mini", "full", "multi"]},
                    "goal": {"type": "string"},
                    "system_prompt": {"type": "string"},
                    "ai_prompt": {"type": "string"},
                    "description": {"type": "string", "description": "User task if goal not expanded yet"},
                    "server_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional; auto from pin/@/sole server",
                    },
                },
            },
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
