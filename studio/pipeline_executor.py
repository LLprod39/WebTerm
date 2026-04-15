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

import asyncio
import contextlib
import json
import logging
import re
import secrets
import threading
from collections import defaultdict, deque
from datetime import timedelta
from threading import Event
from typing import Any

import httpx
from asgiref.sync import sync_to_async as _s2a
from channels.layers import get_channel_layer
from django.utils import timezone

from app.agent_kernel.domain.roles import ROLE_SPECS
from app.agent_kernel.domain.specs import ToolSpec
from app.agent_kernel.hooks.manager import HookManager
from app.agent_kernel.memory.compaction import compact_text
from app.agent_kernel.memory.redaction import sanitize_observation_text
from app.agent_kernel.memory.server_cards import render_server_cards_prompt
from app.agent_kernel.memory.store import DjangoServerMemoryStore
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.runtime.context import build_ops_prompt_context
from app.agent_kernel.sandbox.manager import SandboxManager
from app.core.model_utils import resolve_provider_and_model
from core_ui.activity import log_user_activity_async
from core_ui.audit import audit_context
from servers.mcp_tool_runtime import MCPBoundTool

from .mcp_client import call_mcp_tool
from .models import PipelineRun
from .pipeline_runtime import is_runtime_stop_requested, register_executor, unregister_executor
from .pipeline_validation import validate_pipeline_definition
from .skill_policy import apply_skill_policies, compile_skill_policies
from .skill_registry import normalise_skill_slugs, resolve_skills

logger = logging.getLogger(__name__)
_SIMPLE_TEMPLATE_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_PIPELINE_MEMORY_STORE = DjangoServerMemoryStore()
_TELEGRAM_UPDATE_OFFSETS: dict[str, int] = {}
_TELEGRAM_UPDATE_LOCKS: dict[str, threading.Lock] = {}
_TELEGRAM_PENDING_CALLBACKS: dict[str, dict[str, Any]] = {}
_TELEGRAM_PENDING_REPLIES: dict[str, list[dict[str, Any]]] = {}


def _s2a_fn(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


def _telegram_approval_callback_data(decision: str, approval_token: str) -> str:
    return f"approval:{decision}:{approval_token}"


def _parse_telegram_approval_callback_data(value: str) -> dict[str, str] | None:
    raw = str(value or "").strip()
    if not raw.startswith("approval:"):
        return None
    parts = raw.split(":", 2)
    if len(parts) != 3:
        return None
    _, decision, token = parts
    if decision not in {"approved", "rejected"} or not token:
        return None
    return {"decision": decision, "token": token}


def _telegram_reply_key(chat_id: str, reply_to_message_id: int) -> str:
    return f"{chat_id}:{reply_to_message_id}"


def _telegram_update_lock(bot_token: str) -> threading.Lock:
    lock = _TELEGRAM_UPDATE_LOCKS.get(bot_token)
    if lock is None:
        lock = threading.Lock()
        _TELEGRAM_UPDATE_LOCKS[bot_token] = lock
    return lock


def _pop_telegram_reply(chat_id: str, reply_to_message_id: int) -> dict[str, Any] | None:
    key = _telegram_reply_key(chat_id, reply_to_message_id)
    queued = _TELEGRAM_PENDING_REPLIES.get(key) or []
    if not queued:
        return None
    item = queued.pop(0)
    if queued:
        _TELEGRAM_PENDING_REPLIES[key] = queued
    else:
        _TELEGRAM_PENDING_REPLIES.pop(key, None)
    return item


async def _poll_telegram_updates(bot_token: str) -> None:
    if not bot_token:
        return

    lock = _telegram_update_lock(bot_token)
    await asyncio.to_thread(lock.acquire)
    try:
        offset = int(_TELEGRAM_UPDATE_OFFSETS.get(bot_token, 0) or 0)
        base_url = f"https://api.telegram.org/bot{bot_token}"
        max_update_id = offset - 1

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{base_url}/getUpdates",
                    json={
                        "offset": offset,
                        "timeout": 0,
                        "allowed_updates": ["callback_query", "message"],
                    },
                )
                if response.status_code != 200:
                    logger.warning(
                        "Telegram polling failed for bot %s: %s %s",
                        bot_token[:8],
                        response.status_code,
                        response.text[:200],
                    )
                    return

                payload = response.json()
                if not payload.get("ok"):
                    logger.warning("Telegram polling returned not-ok payload for bot %s", bot_token[:8])
                    return

                for update in payload.get("result") or []:
                    try:
                        update_id = int(update.get("update_id"))
                    except (TypeError, ValueError):
                        update_id = None
                    if update_id is not None:
                        max_update_id = max(max_update_id, update_id)

                    callback = update.get("callback_query") or {}
                    parsed = _parse_telegram_approval_callback_data(callback.get("data"))
                    callback_id = str(callback.get("id") or "").strip()
                    if callback_id and parsed:
                        with contextlib.suppress(Exception):
                            await client.post(
                                f"{base_url}/answerCallbackQuery",
                                json={"callback_query_id": callback_id, "text": "Решение получено"},
                            )
                    if parsed:
                        _TELEGRAM_PENDING_CALLBACKS[parsed["token"]] = {
                            "decision": parsed["decision"],
                            "response_text": "через кнопку в Telegram",
                            "callback_query_id": callback_id,
                            "callback_from": ((callback.get("from") or {}) or {}).get("username") or "",
                        }

                    message = update.get("message") or {}
                    if not isinstance(message, dict):
                        continue
                    reply_to = message.get("reply_to_message") or {}
                    chat = message.get("chat") or {}
                    text = str(message.get("text") or "").strip()
                    chat_id = str(chat.get("id") or "").strip()
                    try:
                        reply_to_message_id = int(reply_to.get("message_id"))
                    except (TypeError, ValueError):
                        reply_to_message_id = 0
                    if not chat_id or reply_to_message_id <= 0 or not text:
                        continue
                    key = _telegram_reply_key(chat_id, reply_to_message_id)
                    _TELEGRAM_PENDING_REPLIES.setdefault(key, []).append(
                        {
                            "text": text,
                            "chat_id": chat_id,
                            "message_id": message.get("message_id"),
                            "reply_to_message_id": reply_to_message_id,
                            "from_username": ((message.get("from") or {}) or {}).get("username") or "",
                        }
                    )
        except Exception as exc:
            logger.warning("Telegram polling error for bot %s: %s", bot_token[:8], exc)
            return
        finally:
            next_offset = max_update_id + 1
            if next_offset > offset:
                _TELEGRAM_UPDATE_OFFSETS[bot_token] = next_offset
    finally:
        lock.release()


async def _poll_telegram_approval_decision(bot_token: str, approval_token: str) -> dict[str, Any] | None:
    if not bot_token or not approval_token:
        return None

    cached = _TELEGRAM_PENDING_CALLBACKS.pop(approval_token, None)
    if cached:
        return cached

    await _poll_telegram_updates(bot_token)
    return _TELEGRAM_PENDING_CALLBACKS.pop(approval_token, None)


async def _poll_telegram_reply_message(bot_token: str, chat_id: str, reply_to_message_id: int) -> dict[str, Any] | None:
    if not bot_token or not chat_id or reply_to_message_id <= 0:
        return None

    cached = _pop_telegram_reply(chat_id, reply_to_message_id)
    if cached:
        return cached

    await _poll_telegram_updates(bot_token)
    return _pop_telegram_reply(chat_id, reply_to_message_id)


def _merge_unique_strings(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            value = str(item or "").strip()
            if not value:
                continue
            lowered = value.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            merged.append(value)
    return merged


def _render_template_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        # Use a narrow placeholder syntax ({name}) so JSON examples and object braces
        # inside prompts/templates do not break interpolation.
        return _SIMPLE_TEMPLATE_PATTERN.sub(lambda match: str(context.get(match.group(1), "")), value)
    if isinstance(value, list):
        return [_render_template_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: _render_template_value(item, context) for key, item in value.items()}
    return value


def _coerce_mcp_arguments(config: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    raw_text = str(config.get("arguments_text") or "").strip()
    if raw_text:
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return None, f"Invalid MCP arguments JSON: {exc}"
        if not isinstance(parsed, dict):
            return None, "MCP arguments must be a JSON object"
        return parsed, None

    raw_arguments = config.get("arguments")
    if isinstance(raw_arguments, dict):
        return raw_arguments, None
    if raw_arguments in (None, ""):
        return {}, None
    return None, "MCP arguments must be a JSON object"


def _pipeline_actor_context(run: PipelineRun) -> dict[str, Any]:
    fields_cache = getattr(getattr(run, "_state", None), "fields_cache", {}) or {}
    actor = fields_cache.get("triggered_by")
    pipeline = fields_cache.get("pipeline")

    user_id = getattr(run, "triggered_by_id", None)
    username = ""

    if actor is not None:
        user_id = getattr(actor, "id", user_id)
        username = str(getattr(actor, "username", "") or "").strip()

    if user_id is None and pipeline is not None:
        owner = getattr(getattr(pipeline, "_state", None), "fields_cache", {}).get("owner")
        user_id = getattr(pipeline, "owner_id", None)
        if owner is not None:
            user_id = getattr(owner, "id", user_id)
            username = str(getattr(owner, "username", "") or "").strip()

    pipeline_name = ""
    if pipeline is not None:
        pipeline_name = str(getattr(pipeline, "name", "") or "").strip()
    return {
        "user_id": user_id,
        "username_snapshot": username,
        "channel": "pipeline",
        "path": f"/api/studio/pipelines/{run.pipeline_id}/run/",
        "entity_type": "pipeline_run",
        "entity_id": str(run.pk),
        "entity_name": pipeline_name or f"pipeline-run-{run.pk}",
    }


def _save_server_command_history(*, server_id: int, user_id: int | None, command: str, output: str, exit_code: int | None) -> None:
    from servers.models import ServerCommandHistory

    ServerCommandHistory.objects.create(
        server_id=server_id,
        user_id=user_id,
        command=command,
        output=(output or "")[:10000],
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
    actor_ctx = _pipeline_actor_context(run)
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


def _mcp_result_to_text(result: dict[str, Any]) -> str:
    parts: list[str] = []

    for item in result.get("content") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and item.get("text"):
            parts.append(str(item["text"]))
        elif item.get("type") == "json" and "json" in item:
            parts.append(json.dumps(item["json"], ensure_ascii=False, indent=2))
        elif item.get("type") == "image":
            parts.append("[MCP returned image content]")

    structured = result.get("structuredContent")
    if structured is not None and not parts:
        parts.append(json.dumps(structured, ensure_ascii=False, indent=2))

    if not parts:
        parts.append(json.dumps(result, ensure_ascii=False, indent=2))

    return "\n\n".join(part for part in parts if part)


async def _load_owned_servers(owner, server_ids: list[int]):
    from servers.models import Server

    if not server_ids:
        return []
    return await _s2a_fn(lambda: list(Server.objects.filter(id__in=server_ids, user=owner)))()


async def _load_owned_agent_config(owner, agent_config_id: int):
    from studio.models import AgentConfig

    return await _s2a_fn(
        lambda: AgentConfig.objects.filter(id=agent_config_id, owner=owner).prefetch_related("mcp_servers", "server_scope").first()
    )()


async def _load_agent_scope_ids(agent_conf) -> set[int]:
    if not agent_conf:
        return set()
    owner = getattr(agent_conf, "owner", None)
    return set(await _s2a_fn(lambda: list(agent_conf.server_scope.filter(user=owner).values_list("id", flat=True)))())


def _pipeline_permission_mode(config: dict[str, Any]) -> str:
    mode = str(config.get("permission_mode") or "").strip().upper()
    if mode in {"PLAN", "SAFE", "ASSISTED", "AUTONOMOUS", "AUTO_GUARDED"}:
        return mode
    return "SAFE"


def _pipeline_role_slug(config: dict[str, Any]) -> str:
    role = str(config.get("role") or "").strip()
    if role in ROLE_SPECS:
        return role
    if config.get("watcher"):
        return "watcher_daemon"
    return "custom"


async def _load_pipeline_server_memory(owner, config: dict[str, Any], context: dict[str, Any]) -> str:
    raw_server_ids = config.get("server_ids") or []
    if config.get("server_id") and not raw_server_ids:
        raw_server_ids = [config.get("server_id")]

    server_ids: list[int] = []
    for value in raw_server_ids[:3]:
        try:
            server_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    if not server_ids and context.get("target_server_id"):
        with contextlib.suppress(TypeError, ValueError):
            server_ids.append(int(context.get("target_server_id")))

    if not server_ids:
        return "Память по серверам для этого pipeline node не выбрана."

    cards = []
    servers = await _load_owned_servers(owner, server_ids)
    for server in servers[:3]:
        try:
            cards.append(await _PIPELINE_MEMORY_STORE.get_server_card(server.id))
        except Exception as exc:
            logger.debug("Failed to load pipeline server memory for %s: %s", server.id, exc)
    return render_server_cards_prompt(cards, max_cards=3, max_records=5)


async def _load_pipeline_operational_recipes(
    owner,
    config: dict[str, Any],
    context: dict[str, Any],
    *,
    role_slug: str,
    query: str,
) -> str:
    raw_server_ids = config.get("server_ids") or []
    if config.get("server_id") and not raw_server_ids:
        raw_server_ids = [config.get("server_id")]

    server_ids: list[int] = []
    for value in raw_server_ids[:3]:
        try:
            server_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    if not server_ids and context.get("target_server_id"):
        with contextlib.suppress(TypeError, ValueError):
            server_ids.append(int(context.get("target_server_id")))

    group_ids: list[int] = []
    if server_ids:
        for server in await _load_owned_servers(owner, server_ids):
            if getattr(server, "group_id", None):
                group_ids.append(server.group_id)

    recipe_query = "\n".join(part for part in [query, role_slug] if part).strip()
    return await _PIPELINE_MEMORY_STORE.build_operational_recipes_prompt(
        recipe_query,
        server_ids=server_ids,
        group_ids=list(dict.fromkeys(group_ids)),
        limit=4,
    )


def _compact_node_outputs_context(node_outputs: dict[str, dict], *, max_nodes: int = 6, max_chars: int = 1200) -> str:
    lines: list[str] = []
    for nid, out in list(node_outputs.items())[-max_nodes:]:
        sanitized_output = sanitize_observation_text(str(out.get("output") or "").strip()).text
        output_text = compact_text(sanitized_output, limit=max_chars)
        if output_text:
            lines.append(f"=== Output of node [{nid}] ===\n{output_text}")
    return "\n\n".join(lines)


def _build_pipeline_tool_spec(tool_name: str, *, command: str = "") -> ToolSpec:
    lowered_name = (tool_name or "").lower()
    lowered_command = (command or "").lower()
    category = "general"
    risk = "read"
    mutates_state = False
    requires_verification = False

    if lowered_name in {"ssh_execute", "agent/ssh_cmd", "ssh_cmd"} or command:
        category = "ssh"
        risk = "exec"
        requires_verification = True
    elif "keycloak" in lowered_name:
        category = "keycloak"
        risk = "admin"
        mutates_state = True
        requires_verification = True
    elif "docker" in lowered_name or "docker" in lowered_command:
        category = "docker"
        risk = "exec"
        requires_verification = True
    elif "nginx" in lowered_name or "nginx" in lowered_command:
        category = "nginx"
        risk = "exec"
        requires_verification = True
    elif "service" in lowered_name or "systemctl" in lowered_command:
        category = "service"
        risk = "exec"
        requires_verification = True
    elif lowered_name.startswith("mcp"):
        category = "mcp"
        risk = "network"

    return ToolSpec(
        name=tool_name or "pipeline_tool",
        category=category,
        risk=risk,
        description=f"Pipeline node tool: {tool_name}",
        input_schema={},
        mutates_state=mutates_state,
        requires_verification=requires_verification,
        output_compactor="tail",
        runner="pipeline",
    )


def _build_pipeline_ops_context(
    *,
    role_slug: str,
    permission_mode: str,
    server_memory_prompt: str,
    operational_recipes_prompt: str,
    tool_spec_lines: str,
    max_iterations: int,
) -> str:
    role_spec = ROLE_SPECS.get(role_slug, ROLE_SPECS["custom"])
    return build_ops_prompt_context(
        role_spec=role_spec,
        permission_mode=permission_mode,
        server_memory_prompt=server_memory_prompt,
        operational_recipes_prompt=operational_recipes_prompt,
        tool_registry_prompt=tool_spec_lines,
        max_iterations=max_iterations,
        session_timeout=0,
    )


# ---------------------------------------------------------------------------
# Topological sort (Kahn's algorithm)
# ---------------------------------------------------------------------------


def _topo_sort(nodes: list[dict], edges: list[dict]) -> list[list[dict]]:
    """
    Returns nodes in execution layers (BFS topological order).
    Nodes in the same layer can run in parallel.
    """
    id_to_node = {n["id"]: n for n in nodes}
    in_degree: dict[str, int] = defaultdict(int)
    children: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        src = edge["source"]
        dst = edge["target"]
        children[src].append(dst)
        in_degree[dst] += 1

    # Nodes with no incoming edges (triggers / entry points)
    queue: deque[str] = deque(nid for nid in id_to_node if in_degree[nid] == 0)
    layers: list[list[dict]] = []

    while queue:
        layer_size = len(queue)
        layer: list[dict] = []
        for _ in range(layer_size):
            nid = queue.popleft()
            layer.append(id_to_node[nid])
            for child in children[nid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)
        if layer:
            layers.append(layer)

    return layers


def _graph_edge_handle(edge: dict[str, Any]) -> str:
    return str(edge.get("sourceHandle") or "").strip() or "out"


def _possible_routing_ports(node_type: str) -> set[str]:
    if node_type.startswith("trigger/"):
        return {"out"}
    if node_type == "logic/condition":
        return {"true", "false"}
    if node_type == "logic/parallel":
        return {"out"}
    if node_type == "logic/merge":
        return {"out"}
    if node_type == "logic/wait":
        return {"done", "out"}
    if node_type == "logic/human_approval":
        return {"approved", "rejected", "timeout"}
    if node_type == "logic/telegram_input":
        return {"received", "timeout"}
    if node_type.startswith("agent/") or node_type.startswith("output/"):
        return {"success", "error", "out"}
    return {"out"}


def _routing_ports_for_state(node_type: str, state: dict[str, Any] | None) -> set[str]:
    if isinstance(state, dict):
        raw = state.get("routing_ports")
        if isinstance(raw, list) and raw:
            return {str(item).strip() for item in raw if str(item).strip()}
    return _possible_routing_ports(node_type)


def _result_routing_ports(node: dict[str, Any], result: dict[str, Any]) -> list[str]:
    node_type = str(node.get("type") or "")
    status = str(result.get("status") or "")
    if status == "stopped":
        return []
    if node_type == "logic/condition":
        return ["true"] if bool(result.get("passed")) else ["false"]
    if node_type == "logic/parallel":
        return ["out"]
    if node_type == "logic/merge":
        return ["out"]
    if node_type == "logic/wait":
        return ["done", "out"] if status == "completed" else []
    if node_type == "logic/human_approval":
        decision = str(result.get("decision") or "").strip()
        return [decision] if decision in {"approved", "rejected", "timeout"} else []
    if node_type == "logic/telegram_input":
        decision = str(result.get("decision") or "").strip()
        return [decision] if decision in {"received", "timeout"} else []
    if node_type.startswith("agent/") or node_type.startswith("output/"):
        if status == "completed":
            return ["success", "out"]
        if status == "failed":
            return ["error"]
        return []
    return ["out"] if status == "completed" else []


def _serialize_routing_state(
    *,
    entry_node_id: str,
    activated_nodes: set[str],
    completed_nodes: set[str],
    queued_nodes: set[str],
    pending_merges: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    serialized_merges: dict[str, dict[str, Any]] = {}
    for node_id, item in pending_merges.items():
        serialized_merges[node_id] = {
            "mode": str(item.get("mode") or "all"),
            "arrived_sources": sorted(str(source) for source in (item.get("arrived_sources") or set())),
            "possible_sources": sorted(str(source) for source in (item.get("possible_sources") or set())),
            "released": bool(item.get("released")),
        }
    return {
        "entry_node_id": str(entry_node_id or ""),
        "activated_nodes": sorted(activated_nodes),
        "completed_nodes": sorted(completed_nodes),
        "queued_nodes": sorted(queued_nodes),
        "pending_merges": serialized_merges,
    }


def _reachable_nodes_from_entry(
    *,
    entry_node_id: str,
    id_to_node: dict[str, dict[str, Any]],
    outgoing_edges: dict[str, list[dict[str, Any]]],
    node_states: dict[str, dict[str, Any]],
) -> set[str]:
    if not entry_node_id or entry_node_id not in id_to_node:
        return set()
    visited: set[str] = set()
    queue: deque[str] = deque([entry_node_id])
    while queue:
        node_id = queue.popleft()
        if node_id in visited:
            continue
        visited.add(node_id)
        node_type = str(id_to_node[node_id].get("type") or "")
        allowed_ports = _routing_ports_for_state(node_type, node_states.get(node_id))
        for edge in outgoing_edges.get(node_id, []):
            if _graph_edge_handle(edge) not in allowed_ports:
                continue
            target = str(edge.get("target") or "")
            if target and target not in visited:
                queue.append(target)
    return visited


def _possible_merge_sources(
    *,
    merge_node_id: str,
    entry_node_id: str,
    id_to_node: dict[str, dict[str, Any]],
    incoming_edges: dict[str, list[dict[str, Any]]],
    outgoing_edges: dict[str, list[dict[str, Any]]],
    node_states: dict[str, dict[str, Any]],
) -> set[str]:
    reachable = _reachable_nodes_from_entry(
        entry_node_id=entry_node_id,
        id_to_node=id_to_node,
        outgoing_edges=outgoing_edges,
        node_states=node_states,
    )
    possible: set[str] = set()
    for edge in incoming_edges.get(merge_node_id, []):
        source = str(edge.get("source") or "")
        if not source or source not in reachable or source not in id_to_node:
            continue
        source_type = str(id_to_node[source].get("type") or "")
        allowed_ports = _routing_ports_for_state(source_type, node_states.get(source))
        if _graph_edge_handle(edge) in allowed_ports:
            possible.add(source)
    return possible


# ---------------------------------------------------------------------------
# Node executor helpers
# ---------------------------------------------------------------------------


async def _execute_agent_react(node: dict, context: dict, run: PipelineRun) -> dict:
    """Execute an agent/react node using AgentEngine."""
    from servers.agent_engine import AgentEngine
    from servers.models import AgentRun, ServerAgent

    config = node.get("data", {})
    node_id = node.get("id")
    agent_config_id = config.get("agent_config_id")
    server_ids = config.get("server_ids", [])
    mcp_server_ids = config.get("mcp_server_ids", [])
    node_skill_slugs = normalise_skill_slugs(config.get("skill_slugs"))
    goal = config.get("goal", "")
    owner = await _s2a_fn(lambda: run.pipeline.owner)()

    # Substitute known context values and leave missing ones blank.
    goal = _render_template_value(goal, context)

    servers = await _load_owned_servers(owner, server_ids) if server_ids else []

    # Create a temporary ServerAgent from AgentConfig or inline config
    if agent_config_id:
        try:
            agent_conf_pk = int(agent_config_id)
        except (TypeError, ValueError):
            return {"status": "failed", "error": f"Invalid agent config id: {agent_config_id}"}
        agent_conf = await _load_owned_agent_config(owner, agent_conf_pk)
        if agent_conf is None:
            return {"status": "failed", "error": f"Agent config not found: {agent_config_id}"}
        system_prompt = _render_template_value(agent_conf.system_prompt, context)
        instructions = _render_template_value(agent_conf.instructions, context)
        max_iterations = agent_conf.max_iterations
        model = agent_conf.model
        tools_config = dict.fromkeys(agent_conf.allowed_tools or [], True)
        mcp_servers = await _s2a_fn(lambda: list(agent_conf.mcp_servers.filter(owner=owner)))()
        skill_slugs = _merge_unique_strings(list(agent_conf.skill_slugs or []), node_skill_slugs)
        allowed_server_ids = await _load_agent_scope_ids(agent_conf)
        if allowed_server_ids:
            disallowed = [server_id for server_id in server_ids if server_id not in allowed_server_ids]
            if disallowed:
                return {
                    "status": "failed",
                    "error": f"Node references servers outside agent scope: {disallowed}",
                }
    else:
        system_prompt = _render_template_value(config.get("system_prompt", ""), context)
        instructions = _render_template_value(config.get("instructions", ""), context)
        max_iterations = config.get("max_iterations", 10)
        model = config.get("model", "gemini-2.0-flash-exp")
        tools_config = dict.fromkeys(config.get("allowed_tools", []) or [], True)
        from .models import MCPServerPool

        mcp_servers = (
            await _s2a_fn(lambda: list(MCPServerPool.objects.filter(id__in=mcp_server_ids, owner=owner)))()
            if mcp_server_ids
            else []
        )
        skill_slugs = node_skill_slugs

    skills, skill_errors = resolve_skills(skill_slugs)

    if server_ids and not servers:
        return {"status": "failed", "error": f"Servers not found: {server_ids}"}
    if not servers and not mcp_servers and not skills:
        return {"status": "failed", "error": "Configure at least one server, one MCP server, or one skill for this agent node"}

    model_preference, specific_model = resolve_provider_and_model(
        config.get("provider"),
        model,
        default_provider="auto",
    )

    sa = ServerAgent(
        name=f"pipeline_node_{node['id']}",
        mode=ServerAgent.MODE_FULL,
        goal=goal,
        system_prompt=system_prompt,
        ai_prompt=instructions,
        max_iterations=max_iterations,
        tools_config=tools_config,
        allow_multi_server=len(servers) > 1,
    )

    engine = AgentEngine(
        agent=sa,
        servers=servers,
        user=owner,
        event_callback=_make_run_event_callback(run, node["id"]),
        model_preference=model_preference,
        specific_model=specific_model,
        mcp_servers=mcp_servers,
        skills=skills,
        skill_errors=skill_errors,
    )

    logger.info(
        "pipeline run %s node %s agent/react start: provider=%s model=%s servers=%s mcp_servers=%s skills=%s",
        run.pk,
        node_id,
        model_preference,
        specific_model,
        [srv.name for srv in servers],
        [srv.name for srv in mcp_servers],
        [skill.slug for skill in skills],
    )
    agent_run: AgentRun = await engine.run()
    logger.info(
        "pipeline run %s node %s agent/react done: agent_run_id=%s status=%s report_chars=%s",
        run.pk,
        node_id,
        agent_run.pk,
        agent_run.status,
        len(agent_run.final_report or ""),
    )
    return {
        "status": "completed" if agent_run.status == "completed" else "failed",
        "agent_run_id": agent_run.pk,
        "output": agent_run.final_report or "",
        "error": agent_run.ai_analysis if agent_run.status != "completed" else "",
    }


async def _execute_agent_multi(node: dict, context: dict, run: PipelineRun) -> dict:
    """Execute an agent/multi node using MultiAgentEngine."""
    from servers.models import ServerAgent
    from servers.multi_agent_engine import MultiAgentEngine

    config = node.get("data", {})
    server_ids = config.get("server_ids", [])
    mcp_server_ids = config.get("mcp_server_ids", [])
    node_skill_slugs = normalise_skill_slugs(config.get("skill_slugs"))
    goal = config.get("goal", "")
    owner = await _s2a_fn(lambda: run.pipeline.owner)()

    goal = _render_template_value(goal, context)

    servers = await _load_owned_servers(owner, server_ids) if server_ids else []

    agent_config_id = config.get("agent_config_id")
    if agent_config_id:
        try:
            agent_conf_pk = int(agent_config_id)
        except (TypeError, ValueError):
            return {"status": "failed", "error": f"Invalid agent config id: {agent_config_id}"}
        agent_conf = await _load_owned_agent_config(owner, agent_conf_pk)
        if agent_conf is None:
            return {"status": "failed", "error": f"Agent config not found: {agent_config_id}"}
        system_prompt = _render_template_value(agent_conf.system_prompt, context)
        max_iterations = agent_conf.max_iterations
        model = agent_conf.model
        tools_config = dict.fromkeys(agent_conf.allowed_tools or [], True)
        mcp_servers = await _s2a_fn(lambda: list(agent_conf.mcp_servers.filter(owner=owner)))()
        skill_slugs = _merge_unique_strings(list(agent_conf.skill_slugs or []), node_skill_slugs)
        allowed_server_ids = await _load_agent_scope_ids(agent_conf)
        if allowed_server_ids:
            disallowed = [server_id for server_id in server_ids if server_id not in allowed_server_ids]
            if disallowed:
                return {
                    "status": "failed",
                    "error": f"Node references servers outside agent scope: {disallowed}",
                }
    else:
        system_prompt = _render_template_value(config.get("system_prompt", ""), context)
        max_iterations = config.get("max_iterations", 20)
        model = config.get("model", "gemini-2.0-flash-exp")
        tools_config = dict.fromkeys(config.get("allowed_tools", []) or [], True)
        from .models import MCPServerPool

        mcp_servers = (
            await _s2a_fn(lambda: list(MCPServerPool.objects.filter(id__in=mcp_server_ids, owner=owner)))()
            if mcp_server_ids
            else []
        )
        skill_slugs = node_skill_slugs

    skills, skill_errors = resolve_skills(skill_slugs)

    if server_ids and not servers:
        return {"status": "failed", "error": f"Servers not found: {server_ids}"}
    if not servers and not mcp_servers and not skills:
        return {
            "status": "failed",
            "error": "Configure at least one server, one MCP server, or one skill for this multi agent node",
        }

    model_preference, specific_model = resolve_provider_and_model(
        config.get("provider"),
        model,
        default_provider="auto",
    )

    sa = ServerAgent(
        name=f"pipeline_multi_{node['id']}",
        mode=ServerAgent.MODE_MULTI,
        goal=goal,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        tools_config=tools_config,
        allow_multi_server=True,
    )

    engine = MultiAgentEngine(
        agent=sa,
        servers=servers,
        user=owner,
        event_callback=_make_run_event_callback(run, node["id"]),
        model_preference=model_preference,
        specific_model=specific_model,
        mcp_servers=mcp_servers,
        skills=skills,
        skill_errors=skill_errors,
    )

    agent_run = await engine.run()
    return {
        "status": "completed" if agent_run.status == "completed" else "failed",
        "agent_run_id": agent_run.pk,
        "output": agent_run.final_report or "",
        "error": agent_run.ai_analysis if agent_run.status != "completed" else "",
    }


async def _execute_agent_ssh_cmd(node: dict, context: dict, run: PipelineRun) -> dict:
    """Execute a direct SSH command without LLM."""
    import asyncssh

    from servers.models import Server

    config = node.get("data", {})
    server_id = config.get("server_id")
    command = config.get("command", "")
    preflight_commands = list(config.get("preflight_commands") or [])
    verification_commands = list(config.get("verification_commands") or [])

    with contextlib.suppress(KeyError, ValueError):
        command = command.format(**context)

    if not server_id:
        return {
            "status": "skipped",
            "output": "⚠️ No server configured for this SSH node. Click the node → select a Server in the config panel.",
        }
    if not command:
        # If an AgentConfig is attached, the node was likely meant to be agent/react — delegate.
        # Normalise server_id → server_ids so _execute_agent_react finds the server.
        if config.get("agent_config_id") or config.get("goal"):
            patched_node = dict(node)
            patched_data = dict(config)
            if server_id and not patched_data.get("server_ids"):
                patched_data["server_ids"] = [server_id]
            patched_node["data"] = patched_data
            return await _execute_agent_react(patched_node, context, run)
        return {
            "status": "failed",
            "error": "Команда не задана. Откройте узел в редакторе и введите команду в поле «Command», "
                     "или смените тип узла на «ReAct Agent» если нужен ИИ-агент.",
        }

    owner = await _s2a_fn(lambda: run.pipeline.owner)()
    try:
        server = await _s2a_fn(Server.objects.get)(id=server_id, user=owner)
    except Server.DoesNotExist:
        return {"status": "failed", "error": f"Server not found: {server_id}"}

    permission_engine = PermissionEngine(mode=_pipeline_permission_mode(config))
    sandbox_manager = SandboxManager()
    hook_manager = HookManager()
    spec = _build_pipeline_tool_spec("ssh_execute", command=command)
    decision = permission_engine.evaluate(spec, {"command": command})
    if not decision.allowed and not preflight_commands:
        return {
            "status": "failed",
            "error": decision.reason,
            "output": "",
        }

    try:
        from servers.monitor import _build_connect_kwargs

        connect_kwargs = await _build_connect_kwargs(server)
        connect_kwargs["connect_timeout"] = 30

        async with asyncssh.connect(**connect_kwargs) as conn:
            combined_outputs: list[str] = []

            async def _run_remote_command(command_text: str, *, stage: str) -> tuple[int, str]:
                stage_profile = decision.sandbox_profile if stage == "command" else "ops_read"
                sandbox_decision = sandbox_manager.validate(spec, {"command": command_text}, stage_profile)
                if not sandbox_decision.allowed:
                    raise RuntimeError(sandbox_decision.reason)
                remote_result = await conn.run(command_text, timeout=120)
                remote_output = remote_result.stdout + (("\n" + remote_result.stderr) if remote_result.stderr else "")
                compacted_output = await hook_manager.post_tool_use("ssh_execute", remote_output)
                permission_engine.record_success(spec, {"command": command_text}, compacted_output)
                await _log_pipeline_ssh_command(
                    run=run,
                    server=server,
                    node_id=str(node.get("id") or ""),
                    command=f"[{stage}] {command_text}",
                    exit_code=remote_result.exit_status,
                    output=compacted_output,
                )
                combined_outputs.append(f"## {stage}\n{compacted_output}")
                return remote_result.exit_status, compacted_output

            for preflight_command in preflight_commands:
                rendered = _render_template_value(preflight_command, context)
                exit_code, _ = await _run_remote_command(str(rendered), stage="preflight")
                if exit_code != 0:
                    return {
                        "status": "failed",
                        "error": f"Preflight command failed: {rendered}",
                        "output": "\n\n".join(combined_outputs),
                    }

            decision = permission_engine.evaluate(spec, {"command": command})
            if not decision.allowed:
                return {"status": "failed", "error": decision.reason, "output": "\n\n".join(combined_outputs)}

            exit_code, output = await _run_remote_command(command, stage="command")
            verification_summary = permission_engine.verification_summary()
            if verification_commands:
                for verify_command in verification_commands:
                    rendered = _render_template_value(verify_command, context)
                    verify_exit_code, _ = await _run_remote_command(str(rendered), stage="verification")
                    if verify_exit_code != 0:
                        return {
                            "status": "failed",
                            "error": f"Verification command failed: {rendered}",
                            "output": "\n\n".join(combined_outputs),
                        }
                verification_summary = permission_engine.verification_summary()
                combined_outputs.append(f"## verification_summary\n{verification_summary}")

            full_output = "\n\n".join(combined_outputs) if combined_outputs else output
            return {
                "status": "completed" if exit_code == 0 else "failed",
                "output": full_output,
                "exit_code": exit_code,
                "verification_summary": verification_summary,
                "error": "" if exit_code == 0 else output,
            }
    except Exception as exc:
        error_text = f"{exc} (server: {server.name} [{server.username}@{server.host}])"
        await _log_pipeline_ssh_command(
            run=run,
            server=server,
            node_id=str(node.get("id") or ""),
            command=command,
            exit_code=-1,
            error=error_text,
        )
        return {
            "status": "failed",
            "error": error_text,
        }


def _resolve_llm_provider_and_model(config: dict) -> tuple[str, str]:
    provider, model = resolve_provider_and_model(
        config.get("provider"),
        config.get("model"),
        default_provider="gemini",
    )
    return provider, model or "gemini-2.0-flash-exp"


async def _execute_agent_llm_query(node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun) -> dict:
    """
    Direct LLM query — no SSH needed.
    Sends a prompt (with all previous node outputs as context) to the chosen provider (Gemini, OpenAI, Grok, Claude)
    and returns the response.
    """
    import time

    config = node.get("data", {})
    prompt_template = config.get("prompt", "")
    system_prompt = config.get("system_prompt", "You are a helpful DevOps assistant.")
    include_all_outputs = config.get("include_all_outputs", True)
    purpose = str(config.get("purpose") or "opssummary").strip() or "opssummary"
    permission_mode = _pipeline_permission_mode(config)
    role_slug = _pipeline_role_slug(config)
    max_context_nodes = max(1, min(int(config.get("max_context_nodes", 6) or 6), 12))
    max_output_context_chars = max(200, min(int(config.get("max_output_chars", 1200) or 1200), 4000))
    provider, specific_model = _resolve_llm_provider_and_model(config)

    if not prompt_template:
        return {"status": "failed", "error": "No prompt configured for llm_query node"}

    # Build rich context string from all previous node outputs
    outputs_context = (
        _compact_node_outputs_context(node_outputs, max_nodes=max_context_nodes, max_chars=max_output_context_chars)
        if include_all_outputs
        else ""
    )

    substitutions = dict(context)
    substitutions["all_outputs"] = outputs_context
    prompt = _render_template_value(prompt_template, substitutions)

    owner = await _s2a_fn(lambda: run.pipeline.owner)()
    server_memory_prompt = await _load_pipeline_server_memory(owner, config, context)
    operational_recipes_prompt = await _load_pipeline_operational_recipes(
        owner,
        config,
        context,
        role_slug=role_slug,
        query=prompt,
    )
    ops_context = _build_pipeline_ops_context(
        role_slug=role_slug,
        permission_mode=permission_mode,
        server_memory_prompt=server_memory_prompt,
        operational_recipes_prompt=operational_recipes_prompt,
        tool_spec_lines="- llm_query: reasoning / summarization / planning [general / read]",
        max_iterations=1,
    )

    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    if outputs_context and "{all_outputs}" not in prompt_template and include_all_outputs:
        full_prompt = f"{system_prompt}\n\n{ops_context}\n\n## Context from previous pipeline steps:\n{outputs_context}\n\n## Your task:\n{prompt}"
    else:
        full_prompt = f"{system_prompt}\n\n{ops_context}\n\n{prompt}" if system_prompt else f"{ops_context}\n\n{prompt}"

    try:
        from app.core.llm import LLMProvider

        t0 = time.time()
        llm = LLMProvider()
        output_chunks: list[str] = []
        async for chunk in llm.stream_chat(
            full_prompt,
            model=provider,
            specific_model=specific_model or None,
            purpose=purpose,
        ):
            output_chunks.append(chunk)
        output_text = compact_text("".join(output_chunks), limit=6000)
        elapsed = int((time.time() - t0) * 1000)
        logger.info("llm_query node %s: %s/%s %.1fs, %d chars", node.get("id"), provider, specific_model, elapsed / 1000, len(output_text))

        if output_text.strip().startswith("Error:"):
            return {"status": "failed", "error": output_text.strip(), "output": output_text}
        return {"status": "completed", "output": output_text}
    except Exception as exc:
        logger.exception("llm_query node %s failed", node.get("id"))
        return {"status": "failed", "error": str(exc)}


async def _execute_agent_mcp_call(
    node: dict,
    context: dict,
    run: PipelineRun,
    executed_mcp_tools: set[str] | None = None,
) -> dict:
    """Execute a direct MCP tools/call request against a configured MCP server."""
    from .models import MCPServerPool

    config = node.get("data", {})
    owner = await _s2a_fn(lambda: run.pipeline.owner)()
    mcp_server_id = config.get("mcp_server_id")
    tool_name = str(config.get("tool_name") or "").strip()
    node_skill_slugs = normalise_skill_slugs(config.get("skill_slugs"))

    if not mcp_server_id:
        return {"status": "failed", "error": "Select an MCP server for this node"}
    if not tool_name:
        return {"status": "failed", "error": "Select an MCP tool for this node"}

    arguments_template, error = _coerce_mcp_arguments(config)
    if error:
        return {"status": "failed", "error": error}

    try:
        mcp_server = await _s2a_fn(MCPServerPool.objects.get)(id=int(mcp_server_id), owner=owner)
    except MCPServerPool.DoesNotExist:
        return {"status": "failed", "error": f"MCP server not found: {mcp_server_id}"}
    except (TypeError, ValueError):
        return {"status": "failed", "error": f"Invalid MCP server id: {mcp_server_id}"}

    arguments = _render_template_value(arguments_template or {}, context)
    skills, skill_errors = resolve_skills(node_skill_slugs)
    skill_policies, policy_errors = compile_skill_policies(skills)
    if skill_errors or policy_errors:
        return {
            "status": "failed",
            "error": f"Skill policy validation failed: {'; '.join([*skill_errors, *policy_errors])}",
        }

    binding = MCPBoundTool(
        action_name=f"pipeline_{node.get('id') or 'node'}_{tool_name}",
        server=mcp_server,
        tool_name=tool_name,
        description=f"Pipeline MCP call for {tool_name}",
        input_schema=None,
    )
    permission_engine = PermissionEngine(mode=_pipeline_permission_mode(config))
    sandbox_manager = SandboxManager()
    hook_manager = HookManager()
    spec = _build_pipeline_tool_spec(f"mcp_{tool_name}")
    decision = permission_engine.evaluate(spec, arguments)
    if not decision.allowed:
        return {"status": "failed", "error": decision.reason}
    prepared_args, policy_messages, policy_error = apply_skill_policies(
        skill_policies,
        binding,
        arguments,
        executed_mcp_tools if executed_mcp_tools is not None else set(),
    )
    if policy_error:
        return {
            "status": "failed",
            "error": policy_error,
        }
    sandbox_decision = sandbox_manager.validate(spec, prepared_args, decision.sandbox_profile)
    if not sandbox_decision.allowed:
        return {"status": "failed", "error": sandbox_decision.reason}

    try:
        logger.info(
            "pipeline run %s node %s mcp_call start: server=%s tool=%s args=%s",
            run.pk,
            node.get("id"),
            mcp_server.name,
            tool_name,
            json.dumps(prepared_args, ensure_ascii=False)[:800],
        )
        result = await call_mcp_tool(mcp_server, tool_name, prepared_args)
        output = _mcp_result_to_text(result)
        if decision.notes:
            output = "\n".join([*decision.notes, output]) if output else "\n".join(decision.notes)
        if policy_messages:
            output = "\n".join([*policy_messages, output]) if output else "\n".join(policy_messages)
        output = await hook_manager.post_tool_use(tool_name, output)
        logger.info(
            "pipeline run %s node %s mcp_call done: server=%s tool=%s is_error=%s output_chars=%s",
            run.pk,
            node.get("id"),
            mcp_server.name,
            tool_name,
            bool(result.get("isError")),
            len(output),
        )
        actor_ctx = _pipeline_actor_context(run)
        await log_user_activity_async(
            user_id=actor_ctx.get("user_id"),
            username_snapshot=str(actor_ctx.get("username_snapshot") or ""),
            category="mcp",
            action="mcp_call",
            status="error" if result.get("isError") else "success",
            description=f"{mcp_server.name}.{tool_name}",
            entity_type="pipeline_run",
            entity_id=str(run.pk),
            entity_name=actor_ctx.get("entity_name") or "",
            metadata={
                "node_id": str(node.get("id") or ""),
                "mcp_server_id": mcp_server.id,
                "mcp_server_name": mcp_server.name,
                "tool_name": tool_name,
                "arguments": prepared_args,
                "is_error": bool(result.get("isError")),
                "output_excerpt": output[:4000],
            },
        )
        if not result.get("isError"):
            permission_engine.record_success(spec, prepared_args, output)
        if result.get("isError"):
            return {
                "status": "failed",
                "error": output or f"MCP tool '{tool_name}' returned an error",
                "output": output,
                "raw_result": result,
            }
        if executed_mcp_tools is not None:
            executed_mcp_tools.add(tool_name)
        return {
            "status": "completed",
            "output": output,
            "raw_result": result,
        }
    except Exception as exc:
        logger.exception("mcp_call node %s failed", node.get("id"))
        actor_ctx = _pipeline_actor_context(run)
        await log_user_activity_async(
            user_id=actor_ctx.get("user_id"),
            username_snapshot=str(actor_ctx.get("username_snapshot") or ""),
            category="mcp",
            action="mcp_call",
            status="error",
            description=f"{mcp_server.name}.{tool_name}" if "mcp_server" in locals() else tool_name,
            entity_type="pipeline_run",
            entity_id=str(run.pk),
            entity_name=actor_ctx.get("entity_name") or "",
            metadata={
                "node_id": str(node.get("id") or ""),
                "error": str(exc),
            },
        )
        return {"status": "failed", "error": str(exc)}


async def _execute_output_email(node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun) -> dict:
    """
    Send an email report via SMTP.
    Uses Django EMAIL_* settings or per-node SMTP config.
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    from django.conf import settings

    config = node.get("data", {})
    g_to, g_host, g_user, g_pass, g_from = _global_email_defaults()

    to_email = (config.get("to_email") or g_to or "").strip()
    to_email = _normalize_email_recipient(to_email, (config.get("smtp_host") or "").strip() or g_host)
    if not to_email:
        return {
            "status": "failed",
            "error": "No recipient email. Set PIPELINE_NOTIFY_EMAIL in .env or fill in the node.",
        }

    subject_template = config.get("subject", f"Pipeline Report: {run.pipeline.name}")
    body_template = config.get("body", "")

    # context is already enriched with {nid}, {nid_output}, {nid_error} from _execute_node
    subs = dict(context)

    # Format subject
    try:
        subject = subject_template.format_map(subs)
    except (KeyError, ValueError):
        subject = subject_template

    # Build body
    if body_template:
        try:
            body = body_template.format_map(subs)
        except (KeyError, ValueError):
            body = body_template
    else:
        lines = [
            f"# Pipeline Run Report: {run.pipeline.name}",
            f"Status: {run.status}",
            "",
        ]
        for nid, state in node_outputs.items():
            if state.get("output"):
                lines.append(f"## [{nid}]")
                lines.append(state["output"][:2000])
                lines.append("")
        body = "\n".join(lines)

    # SMTP config: node overrides global Django settings which override hardcoded defaults
    smtp_host = (config.get("smtp_host") or "").strip() or g_host or getattr(settings, "EMAIL_HOST", "smtp.gmail.com")
    smtp_port = int((config.get("smtp_port") or getattr(settings, "EMAIL_PORT", 587)) or 587)
    smtp_user = (config.get("smtp_user") or "").strip() or g_user or getattr(settings, "EMAIL_HOST_USER", "")
    smtp_password = (config.get("smtp_password") or "").strip() or g_pass or getattr(settings, "EMAIL_HOST_PASSWORD", "")
    from_email = (config.get("from_email") or "").strip() or g_from or smtp_user or "pipeline@noreply.local"
    # SMTP servers (Yandex, etc.) reject sender if From is not a real mailbox on their side
    from_email = _resolve_from_email(from_email, smtp_user, smtp_host)
    use_tls = smtp_port in (587, 465)

    def _send_sync():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain", "utf-8"))
        # Try Markdown as HTML alternative
        try:
            import markdown
            html_body = markdown.markdown(body)
            msg.attach(MIMEText(f"<html><body>{html_body}</body></html>", "html", "utf-8"))
        except ImportError:
            pass

        # Port 465 = SSL from the start (Yandex, etc.); 587 = STARTTLS
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_email, to_email.split(","), msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.ehlo()
                if use_tls and smtp_port == 587:
                    server.starttls()
                    server.ehlo()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.sendmail(from_email, to_email.split(","), msg.as_string())

    try:
        await asyncio.get_event_loop().run_in_executor(None, _send_sync)
        return {"status": "completed", "output": f"✉️ Email sent to {to_email} | Subject: {subject}"}
    except Exception as exc:
        logger.warning("output/email node %s failed: %s", node.get("id"), exc)
        return {"status": "failed", "error": f"SMTP error: {exc}"}


async def _execute_logic_condition(
    node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun
) -> dict:
    """Evaluate condition against previous node output."""
    config = node.get("data", {})
    source_node_id = config.get("source_node_id", "")

    source_output = node_outputs.get(source_node_id, {}).get("output", "")

    # Simple keyword condition
    check_type = config.get("check_type", "contains")
    check_value = config.get("check_value", "")

    passed = False
    if check_type == "contains":
        passed = check_value.lower() in source_output.lower()
    elif check_type == "not_contains":
        passed = check_value.lower() not in source_output.lower()
    elif check_type == "status_ok":
        passed = node_outputs.get(source_node_id, {}).get("status") == "completed"
    elif check_type == "status_failed":
        passed = node_outputs.get(source_node_id, {}).get("status") == "failed"
    elif check_type == "always_true":
        passed = True

    return {"status": "completed", "passed": passed, "output": str(passed)}


async def _execute_output_report(node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun) -> dict:
    """Compile a markdown report from all node outputs."""
    config = node.get("data", {})
    template = config.get("template", "")

    if template:
        # Render what we can and leave missing values blank instead of leaking raw placeholders.
        report = _render_template_value(template, context)
    else:
        lines = [f"# Pipeline Run Report: {run.pipeline.name}\n"]
        for nid, state in node_outputs.items():
            lines.append(f"## Node `{nid}`")
            lines.append(f"**Status:** {state.get('status', 'unknown')}")
            if state.get("output"):
                lines.append(f"```\n{state['output'][:2000]}\n```")
            if state.get("error"):
                lines.append(f"**Error:** {state['error']}")
            lines.append("")
        report = "\n".join(lines)

    await _s2a_fn(PipelineRun.objects.filter(pk=run.pk).update)(summary=report)
    return {"status": "completed", "output": report}


async def _execute_output_webhook(node: dict, context: dict, node_outputs: dict[str, dict]) -> dict:
    """POST the pipeline results to an external webhook URL."""
    config = node.get("data", {})
    url = config.get("url", "")
    if not url:
        return {"status": "failed", "error": "No URL configured"}

    payload = {
        "context": context,
        "outputs": {k: {"status": v.get("status"), "output": v.get("output", "")[:1000]} for k, v in node_outputs.items()},
    }
    extra_payload = config.get("extra_payload", {})
    payload.update(extra_payload)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            return {
                "status": "completed",
                "output": f"POST {url} → {resp.status_code}",
                "http_status": resp.status_code,
            }
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}


def _load_notif_cfg() -> dict:
    """Load .notification_config.json (saved via UI) merged with env/Django settings."""
    try:
        from studio.views import _load_notif_config

        return _load_notif_config()
    except Exception:
        pass
    # Minimal fallback when views can't be imported
    try:
        from django.conf import settings as _s

        return {
            "telegram_bot_token": getattr(_s, "TELEGRAM_BOT_TOKEN", "") or "",
            "telegram_chat_id": getattr(_s, "TELEGRAM_CHAT_ID", "") or "",
            "notify_email": getattr(_s, "PIPELINE_NOTIFY_EMAIL", "") or getattr(_s, "EMAIL_HOST_USER", "") or "",
            "smtp_host": getattr(_s, "EMAIL_HOST", "") or "",
            "smtp_user": getattr(_s, "EMAIL_HOST_USER", "") or "",
            "smtp_password": getattr(_s, "EMAIL_HOST_PASSWORD", "") or "",
            "from_email": getattr(_s, "DEFAULT_FROM_EMAIL", "") or "",
            "site_url": getattr(_s, "SITE_URL", "http://localhost:8000") or "http://localhost:8000",
        }
    except Exception:
        return {}


def _global_tg_defaults() -> tuple[str, str]:
    """Return (bot_token, chat_id) — notification config file → env → Django settings."""
    cfg = _load_notif_cfg()
    return cfg.get("telegram_bot_token") or "", cfg.get("telegram_chat_id") or ""


def _global_email_defaults() -> tuple[str, str, str, str, str]:
    """Return (to_email, smtp_host, smtp_user, smtp_password, from_email)."""
    cfg = _load_notif_cfg()
    return (
        cfg.get("notify_email") or "",
        cfg.get("smtp_host") or "",
        cfg.get("smtp_user") or "",
        cfg.get("smtp_password") or "",
        cfg.get("from_email") or "",
    )


def _global_site_url() -> str:
    cfg = _load_notif_cfg()
    return (cfg.get("site_url") or "http://localhost:8000").rstrip("/")


def _resolve_from_email(from_email: str, smtp_user: str, smtp_host: str) -> str:
    """
    If From is the default noreply@weuai.site or broken (noreply@login), SMTP rejects it.
    Use the authenticated user's real address instead.
    """
    if not from_email or "weuai.site" in from_email or "noreply@" in (from_email or "").lower():
        if not smtp_user:
            return from_email or "pipeline@noreply.local"
        user = (smtp_user or "").strip()
        if "@" in user:
            return user
        host = (smtp_host or "").lower()
        if "yandex" in host:
            return f"{user}@yandex.ru"
        if "gmail" in host:
            return f"{user}@gmail.com"
        return user
    return from_email


def _normalize_email_recipient(to_email: str, smtp_host: str) -> str:
    """If recipient is only login (no @), append domain for Yandex/Gmail."""
    to_email = (to_email or "").strip()
    if not to_email or "@" in to_email:
        return to_email
    host = (smtp_host or "").lower()
    if "yandex" in host:
        return f"{to_email}@yandex.ru"
    if "gmail" in host:
        return f"{to_email}@gmail.com"
    return to_email


async def _send_telegram_message(
    *,
    bot_token: str,
    chat_id: str,
    message: str,
    parse_mode: str = "Markdown",
    reply_markup: dict[str, Any] | None = None,
    disable_web_page_preview: bool = False,
) -> dict[str, Any]:
    """Send one or more Telegram messages, optionally attaching inline buttons to the final chunk."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = [message[i : i + 4000] for i in range(0, len(message), 4000)] or [""]
    sent = 0
    message_ids: list[int] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for index, chunk in enumerate(chunks):
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if disable_web_page_preview:
                payload["disable_web_page_preview"] = True
            if reply_markup and index == len(chunks) - 1:
                payload["reply_markup"] = reply_markup

            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                err = resp.text[:200]
                return {"status": "failed", "error": f"Telegram API error {resp.status_code}: {err}"}
            with contextlib.suppress(Exception):
                resp_payload = resp.json()
                message_id = int(((resp_payload.get("result") or {}) or {}).get("message_id"))
                message_ids.append(message_id)
            sent += 1

    return {
        "status": "completed",
        "output": f"📱 Telegram message sent to {chat_id} ({sent} chunk(s))",
        "message_ids": message_ids,
        "last_message_id": message_ids[-1] if message_ids else None,
    }


async def _execute_output_telegram(node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun) -> dict:
    """Send a message via Telegram Bot API. Falls back to TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from .env."""
    config = node.get("data", {})
    g_token, g_chat = _global_tg_defaults()
    bot_token = (config.get("bot_token") or g_token or "").strip()
    chat_id = (config.get("chat_id") or g_chat or "").strip()

    if not bot_token:
        return {"status": "failed", "error": "bot_token not configured. Set TELEGRAM_BOT_TOKEN in .env or fill in the node."}
    if not chat_id:
        return {"status": "failed", "error": "chat_id not configured. Set TELEGRAM_CHAT_ID in .env or fill in the node."}

    message_template = config.get("message", "")
    if not message_template:
        # Auto-build message from pipeline outputs
        lines = [f"📊 *Pipeline: {run.pipeline.name}*\n"]
        for nid, state in node_outputs.items():
            out = (state.get("output") or "").strip()
            if out:
                lines.append(f"*[{nid}]*\n{out[:800]}")
        message_template = "\n\n".join(lines) or f"Pipeline {run.pipeline.name} status update."

    subs = dict(context)
    subs["pipeline_name"] = run.pipeline.name
    subs["run_id"] = str(run.pk)
    subs["entry_node_id"] = str(run.entry_node_id or "")
    subs["trigger_type"] = str(getattr(run.trigger, "trigger_type", "") or "")
    subs["trigger_name"] = str(getattr(run.trigger, "name", "") or "")
    subs["all_outputs"] = "\n\n".join(
        f"[{nid}]: {(v.get('output') or '')[:500]}" for nid, v in node_outputs.items() if v.get("output")
    )
    try:
        message = message_template.format_map(subs)
    except (KeyError, ValueError):
        message = message_template

    parse_mode = config.get("parse_mode", "Markdown")
    reply_markup = config.get("reply_markup")
    disable_web_page_preview = bool(config.get("disable_web_page_preview", False))

    try:
        return await _send_telegram_message(
            bot_token=bot_token,
            chat_id=chat_id,
            message=message,
            parse_mode=parse_mode,
            reply_markup=reply_markup if isinstance(reply_markup, dict) else None,
            disable_web_page_preview=disable_web_page_preview,
        )
    except Exception as exc:
        return {"status": "failed", "error": f"Telegram send error: {exc}"}


async def _execute_logic_wait(node: dict, context: dict, run: PipelineRun, stop_event: Event | None = None) -> dict:
    """Pause pipeline execution for a configurable number of minutes."""
    config = node.get("data", {})
    try:
        minutes = float(config.get("wait_minutes", 1))
    except (TypeError, ValueError):
        minutes = 1.0

    minutes = max(0.1, min(minutes, 1440))  # clamp: 6 seconds to 24 hours
    logger.info("logic/wait node %s: sleeping %.1f minutes", node.get("id"), minutes)
    remaining_seconds = minutes * 60
    while remaining_seconds > 0:
        if stop_event and stop_event.is_set():
            return {"status": "stopped", "output": "Wait cancelled by stop request", "stopped": True}
        fresh_status = await _s2a(
            lambda: PipelineRun.objects.filter(pk=run.pk).values_list("status", flat=True).first(),
            thread_sensitive=False,
        )()
        if fresh_status == PipelineRun.STATUS_STOPPED:
            return {"status": "stopped", "output": "Wait cancelled by stop request", "stopped": True}
        sleep_seconds = min(1.0, remaining_seconds)
        await asyncio.sleep(sleep_seconds)
        remaining_seconds -= sleep_seconds
    return {"status": "completed", "output": f"⏱️ Ожидание завершено: {minutes:.1f} мин."}


async def _execute_logic_human_approval(
    node: dict,
    context: dict,
    node_outputs: dict[str, dict],
    run: PipelineRun,
    stop_event: Event | None = None,
) -> dict:
    """
    Pause the pipeline and wait for a human approve/reject decision.

    How it works:
    1. Generates a signed one-time token stored in node_states.
    2. Sends an email and/or Telegram message with approve/reject actions.
       APPROVE → GET /api/studio/runs/<run_id>/approve/<node_id>/?token=...&decision=approved
       REJECT  → GET /api/studio/runs/<run_id>/approve/<node_id>/?token=...&decision=rejected
       Telegram uses inline callback buttons, so no external browser access is required.
    3. Polls Telegram callbacks and the DB for the decision.
    4. On timeout, returns failed.
    5. If approved, the pipeline continues; if rejected, the run is treated as failed
       (downstream nodes can check {node_id_status} == "failed" with a logic/condition).
    """
    config = node.get("data", {})
    node_id = node["id"]
    timeout_minutes = float(config.get("timeout_minutes", 120))

    # Global fallbacks from Django settings / env
    g_to, _gh, _gu, _gp, _gf = _global_email_defaults()
    g_token, g_chat = _global_tg_defaults()
    base_url = (config.get("base_url") or "").rstrip("/") or _global_site_url()

    # Build rich context for the notification message
    all_outputs_text = "\n\n".join(
        f"--- [{nid}] ---\n{(v.get('output') or '').strip()[:2000]}"
        for nid, v in node_outputs.items()
        if (v.get("output") or "").strip()
    )
    subs = dict(context)
    subs["all_outputs"] = all_outputs_text

    message_template = config.get(
        "message",
        "🔔 *Требуется подтверждение пайплайна*\n\n"
        "*Пайплайн:* {pipeline_name}\n"
        "*Запуск:* {run_id}\n\n"
        "{all_outputs}\n\n"
        "Пожалуйста, проверьте план выше и примите решение:\n\n"
        "✅ *ОДОБРИТЬ:* {approve_url}\n\n"
        "❌ *ОТКЛОНИТЬ:* {reject_url}",
    )

    # Generate one-time token
    approval_token = secrets.token_urlsafe(32)
    approve_url = f"{base_url}/api/studio/runs/{run.pk}/approve/{node_id}/?token={approval_token}&decision=approved"
    reject_url = f"{base_url}/api/studio/runs/{run.pk}/approve/{node_id}/?token={approval_token}&decision=rejected"

    subs["pipeline_name"] = run.pipeline.name
    subs["run_id"] = str(run.pk)
    subs["approve_url"] = approve_url
    subs["reject_url"] = reject_url
    subs["all_outputs"] = all_outputs_text
    subs["timeout_minutes"] = str(int(timeout_minutes))

    with contextlib.suppress(KeyError, ValueError):
        message_template.format_map(subs)

    # Save initial "awaiting" state with token
    await _update_node_state(
        run,
        node_id,
        {
            "status": "awaiting_approval",
            "approval_token": approval_token,
            "approve_url": approve_url,
            "reject_url": reject_url,
            "started_at": timezone.now().isoformat(),
        },
    )

    # ── Send notifications ──────────────────────────────────────────────────

    # Email notification — node config overrides global settings; subject/body from node or default
    to_email = (config.get("to_email") or g_to or "").strip()
    if to_email:
        email_subject_tpl = (config.get("email_subject") or "").strip()
        email_body_tpl = (config.get("email_body") or "").strip()
        if email_subject_tpl:
            try:
                email_subject = email_subject_tpl.format_map(subs)
            except (KeyError, ValueError):
                email_subject = email_subject_tpl
        else:
            email_subject = f"Обновление сервера: нужно ваше решение (запуск #{run.pk})"
        if email_body_tpl:
            try:
                email_body = email_body_tpl.format_map(subs)
            except (KeyError, ValueError):
                email_body = email_body_tpl
        else:
            plan_preview = (all_outputs_text or "").strip()
            if len(plan_preview) > 1200:
                plan_preview = plan_preview[:1200].rstrip() + "\n\n... (полный отчёт в логе пайплайна)"
            email_body = (
                "Здравствуйте.\n\n"
                "Пайплайн собрал план обновлений на сервере и ждёт вашего решения.\n\n"
                "——— Отчёт и план ———\n\n"
                f"{plan_preview}\n\n"
                "——— Что сделать ———\n\n"
                f"ОДОБРИТЬ: {approve_url}\n\n"
                f"ОТКЛОНИТЬ: {reject_url}\n\n"
                f"Ссылка действительна {timeout_minutes:.0f} мин.\n\n"
                "С уважением,\nWEU Pipeline"
            )
        email_node = {
            "id": f"{node_id}_approval_email",
            "data": {
                "to_email": to_email,
                "subject": email_subject,
                "body": email_body,
                "smtp_host": config.get("smtp_host") or "",
                "smtp_port": config.get("smtp_port") or "",
                "smtp_user": config.get("smtp_user") or "",
                "smtp_password": config.get("smtp_password") or "",
                "from_email": config.get("from_email") or "",
            },
        }
        try:
            await _execute_output_email(email_node, subs, node_outputs, run)
            logger.info("human_approval node %s: approval email sent to %s", node_id, to_email)
        except Exception as exc:
            logger.warning("human_approval email failed: %s", exc)

    # Telegram notification — node config overrides global settings
    tg_bot_token = (config.get("tg_bot_token") or g_token or "").strip()
    tg_chat_id = (config.get("tg_chat_id") or g_chat or "").strip()
    raw_tg_parse_mode = config.get("tg_parse_mode")
    tg_parse_mode = "Markdown" if raw_tg_parse_mode is None else str(raw_tg_parse_mode).strip()
    if tg_bot_token and tg_chat_id:
        telegram_message_template = (
            config.get("telegram_message")
            or "🔔 *Требуется подтверждение пайплайна*\n\n"
            "*Пайплайн:* {pipeline_name}\n"
            "*Запуск:* {run_id}\n\n"
            "{all_outputs}\n\n"
            "Нажмите кнопку ниже, чтобы одобрить или отклонить шаг прямо в Telegram."
        )
        try:
            telegram_message = telegram_message_template.format_map(subs)
        except (KeyError, ValueError):
            telegram_message = str(telegram_message_template)
        tg_node = {
            "id": f"{node_id}_approval_tg",
                "data": {
                    "bot_token": tg_bot_token,
                    "chat_id": tg_chat_id,
                    "message": telegram_message,
                    "parse_mode": tg_parse_mode,
                    "disable_web_page_preview": True,
                    "reply_markup": {
                    "inline_keyboard": [
                        [
                            {
                                "text": "✅ Одобрить",
                                "callback_data": _telegram_approval_callback_data("approved", approval_token),
                            },
                            {
                                "text": "❌ Отклонить",
                                "callback_data": _telegram_approval_callback_data("rejected", approval_token),
                            },
                        ]
                    ]
                },
            },
        }
        try:
            await _execute_output_telegram(tg_node, subs, node_outputs, run)
            logger.info("human_approval node %s: Telegram notification sent", node_id)
        except Exception as exc:
            logger.warning("human_approval Telegram failed: %s", exc)

    # ── Poll for decision ───────────────────────────────────────────────────
    deadline = timezone.now() + timedelta(minutes=timeout_minutes)
    poll_interval = 2  # seconds

    while True:
        if stop_event and stop_event.is_set():
            return {"status": "stopped", "output": "Approval wait cancelled by stop request", "stopped": True}
        await asyncio.sleep(poll_interval)

        telegram_callback = None
        if tg_bot_token and tg_chat_id:
            telegram_callback = await _poll_telegram_approval_decision(tg_bot_token, approval_token)

        # Check if pipeline was stopped externally
        fresh_run = await _s2a(lambda: PipelineRun.objects.get(pk=run.pk), thread_sensitive=False)()

        node_state = dict(fresh_run.node_states.get(node_id, {}))
        if telegram_callback and not node_state.get("approval_decision"):
            node_state["approval_decision"] = telegram_callback.get("decision")
            node_state["approval_response"] = telegram_callback.get("response_text") or "via Telegram callback"
            node_state["approval_source"] = "telegram_callback"
            node_state["decided_at"] = timezone.now().isoformat()
            await _update_node_state(fresh_run, node_id, node_state)
            if tg_bot_token and tg_chat_id:
                verdict = "approved" if node_state["approval_decision"] == "approved" else "rejected"
                emoji = "✅" if verdict == "approved" else "❌"
                verdict_text = "одобрено" if verdict == "approved" else "отклонено"
                with contextlib.suppress(Exception):
                    await _send_telegram_message(
                        bot_token=tg_bot_token,
                        chat_id=tg_chat_id,
                        message=(
                            f"{emoji} *Решение записано*\n\n"
                            f"*Пайплайн:* {run.pipeline.name}\n"
                            f"*Запуск:* #{run.pk}\n"
                            f"*Узел:* {config.get('label') or node_id}\n"
                            f"*Решение:* {verdict_text}"
                        ),
                    )

        decision = node_state.get("approval_decision")

        if decision == "approved":
            user_response = node_state.get("approval_response", "")
            logger.info("human_approval node %s: APPROVED (response: %r)", node_id, user_response[:100])
            return {
                "status": "completed",
                "output": f"ОДОБРЕНО\n\nКомментарий:\n{user_response}" if user_response else "ОДОБРЕНО",
                "approved": True,
                "decision": "approved",
                "user_response": user_response,
            }

        if decision == "rejected":
            user_response = node_state.get("approval_response", "")
            logger.info("human_approval node %s: REJECTED", node_id)
            return {
                "status": "failed",
                "error": f"ОТКЛОНЕНО оператором.\n\nПричина: {user_response}" if user_response else "ОТКЛОНЕНО оператором.",
                "approved": False,
                "decision": "rejected",
            }

        if is_runtime_stop_requested(fresh_run):
            return {"status": "stopped", "output": "Approval wait cancelled by stop request", "stopped": True}

        if timezone.now() >= deadline:
            logger.warning("human_approval node %s: TIMEOUT after %.0f min", node_id, timeout_minutes)
            return {
                "status": "failed",
                "error": f"Таймаут подтверждения — нет ответа в течение {timeout_minutes:.0f} мин.",
                "decision": "timeout",
            }


async def _execute_logic_telegram_input(
    node: dict,
    context: dict,
    node_outputs: dict[str, dict],
    run: PipelineRun,
    stop_event: Event | None = None,
) -> dict:
    """Wait for a plain-text operator reply in Telegram."""

    config = node.get("data", {})
    node_id = str(node.get("id") or "")
    try:
        timeout_minutes = float(config.get("timeout_minutes", 120) or 120)
    except (TypeError, ValueError):
        timeout_minutes = 120.0
    g_token, g_chat = _global_tg_defaults()
    bot_token = (config.get("tg_bot_token") or g_token or "").strip()
    chat_id = str(config.get("tg_chat_id") or g_chat or "").strip()
    parse_mode = str(config.get("parse_mode") or "Markdown").strip() or "Markdown"

    if not bot_token:
        return {"status": "failed", "error": "tg_bot_token not configured for telegram_input node.", "decision": "timeout"}
    if not chat_id:
        return {"status": "failed", "error": "tg_chat_id not configured for telegram_input node.", "decision": "timeout"}

    all_outputs_text = "\n\n".join(
        f"--- [{nid}] ---\n{(v.get('output') or '').strip()[:2000]}"
        for nid, v in node_outputs.items()
        if (v.get("output") or "").strip()
    )
    subs = dict(context)
    subs["pipeline_name"] = run.pipeline.name
    subs["run_id"] = str(run.pk)
    subs["all_outputs"] = all_outputs_text
    subs["node_label"] = str(config.get("label") or node_id)
    message_template = (
        config.get("message")
        or "📝 *Нужна инструкция оператора*\n\n"
        "*Пайплайн:* {pipeline_name}\n"
        "*Запуск:* {run_id}\n"
        "*Узел:* {node_label}\n\n"
        "{all_outputs}\n\n"
        "Ответьте на это сообщение обычным текстом. Ответ будет передан агенту."
    )
    node_state = dict(run.node_states.get(node_id, {}))
    
    # ── Phase 2: Wakeup / Timeout check ──
    if node_state.get("status") in {"hibernating", "awaiting_operator_reply"}:
        operator_response = str(node_state.get("operator_response") or "").strip()
        if operator_response:
            return {
                "status": "completed",
                "output": operator_response,
                "decision": "received",
                "response_text": operator_response,
            }
            
        started_at_str = node_state.get("started_at")
        if started_at_str:
            from dateutil.parser import isoparse
            started_at = isoparse(started_at_str)
            if timezone.now() >= started_at + timedelta(minutes=timeout_minutes):
                return {
                    "status": "failed",
                    "error": f"Таймаут ожидания ответа оператора — нет ответа в течение {timeout_minutes:.0f} мин.",
                    "decision": "timeout",
                }
        if is_runtime_stop_requested(run):
            return {"status": "stopped", "output": "Ожидание ответа оператора отменено", "stopped": True}
        return {"status": "hibernating", "reason": "awaiting_operator_reply"}

    # ── Phase 1: Send prompt ──
    try:
        prompt_message = str(message_template).format_map(subs)
    except (KeyError, ValueError):
        prompt_message = str(message_template)

    telegram_result = await _send_telegram_message(
        bot_token=bot_token,
        chat_id=chat_id,
        message=prompt_message,
        parse_mode=parse_mode,
        reply_markup={"force_reply": True, "selective": False},
    )
    if telegram_result.get("status") != "completed":
        return {
            "status": "failed",
            "error": str(telegram_result.get("error") or "Не удалось отправить Telegram-сообщение."),
            "decision": "timeout",
        }

    try:
        prompt_message_id = int(telegram_result.get("last_message_id") or 0)
    except (TypeError, ValueError):
        prompt_message_id = 0
    if prompt_message_id <= 0:
        return {
            "status": "failed",
            "error": "Telegram не вернул message_id для ожидания ответа оператора.",
            "decision": "timeout",
        }

    await _update_node_state(
        run,
        node_id,
        {
            "status": "hibernating",
            "telegram_prompt_message_id": prompt_message_id,
            "telegram_chat_id": chat_id,
            "bot_token": bot_token,
            "started_at": timezone.now().isoformat(),
        },
    )
    return {"status": "hibernating", "reason": "awaiting_operator_reply"}


async def _execute_logic_merge(node: dict, context: dict, node_outputs: dict[str, dict], run: PipelineRun) -> dict:
    mode = str((node.get("data") or {}).get("mode") or "all").strip().lower()
    if mode not in {"all", "any"}:
        mode = "all"
    mode_label = "любая ветка" if mode == "any" else "все ветки"
    return {"status": "completed", "output": f"объединение: {mode_label}"}


# ---------------------------------------------------------------------------
# Channel layer event helper
# ---------------------------------------------------------------------------


def _make_run_event_callback(run: PipelineRun, node_id: str):
    """Returns an async callback that forwards agent events to the pipeline run channel group."""

    async def callback(event_type: str, data: dict):
        layer = get_channel_layer()
        if layer:
            with contextlib.suppress(Exception):
                await layer.group_send(
                    f"pipeline_run_{run.pk}",
                    {
                        "type": "pipeline.node.event",
                        "node_id": node_id,
                        "event_type": event_type,
                        "data": data,
                    },
                )

    return callback


# ---------------------------------------------------------------------------
# State persistence helpers
# ---------------------------------------------------------------------------


async def _update_node_state(run: PipelineRun, node_id: str, state: dict):
    """Persist node state and notify WS clients."""
    run.node_states[node_id] = state
    logger.info(
        "pipeline run %s node %s state -> %s",
        run.pk,
        node_id,
        state.get("status", "unknown"),
    )

    await _s2a_fn(lambda: PipelineRun.objects.filter(pk=run.pk).update(node_states=run.node_states))()

    actor_ctx = _pipeline_actor_context(run)
    await log_user_activity_async(
        user_id=actor_ctx.get("user_id"),
        username_snapshot=str(actor_ctx.get("username_snapshot") or ""),
        category="pipeline",
        action="pipeline_node_state",
        status="error" if state.get("status") == "failed" else "success",
        description=f"Node {node_id} -> {state.get('status', 'unknown')}",
        entity_type="pipeline_run",
        entity_id=str(run.pk),
        entity_name=actor_ctx.get("entity_name") or "",
        metadata={
            "node_id": node_id,
            "node_status": state.get("status", "unknown"),
            "started_at": state.get("started_at"),
            "finished_at": state.get("finished_at"),
            "error": str(state.get("error") or "")[:4000],
        },
    )

    layer = get_channel_layer()
    if layer:
        with contextlib.suppress(Exception):
            await layer.group_send(
                f"pipeline_run_{run.pk}",
                {"type": "pipeline.node.state", "node_id": node_id, "state": state},
            )


async def _update_routing_state(run: PipelineRun, routing_state: dict[str, Any]) -> None:
    run.routing_state = routing_state
    await _s2a_fn(lambda: PipelineRun.objects.filter(pk=run.pk).update(routing_state=run.routing_state))()


async def _update_run_status(run: PipelineRun, status: str, **extra):
    run.status = status
    update_fields = ["status"]
    for k, v in extra.items():
        setattr(run, k, v)
        update_fields.append(k)
    logger.info(
        "pipeline run %s status -> %s%s",
        run.pk,
        status,
        f" extra={list(extra.keys())}" if extra else "",
    )
    await _s2a_fn(run.save)(update_fields=list(dict.fromkeys(update_fields)))

    actor_ctx = _pipeline_actor_context(run)
    await log_user_activity_async(
        user_id=actor_ctx.get("user_id"),
        username_snapshot=str(actor_ctx.get("username_snapshot") or ""),
        category="pipeline",
        action="pipeline_run_status",
        status="error" if status == PipelineRun.STATUS_FAILED else "success",
        description=f"Pipeline run #{run.pk} -> {status}",
        entity_type="pipeline_run",
        entity_id=str(run.pk),
        entity_name=actor_ctx.get("entity_name") or "",
        metadata={
            "status": status,
            "extra": extra,
        },
    )

    layer = get_channel_layer()
    if layer:
        with contextlib.suppress(Exception):
            await layer.group_send(
                f"pipeline_run_{run.pk}",
                {"type": "pipeline.status", "status": status, **extra},
            )


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

    def _build_graph(self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> tuple[
        dict[str, dict[str, Any]],
        dict[str, list[dict[str, Any]]],
        dict[str, list[dict[str, Any]]],
    ]:
        id_to_node = {str(node.get("id") or ""): node for node in nodes if str(node.get("id") or "").strip()}
        outgoing_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
        incoming_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges or []:
            source = str(edge.get("source") or "").strip()
            target = str(edge.get("target") or "").strip()
            if source in id_to_node and target in id_to_node:
                outgoing_edges[source].append(edge)
                incoming_edges[target].append(edge)
        return id_to_node, outgoing_edges, incoming_edges

    async def _persist_routing_state(
        self,
        *,
        entry_node_id: str,
        activated_nodes: set[str],
        completed_nodes: set[str],
        ready_nodes: set[str],
        pending_merges: dict[str, dict[str, Any]],
    ) -> None:
        await _update_routing_state(
            self.run,
            _serialize_routing_state(
                entry_node_id=entry_node_id,
                activated_nodes=activated_nodes,
                completed_nodes=completed_nodes,
                queued_nodes=ready_nodes,
                pending_merges=pending_merges,
            ),
        )

    async def _route_from_node(
        self,
        *,
        source_node_id: str,
        routing_ports: set[str],
        entry_node_id: str,
        id_to_node: dict[str, dict[str, Any]],
        outgoing_edges: dict[str, list[dict[str, Any]]],
        incoming_edges: dict[str, list[dict[str, Any]]],
        node_states: dict[str, dict[str, Any]],
        ready_queue: deque[str],
        ready_nodes: set[str],
        activated_nodes: set[str],
        completed_nodes: set[str],
        pending_merges: dict[str, dict[str, Any]],
    ) -> None:
        source_id = str(source_node_id or "").strip()
        if not source_id:
            return
        activated_nodes.add(source_id)

        for edge in outgoing_edges.get(source_id, []):
            if _graph_edge_handle(edge) not in routing_ports:
                continue

            target_id = str(edge.get("target") or "").strip()
            target_node = id_to_node.get(target_id)
            if not target_id or target_node is None:
                continue

            target_type = str(target_node.get("type") or "")
            activated_nodes.add(target_id)

            if target_type == "logic/merge":
                merge_state = pending_merges.setdefault(
                    target_id,
                    {
                        "mode": str((target_node.get("data") or {}).get("mode") or "all").strip().lower() or "all",
                        "arrived_sources": set(),
                        "possible_sources": set(),
                        "released": False,
                    },
                )
                if merge_state["mode"] not in {"all", "any"}:
                    merge_state["mode"] = "all"
                merge_state.setdefault("arrived_sources", set()).add(source_id)
                merge_state["possible_sources"] = _possible_merge_sources(
                    merge_node_id=target_id,
                    entry_node_id=entry_node_id,
                    id_to_node=id_to_node,
                    incoming_edges=incoming_edges,
                    outgoing_edges=outgoing_edges,
                    node_states=node_states,
                )
                if merge_state.get("released") or target_id in completed_nodes or target_id in ready_nodes:
                    continue

                arrived_sources = set(merge_state.get("arrived_sources") or set())
                possible_sources = set(merge_state.get("possible_sources") or set())
                should_release = False
                if merge_state["mode"] == "any":
                    should_release = bool(arrived_sources)
                else:
                    should_release = bool(possible_sources) and arrived_sources >= possible_sources

                if should_release:
                    merge_state["released"] = True
                    ready_queue.append(target_id)
                    ready_nodes.add(target_id)
                continue

            if target_id in completed_nodes or target_id in ready_nodes:
                continue
            ready_queue.append(target_id)
            ready_nodes.add(target_id)

    async def execute(self, context: dict | None = None) -> PipelineRun:
        run = self.run
        owner = await _s2a_fn(lambda: run.pipeline.owner)()
        register_executor(run.pk, self)
        try:
            with audit_context(**_pipeline_actor_context(run)):
                if context is None:
                    context = {}
                if not isinstance(context, dict):
                    await _update_run_status(
                        run,
                        PipelineRun.STATUS_FAILED,
                        error="Pipeline run context must be a JSON object.",
                        finished_at=timezone.now(),
                    )
                    return run
                if await self._sync_stop_state_from_db():
                    await _update_run_status(run, PipelineRun.STATUS_STOPPED, finished_at=timezone.now())
                    return run
                context = dict(context)

                nodes = list(run.nodes_snapshot or run.pipeline.nodes or [])
                edges = list(run.edges_snapshot or run.pipeline.edges or [])
                graph_version = getattr(run.pipeline, "graph_version", None)
                validation_errors = await _s2a_fn(
                    lambda: validate_pipeline_definition(
                        nodes=nodes,
                        edges=edges,
                        owner=owner,
                        graph_version=graph_version,
                    )
                )()
                if validation_errors:
                    await _update_run_status(
                        run,
                        PipelineRun.STATUS_FAILED,
                        error=f"Pipeline validation failed: {'; '.join(validation_errors)}",
                        finished_at=timezone.now(),
                    )
                    return run
                entry_node_id = str(run.entry_node_id or getattr(getattr(run, "trigger", None), "node_id", "") or "").strip()
                id_to_node, outgoing_edges, incoming_edges = self._build_graph(nodes, edges)
                entry_node = id_to_node.get(entry_node_id)
                if not entry_node_id or entry_node is None:
                    await _update_run_status(
                        run,
                        PipelineRun.STATUS_FAILED,
                        error="Pipeline run is missing a valid entry trigger node.",
                        finished_at=timezone.now(),
                    )
                    return run
                if not str(entry_node.get("type") or "").startswith("trigger/"):
                    await _update_run_status(
                        run,
                        PipelineRun.STATUS_FAILED,
                        error=f"Entry node '{entry_node_id}' is not a trigger node.",
                        finished_at=timezone.now(),
                    )
                    return run

                reachable_from_entry = _reachable_nodes_from_entry(
                    entry_node_id=entry_node_id,
                    id_to_node=id_to_node,
                    outgoing_edges=outgoing_edges,
                    node_states={},
                )
                if not any(
                    not str(id_to_node[node_id].get("type") or "").startswith("trigger/")
                    for node_id in reachable_from_entry
                ):
                    await _update_run_status(
                        run,
                        PipelineRun.STATUS_FAILED,
                        error=f"Selected trigger '{entry_node_id}' has no downstream executable nodes.",
                        finished_at=timezone.now(),
                    )
                    return run

                run.nodes_snapshot = nodes
                run.edges_snapshot = edges
                run.context = context
                run.entry_node_id = entry_node_id
                run.node_states = {}
                run.routing_state = _serialize_routing_state(
                    entry_node_id=entry_node_id,
                    activated_nodes={entry_node_id},
                    completed_nodes={entry_node_id},
                    queued_nodes=set(),
                    pending_merges={},
                )
                run.error = ""
                run.started_at = timezone.now()
                await _s2a_fn(run.save)()

                logger.info(
                    "pipeline run %s start: pipeline=%s entry=%s context_keys=%s nodes=%s edges=%s",
                    run.pk,
                    run.pipeline.name,
                    entry_node_id,
                    sorted(context.keys()),
                    len(run.nodes_snapshot or []),
                    len(run.edges_snapshot or []),
                )
                await _update_run_status(run, PipelineRun.STATUS_RUNNING)

                node_outputs: dict[str, dict] = {}
                ready_queue: deque[str] = deque()
                ready_nodes: set[str] = set()
                activated_nodes: set[str] = {entry_node_id}
                completed_nodes: set[str] = {entry_node_id}
                pending_merges: dict[str, dict[str, Any]] = {}
                await self._route_from_node(
                    source_node_id=entry_node_id,
                    routing_ports={"out"},
                    entry_node_id=entry_node_id,
                    id_to_node=id_to_node,
                    outgoing_edges=outgoing_edges,
                    incoming_edges=incoming_edges,
                    node_states=run.node_states,
                    ready_queue=ready_queue,
                    ready_nodes=ready_nodes,
                    activated_nodes=activated_nodes,
                    completed_nodes=completed_nodes,
                    pending_merges=pending_merges,
                )
                await self._persist_routing_state(
                    entry_node_id=entry_node_id,
                    activated_nodes=activated_nodes,
                    completed_nodes=completed_nodes,
                    ready_nodes=ready_nodes,
                    pending_merges=pending_merges,
                )

                try:
                    batch_index = 0
                    while ready_queue:
                        if await self._sync_stop_state_from_db():
                            break

                        batch_index += 1
                        batch_node_ids: list[str] = []
                        while ready_queue:
                            node_id = ready_queue.popleft()
                            ready_nodes.discard(node_id)
                            if node_id not in id_to_node or node_id in completed_nodes:
                                continue
                            batch_node_ids.append(node_id)

                        if not batch_node_ids:
                            continue

                        exec_nodes = [id_to_node[node_id] for node_id in batch_node_ids]
                        logger.info(
                            "pipeline run %s batch %s start: nodes=%s",
                            run.pk,
                            batch_index,
                            [node.get("id") for node in exec_nodes],
                        )

                        started_at = timezone.now().isoformat()
                        for node in exec_nodes:
                            await _update_node_state(
                                run,
                                str(node["id"]),
                                {"status": "running", "started_at": started_at},
                            )

                        results = await asyncio.gather(
                            *(self._execute_node(node, context, node_outputs) for node in exec_nodes),
                            return_exceptions=True,
                        )

                        resolved_states: list[tuple[dict[str, Any], dict[str, Any]]] = []
                        abort_error: str | None = None
                        stop_in_batch = False
                        finished_at = timezone.now().isoformat()

                        for node, result in zip(exec_nodes, results, strict=False):
                            nid = str(node["id"])
                            if isinstance(result, Exception):
                                logger.exception("pipeline run %s node %s raised exception", run.pk, nid, exc_info=result)
                                state: dict[str, Any] = {
                                    "status": "failed",
                                    "error": str(result),
                                }
                            else:
                                state = dict(result)

                            state.setdefault("started_at", started_at)
                            state["finished_at"] = finished_at
                            state["routing_ports"] = _result_routing_ports(node, state)
                            node_outputs[nid] = state
                            completed_nodes.add(nid)
                            activated_nodes.add(nid)
                            resolved_states.append((node, state))
                            await _update_node_state(run, nid, state)

                            logger.info(
                                "pipeline run %s node %s finished: type=%s status=%s ports=%s error=%s output_chars=%s",
                                run.pk,
                                nid,
                                node.get("type", ""),
                                state.get("status"),
                                state.get("routing_ports"),
                                (state.get("error") or "")[:300],
                                len(state.get("output") or ""),
                            )

                            if state.get("status") == "stopped":
                                stop_in_batch = True
                                self.request_stop()

                            node_type = str(node.get("type") or "")
                            on_fail = str((node.get("data") or {}).get("on_failure") or "continue").strip().lower()
                            if (
                                abort_error is None
                                and state.get("status") == "failed"
                                and on_fail == "abort"
                                and (node_type.startswith("agent/") or node_type.startswith("output/"))
                            ):
                                abort_error = f"Node {nid} failed: {state.get('error')}"

                        if abort_error is None and not stop_in_batch and not self._stop_requested:
                            for node, state in resolved_states:
                                await self._route_from_node(
                                    source_node_id=str(node.get("id") or ""),
                                    routing_ports=set(state.get("routing_ports") or []),
                                    entry_node_id=entry_node_id,
                                    id_to_node=id_to_node,
                                    outgoing_edges=outgoing_edges,
                                    incoming_edges=incoming_edges,
                                    node_states=run.node_states,
                                    ready_queue=ready_queue,
                                    ready_nodes=ready_nodes,
                                    activated_nodes=activated_nodes,
                                    completed_nodes=completed_nodes,
                                    pending_merges=pending_merges,
                                )

                        await self._persist_routing_state(
                            entry_node_id=entry_node_id,
                            activated_nodes=activated_nodes,
                            completed_nodes=completed_nodes,
                            ready_nodes=ready_nodes,
                            pending_merges=pending_merges,
                        )

                        if abort_error is not None:
                            raise RuntimeError(abort_error)
                        if stop_in_batch or self._stop_requested:
                            break

                except Exception as exc:
                    run.error = str(exc)
                    logger.exception("pipeline run %s failed", run.pk)
                    await _update_run_status(run, PipelineRun.STATUS_FAILED, error=str(exc), finished_at=timezone.now())
                    return run

                if self._stop_requested:
                    await _update_run_status(run, PipelineRun.STATUS_STOPPED, finished_at=timezone.now())
                else:
                    await _update_run_status(run, PipelineRun.STATUS_COMPLETED, finished_at=timezone.now())

                logger.info("pipeline run %s finished: status=%s", run.pk, run.status)
                return run
        finally:
            unregister_executor(run.pk, self)

    async def _execute_node(self, node: dict, context: dict, node_outputs: dict[str, dict]) -> dict:
        node_type = node.get("type", "")

        # Build enriched context: merge previous node outputs so templates like
        # {n2}, {n2_output}, {n2_error} are all available in every node.
        # Use a defaultdict so unknown keys return "" instead of raising KeyError.
        enriched: dict = defaultdict(str, context)
        enriched["pipeline_name"] = self.run.pipeline.name
        enriched["run_id"] = str(self.run.pk)
        enriched["entry_node_id"] = str(self.run.entry_node_id or "")
        enriched["trigger_type"] = str(getattr(self.run.trigger, "trigger_type", "") or "")
        enriched["trigger_name"] = str(getattr(self.run.trigger, "name", "") or "")
        for nid, state in node_outputs.items():
            out = state.get("output", "") or ""
            err = state.get("error", "") or ""
            enriched[nid] = out
            enriched[f"{nid}_output"] = out
            enriched[f"{nid}_error"] = err
            enriched[f"{nid}_status"] = state.get("status", "")

        if node_type == "agent/react":
            return await _execute_agent_react(node, enriched, self.run)

        if node_type == "agent/multi":
            return await _execute_agent_multi(node, enriched, self.run)

        if node_type == "agent/ssh_cmd":
            return await _execute_agent_ssh_cmd(node, enriched, self.run)

        if node_type == "agent/llm_query":
            return await _execute_agent_llm_query(node, enriched, node_outputs, self.run)

        if node_type == "agent/mcp_call":
            return await _execute_agent_mcp_call(node, enriched, self.run, self._executed_mcp_tools)

        if node_type == "logic/condition":
            return await _execute_logic_condition(node, enriched, node_outputs, self.run)

        if node_type == "logic/parallel":
            return {"status": "completed", "output": "параллельное разветвление"}

        if node_type == "logic/merge":
            return await _execute_logic_merge(node, enriched, node_outputs, self.run)

        if node_type == "logic/wait":
            return await _execute_logic_wait(node, enriched, self.run, self._stop_event)

        if node_type == "logic/human_approval":
            return await _execute_logic_human_approval(node, enriched, node_outputs, self.run, self._stop_event)

        if node_type == "logic/telegram_input":
            return await _execute_logic_telegram_input(node, enriched, node_outputs, self.run, self._stop_event)

        if node_type == "output/report":
            return await _execute_output_report(node, enriched, node_outputs, self.run)

        if node_type == "output/webhook":
            return await _execute_output_webhook(node, enriched, node_outputs)

        if node_type == "output/email":
            return await _execute_output_email(node, enriched, node_outputs, self.run)

        if node_type == "output/telegram":
            return await _execute_output_telegram(node, enriched, node_outputs, self.run)

        logger.warning("Unknown node type: %s (node id=%s)", node_type, node.get("id"))
        return {"status": "skipped", "output": f"unknown node type: {node_type}"}
