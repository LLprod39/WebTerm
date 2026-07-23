"""
Pipeline Executor

Traverses a Pipeline graph (nodes + edges) in topological order and dispatches
each node to the appropriate execution engine:

  trigger/*              — handled by the caller (just passes context)
  agent/react            — wraps servers.AgentEngine (ReAct loop, CAN execute SSH on server)
  agent/multi            — wraps servers.MultiAgentEngine
  agent/ssh_cmd          — direct SSH command without LLM
  agent/llm_query        — direct LLM call (no SSH, pure reasoning/analysis/decision)
  agent/mcp_call         — direct MCP tools/call on a configured MCP server
  logic/condition        — branches based on previous output
  logic/parallel         — launches multiple agent nodes concurrently
  logic/wait             — pauses execution for N minutes
  logic/human_approval   — waits for human approve/reject via signed URL (email+Telegram)
  output/report          — attaches final markdown to the run
  output/webhook         — POSTs result to an external URL
  output/email           — sends email report via SMTP
  output/telegram        — sends message via Telegram Bot API
"""

from __future__ import annotations

import logging
from threading import Event

from asgiref.sync import sync_to_async as _s2a
from django.utils import timezone

from core_ui.audit import audit_context
from studio.executor import nodes as _registered_executor_nodes  # noqa: F401
from studio.executor.context import ExecutionContext
from studio.executor.plugin_nodes import clear_plugin_node_registry_async, sync_plugin_node_registry_async
from studio.executor.registry import registry

from .models import PipelineRun
from .pipeline_agent_llm import (
    _load_pipeline_operational_recipes,
    _load_pipeline_server_memory,
    _resolve_llm_provider_and_model,
)
from .pipeline_agent_llm import (
    execute_agent_llm_query as _execute_agent_llm_query,
)
from .pipeline_agent_mcp import (
    coerce_mcp_arguments as _coerce_mcp_arguments,
)
from .pipeline_agent_mcp import (
    execute_agent_mcp_call as _execute_agent_mcp_call,
)
from .pipeline_agent_mcp import (
    mcp_result_to_text as _mcp_result_to_text,
)
from .pipeline_agent_runtime import (
    _log_pipeline_ssh_command,
)
from .pipeline_agent_runtime import (
    execute_agent_multi as _execute_agent_multi,
)
from .pipeline_agent_runtime import (
    execute_agent_react as _execute_agent_react,
)
from .pipeline_agent_runtime import (
    execute_agent_ssh_cmd as _execute_agent_ssh_cmd,
)
from .pipeline_context import (
    build_enriched_node_context as _build_enriched_node_context,
)
from .pipeline_context import (
    pipeline_actor_context as _pipeline_actor_context,
)
from .pipeline_context import (
    render_template_value as _render_template_value,
)
from .pipeline_interactions import (
    _global_email_defaults,
    _global_site_url,
    _global_tg_defaults,
    _send_telegram_message,
)
from .pipeline_interactions import (
    execute_logic_human_approval as _execute_logic_human_approval,
)
from .pipeline_interactions import (
    execute_logic_telegram_input as _execute_logic_telegram_input,
)
from .pipeline_interactions import (
    resolve_telegram_target as _resolve_telegram_target,
)
from .pipeline_logic import (
    execute_logic_condition as _execute_logic_condition,
)
from .pipeline_logic import (
    execute_logic_merge as _execute_logic_merge,
)
from .pipeline_logic import (
    execute_logic_wait as _execute_logic_wait,
)
from .pipeline_outputs import (
    execute_output_email as _execute_output_email,
)
from .pipeline_outputs import (
    execute_output_report as _execute_output_report,
)
from .pipeline_outputs import (
    execute_output_telegram as _execute_output_telegram,
)
from .pipeline_outputs import (
    execute_output_webhook as _execute_output_webhook,
)
from .pipeline_redaction import (
    redact_pipeline_text as _redact_pipeline_text,
)
from .pipeline_redaction import (
    redact_pipeline_value as _redact_pipeline_value,
)
from .pipeline_redaction import (
    redacted_all_outputs_text as _redacted_all_outputs_text,
)
from .pipeline_redaction import (
    redacted_mapping_context as _redacted_pipeline_context,
)
from .pipeline_run_loop import execute_pipeline_run_loop as _execute_pipeline_run_loop
from .pipeline_run_setup import prepare_pipeline_run_start as _prepare_pipeline_run_start
from .pipeline_run_state import (
    make_run_event_callback as _make_run_event_callback,
)
from .pipeline_run_state import (
    update_run_status as _update_run_status,
)
from .pipeline_runtime import is_runtime_stop_requested, register_executor, unregister_executor
from .pipeline_telegram import (
    _TELEGRAM_PENDING_CALLBACKS,
    _TELEGRAM_PENDING_REPLIES,
    _TELEGRAM_UPDATE_LOCKS,
    _TELEGRAM_UPDATE_OFFSETS,
    _parse_telegram_approval_callback_data,
    _poll_telegram_approval_decision,
    _poll_telegram_reply_message,
    _poll_telegram_updates,
    _telegram_approval_callback_data,
    store_telegram_operator_reply,
)

__all__ = [
    "PipelineExecutor",
    "_TELEGRAM_PENDING_CALLBACKS",
    "_TELEGRAM_PENDING_REPLIES",
    "_TELEGRAM_UPDATE_LOCKS",
    "_TELEGRAM_UPDATE_OFFSETS",
    "_coerce_mcp_arguments",
    "_execute_agent_llm_query",
    "_execute_agent_mcp_call",
    "_execute_agent_multi",
    "_execute_agent_react",
    "_execute_agent_ssh_cmd",
    "_execute_logic_condition",
    "_execute_logic_human_approval",
    "_execute_logic_merge",
    "_execute_logic_telegram_input",
    "_execute_logic_wait",
    "_execute_output_email",
    "_execute_output_report",
    "_execute_output_telegram",
    "_execute_output_webhook",
    "_global_email_defaults",
    "_global_site_url",
    "_global_tg_defaults",
    "_load_pipeline_operational_recipes",
    "_load_pipeline_server_memory",
    "_log_pipeline_ssh_command",
    "_make_run_event_callback",
    "_mcp_result_to_text",
    "_parse_telegram_approval_callback_data",
    "_poll_telegram_approval_decision",
    "_poll_telegram_reply_message",
    "_poll_telegram_updates",
    "_redact_pipeline_text",
    "_redact_pipeline_value",
    "_redacted_all_outputs_text",
    "_redacted_pipeline_context",
    "_render_template_value",
    "_resolve_llm_provider_and_model",
    "_resolve_telegram_target",
    "_send_telegram_message",
    "_telegram_approval_callback_data",
    "store_telegram_operator_reply",
]

logger = logging.getLogger(__name__)


def _s2a_fn(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


async def _execute_registry_node(
    node: dict,
    context: dict,
    node_outputs: dict[str, dict],
    run: PipelineRun,
    stop_event: Event | None = None,
    executed_mcp_tools: set[str] | None = None,
) -> dict:
    """Execute registry-owned nodes from the current production executor."""
    node_type = str(node.get("type") or "")
    node_id = str(node.get("id") or "")
    if node_type not in registry:
        return {"status": "failed", "error": f"Node type is not registered: {node_type}"}

    owner = await _s2a_fn(lambda: run.pipeline.owner)()
    ctx = ExecutionContext(
        run_id=run.pk,
        user=owner,
        pipeline=run.pipeline,
        node_outputs=dict(node_outputs or {}),
        stop_event=stop_event or Event(),
        extra={
            "context": dict(context or {}),
            "run": run,
            "executed_mcp_tools": executed_mcp_tools,
            "runtime": {
                "pipeline_name": run.pipeline.name,
                "run_id": str(run.pk),
                "run_status": str(run.status or ""),
                "entry_node_id": str(run.entry_node_id or ""),
                "trigger_type": str(getattr(run.trigger, "trigger_type", "") or ""),
                "trigger_name": str(getattr(run.trigger, "name", "") or ""),
            },
        },
    )
    try:
        result = await registry.create(node_type, node_id=node_id, node_data=node.get("data") or {}).execute(ctx)
    except Exception as exc:
        logger.exception("pipeline run %s registry node %s raised exception", run.pk, node_id)
        return {"status": "failed", "error": _redact_pipeline_text(str(exc))}

    payload = dict(result.output or {})
    status = str(payload.pop("status", "") or ("completed" if result.ok else "failed"))
    state = {"status": status, **payload}
    if result.error:
        state["error"] = result.error
    if "output" not in state and result.error:
        state["output"] = ""
    return state


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------


class PipelineExecutor:
    """
    Executes a Pipeline via a selected trigger entry node and explicit edge routing.

    Usage::
        executor = PipelineExecutor(pipeline_run)
        await executor.execute(context={"key": "value"})
    """

    def __init__(self, run: PipelineRun):
        self.run = run
        self._stop_requested = False
        self._stop_event = Event()
        self._executed_mcp_tools: set[str] = set()

    def request_stop(self):
        self._stop_requested = True
        self._stop_event.set()

    async def _sync_stop_state_from_db(self) -> bool:
        run_snapshot = await _s2a_fn(
            lambda: PipelineRun.objects.filter(pk=self.run.pk).values("status", "runtime_control").first()
        )()
        if run_snapshot is None:
            self.request_stop()
            return self._stop_requested

        if run_snapshot.get("status") == PipelineRun.STATUS_STOPPED or is_runtime_stop_requested(
            run_snapshot.get("runtime_control")
        ):
            self.request_stop()
        return self._stop_requested

    async def execute(self, context: dict | None = None) -> PipelineRun:
        run = self.run
        register_executor(run.pk, self)
        try:
            with audit_context(**_pipeline_actor_context(run)):
                if await self._sync_stop_state_from_db():
                    await _update_run_status(run, PipelineRun.STATUS_STOPPED, finished_at=timezone.now())
                    return run
                prepared = await _prepare_pipeline_run_start(run, context)
                if prepared is None:
                    return run
                return await _execute_pipeline_run_loop(
                    run,
                    prepared,
                    execute_node=self._execute_node,
                    sync_stop_state_from_db=self._sync_stop_state_from_db,
                    request_stop=self.request_stop,
                    is_stop_requested=lambda: self._stop_requested,
                )
        finally:
            unregister_executor(run.pk, self)

    async def _execute_node(self, node: dict, context: dict, node_outputs: dict[str, dict]) -> dict:
        node_type = node.get("type", "")
        await sync_plugin_node_registry_async()

        enriched = _build_enriched_node_context(
            run=self.run,
            context=context,
            node_outputs=node_outputs,
        )

        if str(node_type) in registry:
            try:
                return await _execute_registry_node(
                    node,
                    enriched,
                    node_outputs,
                    self.run,
                    self._stop_event,
                    self._executed_mcp_tools,
                )
            finally:
                await clear_plugin_node_registry_async()

        logger.error("Unknown node type: %s (node id=%s)", node_type, node.get("id"))
        return {"status": "failed", "error": f"Node type is not registered: {node_type}"}
