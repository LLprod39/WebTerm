from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.agent_kernel.domain.specs import ToolSpec

logger = logging.getLogger(__name__)


def _infer_tool_spec(
    name: str, description: str, params: dict, *, runner: str = "agent", is_mcp: bool = False
) -> ToolSpec:
    category = "general"
    risk = "read"
    mutates_state = False
    requires_verification = False

    if is_mcp:
        category = "mcp"
        risk = "network"
    elif name == "ssh_execute":
        category = "ssh"
        risk = "exec"
        requires_verification = True
    elif name in {"read_console", "wait_for_output"}:
        category = "monitoring"
        risk = "read"
    elif name in {"open_connection", "close_connection", "send_ctrl_c"}:
        category = "service"
        risk = "exec"
    elif name in {"ask_user", "report"}:
        category = "general"
        risk = "read"
    elif "docker" in name:
        category = "docker"
        risk = "exec"
        requires_verification = True
    elif "nginx" in name:
        category = "nginx"
        risk = "exec"
        requires_verification = True
    elif "keycloak" in name:
        category = "keycloak"
        risk = "admin"
        mutates_state = True
        requires_verification = True

    return ToolSpec(
        name=name,
        category=category,
        risk=risk,
        description=description,
        input_schema=params or {},
        mutates_state=mutates_state,
        requires_verification=requires_verification,
        output_compactor="tail",
        runner=runner,
    )


def _tool_spec_from_declared_metadata(name: str, meta: Mapping[str, Any], *, runner: str = "agent") -> ToolSpec | None:
    declared = meta.get("tool_spec")
    if not isinstance(declared, Mapping):
        return None

    output_compactor = declared.get("output_compactor", "tail")
    return ToolSpec(
        name=name,
        category=declared["category"],
        risk=declared["risk"],
        description=str(declared.get("description") or meta.get("description") or ""),
        input_schema=dict(declared.get("input_schema") or meta.get("params") or {}),
        mutates_state=bool(declared.get("mutates_state", False)),
        requires_preflight=tuple(str(item) for item in declared.get("requires_preflight", ())),
        requires_verification=bool(declared.get("requires_verification", False)),
        output_compactor=str(output_compactor) if output_compactor is not None else None,
        runner=str(declared.get("runner") or runner),
    )


class ToolRegistry:
    def __init__(self, specs: dict[str, ToolSpec]):
        self.specs = specs

    @classmethod
    def from_sources(
        cls,
        enabled_tools: list[str],
        mcp_tools: dict | None = None,
        *,
        agent_tools: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> ToolRegistry:
        if enabled_tools and agent_tools is None:
            logger.warning("No built-in agent tool source supplied; only MCP tool specs will be registered.")
        agent_tool_source = agent_tools or {}
        specs: dict[str, ToolSpec] = {}
        for name in enabled_tools:
            meta = agent_tool_source.get(name)
            if not meta:
                continue
            declared = _tool_spec_from_declared_metadata(name, meta, runner="agent")
            if declared is not None:
                specs[name] = declared
                continue
            if meta.get("plugin_id"):
                logger.warning("Plugin agent tool %s is missing explicit tool_spec metadata; skipping.", name)
                continue
            logger.warning("Agent tool %s is missing explicit tool_spec metadata; using compatibility inference.", name)
            specs[name] = _infer_tool_spec(
                name, meta.get("description") or "", meta.get("params") or {}, runner="agent"
            )
        for name, binding in (mcp_tools or {}).items():
            specs[name] = _infer_tool_spec(
                name,
                getattr(binding, "description", "") or getattr(binding, "tool_name", name),
                getattr(binding, "input_schema", None) or {},
                runner="mcp",
                is_mcp=True,
            )
        return cls(specs)

    def get(self, name: str) -> ToolSpec | None:
        return self.specs.get(name)

    def subset(
        self,
        *,
        allowed_names: list[str] | tuple[str, ...] | set[str] | None = None,
        allowed_categories: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> ToolRegistry:
        names_filter = set(allowed_names) if allowed_names is not None else None
        categories_filter = set(allowed_categories) if allowed_categories is not None else None
        specs: dict[str, ToolSpec] = {}
        for name, spec in self.specs.items():
            if names_filter is not None and name not in names_filter:
                continue
            if categories_filter is not None and spec.category not in categories_filter:
                continue
            specs[name] = spec
        return ToolRegistry(specs)

    def names(self) -> tuple[str, ...]:
        return tuple(self.specs.keys())

    def build_prompt_slice(self, *, limit: int = 10) -> str:
        lines = [spec.prompt_line() for spec in list(self.specs.values())[:limit]]
        return "\n".join(lines)
