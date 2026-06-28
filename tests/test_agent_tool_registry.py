from app.agent_kernel.tools.registry import ToolRegistry
from app.plugins.agent_tools import plugin_agent_tool_specs
from servers import agent_tools


def test_builtin_agent_tools_declare_policy_metadata():
    for name, meta in agent_tools.AGENT_TOOLS.items():
        assert "tool_spec" in meta, f"{name} must declare tool_spec metadata"
        assert meta["tool_spec"]["category"]
        assert meta["tool_spec"]["risk"]


def test_tool_registry_uses_declared_metadata_before_name_inference(monkeypatch):
    monkeypatch.setitem(
        agent_tools.AGENT_TOOLS,
        "keycloak_readonly_report",
        {
            "fn": lambda *_args, **_kwargs: None,
            "description": "Read-only report with a name that would match legacy keycloak inference.",
            "params": {},
            "tool_spec": {
                "category": "general",
                "risk": "read",
                "output_compactor": "tail",
            },
        },
    )

    registry = ToolRegistry.from_sources(
        ["ssh_execute", "keycloak_readonly_report"],
        agent_tools=agent_tools.AGENT_TOOLS,
    )

    ssh_spec = registry.get("ssh_execute")
    assert ssh_spec is not None
    assert ssh_spec.category == "ssh"
    assert ssh_spec.risk == "exec"
    assert ssh_spec.requires_verification is True

    readonly_spec = registry.get("keycloak_readonly_report")
    assert readonly_spec is not None
    assert readonly_spec.category == "general"
    assert readonly_spec.risk == "read"
    assert readonly_spec.mutates_state is False


def test_plugin_agent_tools_require_explicit_tool_spec():
    registry = ToolRegistry.from_sources(
        ["plugin_missing_spec"],
        agent_tools={
            "plugin_missing_spec": {
                "plugin_id": "webtrerm.demo-dashboard",
                "description": "No explicit metadata.",
                "params": {},
            }
        },
    )

    assert registry.get("plugin_missing_spec") is None


def test_plugin_agent_tool_specs_project_declared_metadata():
    specs = plugin_agent_tool_specs({"webtrerm.demo-dashboard"})
    spec = specs["plugin_webtrerm_demo_dashboard_ping"]

    assert spec["plugin_id"] == "webtrerm.demo-dashboard"
    assert spec["tool_spec"]["runner"] == "plugin"
    assert spec["tool_spec"]["risk"] == "network"
