from __future__ import annotations

import os
from typing import Any

from django.conf import settings

from app.core.model_utils import resolve_provider_and_model
from studio.models import AgentConfig, MCPServerPool, Pipeline
from studio.pipeline_notifications import _load_notif_cfg

_LLM_PROVIDER_KEYS = {
    "gemini": ("GEMINI_API_KEY",),
    "openai": ("OPENAI_API_KEY", "CODEX_API_KEY"),
    "fair": ("FAIR_HYPERION_API_KEY", "FAIR_API_KEY"),
    "grok": ("GROK_API_KEY",),
    "claude": ("ANTHROPIC_API_KEY",),
    "ollama": ("OLLAMA_API_KEY",),
}
_SEVERITY_RANK = {"ready": 0, "warning": 1, "error": 2}


def _node_data(node: dict[str, Any]) -> dict[str, Any]:
    return node.get("data") if isinstance(node.get("data"), dict) else {}


def _has_value(value: Any) -> bool:
    return bool(str(value or "").strip())


def _first_nonblank(*values: Any) -> Any:
    for value in values:
        if _has_value(value):
            return value
    return ""


def _env_any(keys: tuple[str, ...]) -> bool:
    return any(_has_value(os.getenv(key)) for key in keys)


def _managed_llm_key(provider: str) -> bool:
    try:
        from core_ui.managed_secrets import has_llm_api_key

        return has_llm_api_key(provider)
    except Exception:
        return False


def _llm_provider_ready(provider: str) -> bool:
    if provider == "auto":
        return any(_llm_provider_ready(item) for item in ("fair", "gemini", "openai", "grok", "claude", "ollama"))
    if provider == "ollama":
        return (
            _has_value(os.getenv("OLLAMA_BASE_URL"))
            or _has_value(getattr(settings, "OLLAMA_BASE_URL", ""))
            or _managed_llm_key("ollama")
            or _env_any(_LLM_PROVIDER_KEYS["ollama"])
        )
    keys = _LLM_PROVIDER_KEYS.get(provider)
    return bool(keys and (_env_any(keys) or _managed_llm_key(provider)))


def _email_backend_needs_smtp() -> bool:
    return "smtp" in str(getattr(settings, "EMAIL_BACKEND", "") or "").lower() or not getattr(settings, "EMAIL_BACKEND", "")


def _upsert_requirement(
    requirements: dict[str, dict[str, Any]],
    key: str,
    *,
    kind: str,
    name: str,
    node_id: str,
    status: str,
    severity: str,
    message: str,
) -> None:
    current = requirements.setdefault(
        key,
        {
            "kind": kind,
            "name": name,
            "status": status,
            "severity": severity,
            "required_by_node_ids": [],
            "message": message,
        },
    )
    if node_id and node_id not in current["required_by_node_ids"]:
        current["required_by_node_ids"].append(node_id)
    if _SEVERITY_RANK[severity] > _SEVERITY_RANK[current["severity"]]:
        current["status"] = status
        current["severity"] = severity
        current["message"] = message


def _telegram_requirement(requirements: dict[str, dict[str, Any]], node_id: str, data: dict[str, Any]) -> None:
    cfg = _load_notif_cfg()
    token = _first_nonblank(data.get("bot_token"), data.get("tg_bot_token"), data.get("telegram_bot_token"), cfg.get("telegram_bot_token"))
    chat = _first_nonblank(data.get("chat_id"), data.get("tg_chat_id"), data.get("telegram_chat_id"), cfg.get("telegram_chat_id"))
    _upsert_requirement(
        requirements,
        "telegram:bot-token",
        kind="telegram",
        name="Telegram bot token",
        node_id=node_id,
        status="ready" if _has_value(token) else "missing",
        severity="ready" if _has_value(token) else "error",
        message="Telegram bot token is configured." if _has_value(token) else "Set TELEGRAM_BOT_TOKEN or a node-level bot_token.",
    )
    _upsert_requirement(
        requirements,
        "telegram:chat",
        kind="telegram",
        name="Telegram chat",
        node_id=node_id,
        status="ready" if _has_value(chat) else "runtime_context_or_missing",
        severity="ready" if _has_value(chat) else "warning",
        message=(
            "Telegram chat is configured."
            if _has_value(chat)
            else "Set TELEGRAM_CHAT_ID/node chat_id, or provide tg_chat_id/chat_id in runtime context."
        ),
    )


def _email_requirement(requirements: dict[str, dict[str, Any]], node_id: str, data: dict[str, Any]) -> None:
    cfg = _load_notif_cfg()
    recipient = _first_nonblank(data.get("to_email"), cfg.get("notify_email"))
    smtp_host = _first_nonblank(data.get("smtp_host"), cfg.get("smtp_host"), getattr(settings, "EMAIL_HOST", ""))
    _upsert_requirement(
        requirements,
        "email:recipient",
        kind="email",
        name="Email recipient",
        node_id=node_id,
        status="ready" if _has_value(recipient) else "missing",
        severity="ready" if _has_value(recipient) else "error",
        message="Email recipient is configured." if _has_value(recipient) else "Set PIPELINE_NOTIFY_EMAIL or node to_email.",
    )
    if _email_backend_needs_smtp() and not _has_value(smtp_host):
        _upsert_requirement(
            requirements,
            "email:smtp",
            kind="email",
            name="SMTP host",
            node_id=node_id,
            status="missing",
            severity="warning",
            message="Set EMAIL_HOST or node smtp_host for real SMTP delivery.",
        )


def _llm_requirement(requirements: dict[str, dict[str, Any]], node_id: str, data: dict[str, Any]) -> None:
    provider, _model = resolve_provider_and_model(data.get("provider"), data.get("model"), default_provider="gemini")
    ready = _llm_provider_ready(provider)
    _upsert_requirement(
        requirements,
        f"llm:{provider}",
        kind="llm",
        name=f"LLM provider: {provider}",
        node_id=node_id,
        status="ready" if ready else "missing",
        severity="ready" if ready else "error",
        message=f"LLM provider {provider} is configured." if ready else f"Configure credentials/runtime for LLM provider {provider}.",
    )


def _mcp_requirement(requirements: dict[str, dict[str, Any]], node_id: str, mcp: MCPServerPool | None) -> None:
    if mcp is None:
        _upsert_requirement(
            requirements,
            f"mcp:missing:{node_id}",
            kind="mcp",
            name="MCP server",
            node_id=node_id,
            status="missing",
            severity="error",
            message="Select an accessible MCP server.",
        )
        return
    if mcp.last_test_ok is False:
        status, severity, message = "failed", "error", "MCP server last connection test failed."
    elif mcp.last_test_ok is None:
        status, severity, message = "untested", "warning", "MCP server has not been connection-tested yet."
    else:
        status, severity, message = "ready", "ready", "MCP server last connection test passed."
    _upsert_requirement(
        requirements,
        f"mcp:{mcp.pk}",
        kind="mcp",
        name=f"MCP server: {mcp.name}",
        node_id=node_id,
        status=status,
        severity=severity,
        message=message,
    )


def integration_requirements(pipeline: Pipeline, *, node_ids: set[str] | None = None) -> list[dict[str, Any]]:
    requirements: dict[str, dict[str, Any]] = {}
    for node in pipeline.nodes or []:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip()
        if node_ids is not None and node_id not in node_ids:
            continue
        node_type = str(node.get("type") or "").strip()
        data = _node_data(node)
        if node_type in {"output/telegram", "logic/telegram_input"}:
            _telegram_requirement(requirements, node_id, data)
        elif node_type == "output/email":
            _email_requirement(requirements, node_id, data)
        elif node_type in {"agent/llm_query", "agent/react", "agent/multi"}:
            _llm_requirement(requirements, node_id, data)
            agent_config_id = data.get("agent_config_id")
            if agent_config_id not in (None, ""):
                agent_config = AgentConfig.objects.filter(owner=pipeline.owner, id=agent_config_id).first()
                if agent_config:
                    _llm_requirement(requirements, node_id, {"model": agent_config.model})
                    for mcp in agent_config.mcp_servers.all():
                        _mcp_requirement(requirements, node_id, mcp)
        if node_type == "agent/mcp_call":
            mcp_server = None
            with_id = data.get("mcp_server_id")
            if with_id not in (None, ""):
                mcp_server = MCPServerPool.objects.filter(owner=pipeline.owner, id=with_id).first()
            _mcp_requirement(requirements, node_id, mcp_server)
        elif node_type in {"agent/react", "agent/multi"}:
            for raw_id in data.get("mcp_server_ids") or []:
                mcp = MCPServerPool.objects.filter(owner=pipeline.owner, id=raw_id).first()
                _mcp_requirement(requirements, node_id, mcp)
    return sorted(requirements.values(), key=lambda item: (item["kind"], item["name"]))
