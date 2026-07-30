"""Assistant actions: agent run control + server overview (F-08a split of assistant_actions)."""

from __future__ import annotations

from asgiref.sync import async_to_sync

from app.assistant_actions import AssistantActionContext, AssistantActionError
from app.runtime_limits import ACTIVE_AGENT_RUN_STATUSES
from core_ui.projects import active_project_for_user
from servers.agents.agent_run_report import build_agent_run_report_response
from servers.agents.agent_service import (
    approve_agent_plan_for_user,
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


def _coerce_positive_int(value) -> int | None:
    """Best-effort int from tool/LLM payloads (str, float, nested {id})."""
    if value is None or value is False or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        if value.is_integer() and value > 0:
            return int(value)
        return None
    if isinstance(value, dict):
        for key in ("id", "run_id", "pk", "value"):
            if key in value:
                return _coerce_positive_int(value.get(key))
        return None
    text = str(value).strip()
    if not text:
        return None
    # "run #42" / "#42" / "42.0"
    if text.startswith("#"):
        text = text[1:].strip()
    if text.lower().startswith("run"):
        parts = text.replace("#", " ").split()
        for part in reversed(parts):
            coerced = _coerce_positive_int(part)
            if coerced is not None:
                return coerced
    try:
        if "." in text:
            f = float(text)
            if f.is_integer() and f > 0:
                return int(f)
        parsed = int(text)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _int_payload(ctx: AssistantActionContext, key: str, *, aliases: tuple[str, ...] = ()) -> int:
    payload = ctx.input_payload if isinstance(ctx.input_payload, dict) else {}
    keys = (key, *aliases)
    for candidate_key in keys:
        if candidate_key not in payload:
            continue
        parsed = _coerce_positive_int(payload.get(candidate_key))
        if parsed is not None:
            return parsed
    # Also scan common nested bags some models invent
    for bag_key in ("run", "agent_run", "params", "input"):
        bag = payload.get(bag_key)
        if isinstance(bag, dict):
            for candidate_key in keys:
                parsed = _coerce_positive_int(bag.get(candidate_key))
                if parsed is not None:
                    return parsed
    raise AssistantActionError(
        f"{key} must be an integer (got {payload.get(key)!r}). Pass a positive run id, e.g. run_id=42."
    )


def _resolve_agent_run_id(ctx: AssistantActionContext) -> int:
    """run_id for agent tools — with fallbacks when the model only has agent_id."""
    payload = ctx.input_payload if isinstance(ctx.input_payload, dict) else {}
    try:
        return _int_payload(ctx, "run_id", aliases=("agent_run_id", "runId", "id"))
    except AssistantActionError:
        pass

    agent_id = _coerce_positive_int(payload.get("agent_id") or payload.get("agentId"))
    if agent_id is not None:
        # Prefer plan-review run (approve_plan), else any active run for that agent.
        run = (
            AgentRun.objects.filter(
                agent_id=agent_id,
                agent__user=ctx.user,
                status=AgentRun.STATUS_PLAN_REVIEW,
            )
            .order_by("-id")
            .only("id")
            .first()
        )
        if run is None:
            run = (
                AgentRun.objects.filter(
                    agent_id=agent_id,
                    agent__user=ctx.user,
                    status__in=ACTIVE_AGENT_RUN_STATUSES,
                )
                .order_by("-id")
                .only("id")
                .first()
            )
        if run is not None:
            return int(run.id)

    raise AssistantActionError(
        "run_id must be an integer. If the agent is waiting for plan approval, "
        "pass run_id from agent.run result (or agent_id of a plan_review run)."
    )


def _agent_for_user(user, agent_id: int) -> ServerAgent:
    agent = (
        ServerAgent.objects.filter(id=agent_id, user=user, project=active_project_for_user(user))
        .prefetch_related("servers")
        .first()
    )
    if agent is None:
        raise AssistantActionError("Agent not found", status=404)
    return agent


def _run_for_user(user, run_id: int) -> AgentRun:
    project = active_project_for_user(user)
    run = AgentRun.objects.filter(project=project, id=run_id, user=user).select_related("agent", "server").first()
    if run:
        return run
    run = (
        AgentRun.objects.filter(project=project, id=run_id, agent__user=user).select_related("agent", "server").first()
    )
    if run is None:
        raise AssistantActionError("Agent run not found", status=404)
    return run


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
        raise AssistantActionError(
            result["payload"].get("error") or "Agent run failed",
            status=int(result["status"]),
            details=result["payload"],
        )
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
        raise AssistantActionError(
            result["payload"].get("error") or "Agent stop failed",
            status=int(result["status"]),
            details=result["payload"],
        )
    payload = dict(result["payload"])
    if payload.get("run_id"):
        payload["target_url"] = f"/agents/run/{payload['run_id']}"
    return payload


def reply_to_agent(ctx: AssistantActionContext) -> dict:
    run_id = _resolve_agent_run_id(ctx)
    answer = str(ctx.input_payload.get("answer") or "").strip()
    if not answer:
        raise AssistantActionError("answer is required")
    result = reply_to_agent_run_for_user(run_id=run_id, user=ctx.user, answer=answer, source="assistant_chat")
    if not result["ok"]:
        raise AssistantActionError(
            result["payload"].get("error") or "Agent reply failed",
            status=int(result["status"]),
            details=result["payload"],
        )
    return {**result["payload"], "target_url": f"/agents/run/{run_id}"}


def approve_agent_plan(ctx: AssistantActionContext) -> dict:
    run_id = _resolve_agent_run_id(ctx)
    result = approve_agent_plan_for_user(
        run_id=run_id,
        user=ctx.user,
        accessible_servers_queryset=_accessible_servers_queryset(ctx.user),
        source="assistant_chat",
    )
    if not result["ok"]:
        raise AssistantActionError(
            result["payload"].get("error") or "Agent plan approval failed",
            status=int(result["status"]),
            details=result["payload"],
        )
    return {**result["payload"], "target_url": f"/agents/run/{run_id}"}


def agent_report(ctx: AssistantActionContext) -> dict:
    run = _run_for_user(ctx.user, _resolve_agent_run_id(ctx))
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
