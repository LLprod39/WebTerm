from __future__ import annotations

from app.agent_kernel.domain.specs import ToolSpec


def _infer_tool_spec(name: str, description: str, params: dict, *, runner: str = "agent", is_mcp: bool = False) -> ToolSpec:
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


class ToolRegistry:
    def __init__(self, specs: dict[str, ToolSpec]):
        self.specs = specs

    @classmethod
    def from_sources(cls, enabled_tools: list[str], mcp_tools: dict | None = None) -> ToolRegistry:
        from servers.agent_tools import AGENT_TOOLS

        specs: dict[str, ToolSpec] = {}
        for name in enabled_tools:
            meta = AGENT_TOOLS.get(name)
            if not meta:
                continue
            specs[name] = _infer_tool_spec(name, meta.get("description") or "", meta.get("params") or {}, runner="agent")
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
