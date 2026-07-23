"""Shared config helpers for pipeline agent nodes (tools mode, defaults, interaction)."""

from __future__ import annotations

from typing import Any

from app.core.model_utils import resolve_provider_and_model

TOOLS_MODE_ALL = "all"
TOOLS_MODE_ALLOWLIST = "allowlist"
TOOLS_MODE_DENYLIST = "denylist"

INTERACTION_INTERACTIVE = "interactive"
INTERACTION_UNATTENDED = "unattended"

# Align with frontend defaults (max_iterations≈6); no experimental model hardcode.
DEFAULT_AGENT_MAX_ITERATIONS_REACT = 6
DEFAULT_AGENT_MAX_ITERATIONS_MULTI = 6
DEFAULT_AGENT_MODEL = ""  # empty → provider/auto resolution
DEFAULT_AGENT_PROVIDER = "auto"

SAFE_DEFAULT_TOOLS = (
    "ssh_execute",
    "read_console",
    "report",
    "list_skills",
    "read_skill",
    "analyze_output",
)


def normalize_tools_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode in {TOOLS_MODE_ALL, TOOLS_MODE_ALLOWLIST, TOOLS_MODE_DENYLIST}:
        return mode
    return ""


def _normalize_tool_names(raw_tools: Any) -> list[str]:
    if raw_tools is None:
        return []
    if isinstance(raw_tools, dict):
        return [str(k).strip() for k, v in raw_tools.items() if v and str(k).strip()]
    return [str(item).strip() for item in (raw_tools or []) if str(item).strip()]


def resolve_tools_config(
    config: dict[str, Any] | None,
    *,
    allowed_tools: list[str] | None = None,
    all_tool_names: list[str] | None = None,
) -> tuple[dict[str, bool], str | None]:
    """Return (tools_config for AgentEngine, error).

    Empty tools_config means "all tools" (engine legacy behavior).
    Allowlist: only listed tools True.
    Denylist: all tools True except denied names False.
    """
    cfg = config if isinstance(config, dict) else {}
    tool_names = _normalize_tool_names(allowed_tools if allowed_tools is not None else cfg.get("allowed_tools"))

    mode = normalize_tools_mode(cfg.get("tools_mode"))
    if not mode:
        mode = TOOLS_MODE_ALLOWLIST if tool_names else TOOLS_MODE_ALL

    if mode == TOOLS_MODE_ALL:
        return {}, None

    if mode == TOOLS_MODE_ALLOWLIST:
        if not tool_names:
            return {}, (
                "tools_mode=allowlist requires a non-empty allowed_tools list. Select tools or set tools_mode=all."
            )
        return dict.fromkeys(tool_names, True), None

    # denylist
    known = list(all_tool_names or [])
    if not known:
        # App-level provider seam (registered by servers.apps.ServersConfig.ready):
        # keeps the studio -> servers import boundary intact.
        from app.agent_tool_catalog import list_agent_tool_names

        known = list(list_agent_tool_names()) or list(SAFE_DEFAULT_TOOLS)
    denied = set(tool_names)
    return {name: (name not in denied) for name in known}, None


def default_max_iterations(node_type: str = "agent/react") -> int:
    if node_type == "agent/multi":
        return DEFAULT_AGENT_MAX_ITERATIONS_MULTI
    return DEFAULT_AGENT_MAX_ITERATIONS_REACT


def resolve_agent_model_preference(
    config: dict[str, Any] | None,
    *,
    model: str | None = None,
) -> tuple[str, str | None]:
    cfg = config if isinstance(config, dict) else {}
    model_value = model if model is not None else cfg.get("model", DEFAULT_AGENT_MODEL)
    model_value = str(model_value or "").strip() or None
    return resolve_provider_and_model(
        cfg.get("provider"),
        model_value,
        default_provider=DEFAULT_AGENT_PROVIDER,
    )


def resolve_interaction_mode(
    config: dict[str, Any] | None,
    *,
    trigger_type: str = "",
) -> str:
    cfg = config if isinstance(config, dict) else {}
    explicit = str(cfg.get("interaction_mode") or cfg.get("agent_interaction_mode") or "").strip().lower()
    if explicit in {INTERACTION_INTERACTIVE, INTERACTION_UNATTENDED}:
        return explicit
    trigger = str(trigger_type or "").strip().lower()
    if trigger in {"schedule", "webhook", "monitoring"}:
        return INTERACTION_UNATTENDED
    return INTERACTION_INTERACTIVE


def is_unattended_mode(config: dict[str, Any] | None, *, trigger_type: str = "") -> bool:
    return resolve_interaction_mode(config, trigger_type=trigger_type) == INTERACTION_UNATTENDED


def require_all_servers_enabled(config: dict[str, Any] | None, *, default: bool = False) -> bool:
    cfg = config if isinstance(config, dict) else {}
    value = cfg.get("require_all_servers")
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def agent_node_allows_ask_user(config: dict[str, Any] | None) -> bool:
    """True if ask_user is among enabled tools for this node config."""
    cfg = config if isinstance(config, dict) else {}
    tools_config, error = resolve_tools_config(cfg)
    if error:
        return False
    if not tools_config:
        return True
    return bool(tools_config.get("ask_user", False))
