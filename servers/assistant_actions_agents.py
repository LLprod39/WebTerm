"""Assistant actions: agent listing and creation (F-08a split of assistant_actions)."""

from __future__ import annotations

from app.agent_kernel import skill_provider_registry
from app.assistant_actions import AssistantActionContext, AssistantActionError
from app.sudo_policy import normalize_sudo_policy
from servers.agents.agent_inputs import normalize_input_artifacts, normalize_report_delivery
from servers.agents.agent_pilot_policy import (
    PILOT_MAX_ITERATIONS,
    PILOT_MAX_SESSION_TIMEOUT_SECONDS,
    pilot_agent_policy_violations,
    user_can_automate,
)
from servers.agents.agent_schedule import normalize_schedule_config, schedule_minutes_for_config
from servers.agents.agent_service import list_agents_for_user
from servers.models import ServerAgent
from servers.services.server_query import (
    CAPABILITY_EXECUTE_COMMAND,
    get_servers_for_user_capability,
    resolve_servers_for_user_capability,
)


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
    if agent_type in {
        "auto",
        "git_docker_deploy",
        "security_patrol",
        "log_investigator",
        "infra_scout",
        "deploy_watcher",
    }:
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

    accessible_qs = get_servers_for_user_capability(ctx.user, CAPABILITY_EXECUTE_COMMAND)
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
    from servers.agents.agent_budgets import (
        FULL_DEFAULT_MAX_ITERATIONS,
        FULL_DEFAULT_SESSION_TIMEOUT_SEC,
        clamp_full_iterations,
    )

    restricted_pilot = not user_can_automate(ctx.user)
    default_iterations = PILOT_MAX_ITERATIONS if restricted_pilot else FULL_DEFAULT_MAX_ITERATIONS
    try:
        max_iterations = clamp_full_iterations(int(data.get("max_iterations") or default_iterations))
    except (TypeError, ValueError):
        max_iterations = default_iterations
    try:
        schedule_minutes = int(data.get("schedule_minutes") or 0)
    except (TypeError, ValueError):
        raise AssistantActionError("schedule_minutes must be an integer", status=400) from None
    schedule_config = normalize_schedule_config(data.get("schedule_config"), fallback_minutes=schedule_minutes)
    schedule = schedule_minutes_for_config(schedule_config, schedule_minutes)
    skill_slugs = skill_provider_registry.sanitize_accessible_skill_slugs(
        ctx.user,
        skill_provider_registry.normalise_skill_slugs(
            data.get("skill_slugs") if "skill_slugs" in data else data.get("skills")
        ),
    )

    if mode == ServerAgent.MODE_MINI and not commands:
        raise AssistantActionError("Mini agent requires commands")

    if mode in {ServerAgent.MODE_FULL, ServerAgent.MODE_MULTI}:
        if not goal.strip() and not description.strip():
            raise AssistantActionError("goal or description is required — what should the agent do?")
        if not goal.strip():
            goal, system_prompt, ai_prompt = _scaffold_from_task(name=name, task=description, goal=description)
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

    default_timeout = PILOT_MAX_SESSION_TIMEOUT_SECONDS if restricted_pilot else FULL_DEFAULT_SESSION_TIMEOUT_SEC
    try:
        session_timeout_seconds = int(data.get("session_timeout_seconds") or default_timeout)
    except (TypeError, ValueError):
        session_timeout_seconds = default_timeout
    session_timeout_seconds = max(30, min(session_timeout_seconds, 3600))

    tools_config = data.get("tools_config") if isinstance(data.get("tools_config"), dict) else {}
    # Empty = all tools enabled in the engine
    stop_conditions = data.get("stop_conditions") if isinstance(data.get("stop_conditions"), list) else []
    sudo_policy = normalize_sudo_policy(data.get("sudo_policy"))

    allow_multi_raw = data.get("allow_multi_server", False if restricted_pilot else mode == ServerAgent.MODE_MULTI)
    if not isinstance(allow_multi_raw, bool):
        raise AssistantActionError("allow_multi_server must be a boolean", status=400)
    allow_multi_server = allow_multi_raw
    try:
        max_connections = int(data.get("max_connections") or (1 if restricted_pilot else 5))
    except (TypeError, ValueError):
        raise AssistantActionError("max_connections must be an integer", status=400) from None
    max_connections = max(1, min(max_connections, 10))

    accessible, denied_server_ids = resolve_servers_for_user_capability(
        server_ids,
        ctx.user,
        CAPABILITY_EXECUTE_COMMAND,
        base_queryset=accessible_qs,
    )
    if denied_server_ids or not accessible:
        raise AssistantActionError("Missing server capability: execute_command", status=403)
    project_ids = {server.project_id for server in accessible}
    if len(project_ids) > 1:
        raise AssistantActionError("Selected servers cannot be combined in one agent", status=400)

    policy_violations = pilot_agent_policy_violations(
        user=ctx.user,
        servers=accessible,
        tools_config=tools_config,
        sudo_policy=sudo_policy,
        schedule_minutes=schedule,
        schedule_config=schedule_config,
        allow_multi_server=allow_multi_server,
        max_connections=max_connections,
        max_iterations=max_iterations,
        session_timeout_seconds=session_timeout_seconds,
    )
    if policy_violations:
        raise AssistantActionError(
            f"Pilot policy violation: {'; '.join(policy_violations)}",
            status=403,
        )

    agent = ServerAgent.objects.create(
        user=ctx.user,
        project_id=next(iter(project_ids), None),
        name=name,
        mode=mode,
        agent_type=agent_type,
        commands=commands,
        ai_prompt=ai_prompt,
        goal=goal,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        allow_multi_server=allow_multi_server,
        tools_config=tools_config if tools_config else {},
        sudo_policy=sudo_policy,
        stop_conditions=stop_conditions,
        session_timeout_seconds=session_timeout_seconds,
        max_connections=max_connections,
        schedule_minutes=schedule,
        schedule_config=schedule_config,
        skill_slugs=skill_slugs,
        input_artifacts=normalize_input_artifacts(data.get("input_artifacts")),
        report_delivery=normalize_report_delivery(data.get("report_delivery")),
        is_enabled=True,
    )
    agent.servers.set(accessible)

    from servers.agents.agent_service import serialize_agent_item

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
        "target_url": "/agents",
        "run_hint": f"agent.run with agent_id={agent.id} after user provides a Git URL (if deploy agent).",
    }
