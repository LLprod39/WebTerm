from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async as _s2a

from app.command_history_provider import save_command_history_entry
from studio.models import PipelineRun
from studio.services import get_owned_servers_by_ids

from .pipeline_context import pipeline_actor_context, render_template_value

logger = logging.getLogger(__name__)


def _s2a_fn(func, thread_sensitive: bool = False):
    return _s2a(func, thread_sensitive=thread_sensitive)


def _save_server_command_history(
    *, server_id: int, user_id: int | None, command: str, output: str, exit_code: int | None
) -> None:
    save_command_history_entry(
        server_id=server_id,
        user_id=user_id,
        command=command,
        output=output,
        exit_code=exit_code,
    )


async def _log_pipeline_ssh_command(
    *,
    run: PipelineRun,
    server,
    node_id: str,
    command: str,
    exit_code: int | None,
    output: str = "",
    error: str = "",
) -> None:
    # Prefer facade attribute so monkeypatches on pipeline_agent_runtime.log_user_activity_async apply.
    from studio.pipeline import pipeline_agent_runtime as runtime

    log_user_activity_async = getattr(runtime, "log_user_activity_async", None)
    if log_user_activity_async is None:
        from core_ui.activity import log_user_activity_async as log_user_activity_async

    actor_ctx = pipeline_actor_context(run)
    status = "success" if exit_code == 0 and not error else "error"
    combined_output = error or output
    await log_user_activity_async(
        user_id=actor_ctx.get("user_id"),
        username_snapshot=str(actor_ctx.get("username_snapshot") or ""),
        category="terminal",
        action="server_execute_command",
        status=status,
        description=command[:4000],
        entity_type="server",
        entity_id=str(server.id),
        entity_name=server.name,
        metadata={
            "source": "pipeline_ssh_cmd",
            "pipeline_id": run.pipeline_id,
            "pipeline_run_id": run.pk,
            "node_id": node_id,
            "exit_code": exit_code,
            "output_excerpt": combined_output[:4000],
        },
    )
    await _s2a_fn(_save_server_command_history, thread_sensitive=True)(
        server_id=server.id,
        user_id=actor_ctx.get("user_id"),
        command=command,
        output=combined_output,
        exit_code=exit_code,
    )


async def _load_owned_servers(owner, server_ids: list[int]):
    if not server_ids:
        return []
    return await _s2a_fn(get_owned_servers_by_ids)(owner, server_ids, order_by="-updated_at")


def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_context_value(config: dict[str, Any], context: dict[str, Any], field: str, default_key: str) -> Any:
    direct = config.get(field)
    if direct not in (None, ""):
        return render_template_value(direct, context) if isinstance(direct, str) else direct
    key = str(config.get(f"{field}_context_key") or default_key).strip()
    return context.get(key) if key else ""


async def _load_owned_agent_config(owner, agent_config_id: int):
    from studio.models import AgentConfig

    return await _s2a_fn(
        lambda: (
            AgentConfig.objects.filter(id=agent_config_id, owner=owner)
            .prefetch_related("mcp_servers", "server_scope")
            .first()
        )
    )()


async def _load_agent_scope_ids(agent_conf) -> set[int]:
    if not agent_conf:
        return set()
    owner = getattr(agent_conf, "owner", None)
    return set(await _s2a_fn(lambda: list(agent_conf.server_scope.filter(user=owner).values_list("id", flat=True)))())


def _pipeline_trigger_type(run: PipelineRun) -> str:
    return str(getattr(run.trigger, "trigger_type", "") or getattr(run, "trigger_type", "") or "")
