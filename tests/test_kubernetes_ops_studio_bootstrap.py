from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError

from core_ui.models import UserAppPermission
from kubernetes_ops.studio_bootstrap import ensure_kubernetes_studio_mcp_binding
from studio.demo_mcp_tools import TOOL_HANDLERS, TOOLS
from studio.models import MCPServerPool


def test_demo_mcp_exposes_read_only_kubernetes_describe_tool():
    tool_names = {item["name"] for item in TOOLS}

    assert "kubernetes_describe_workload" in tool_names

    result = TOOL_HANDLERS["kubernetes_describe_workload"](
        {
            "cluster": "prod-kz-context",
            "namespace": "payments",
            "kind": "deployment",
            "name": "payments-api",
        }
    )

    assert result["structuredContent"]["target"]["namespace"] == "payments"
    assert result["structuredContent"]["policy"]["permission_mode"] == "READ_ONLY"
    assert result["structuredContent"]["policy"]["mutates_state"] is False
    assert "restart" in result["structuredContent"]["policy"]["blocked_actions"]
    assert "MUTATES_STATE: false" in result["content"][0]["text"]


@pytest.mark.django_db
def test_ensure_kubernetes_studio_mcp_binding_grants_features_and_tests_tool(monkeypatch):
    async def fake_list_mcp_tools(_mcp):
        return [{"name": "kubernetes_describe_workload"}]

    monkeypatch.setattr("kubernetes_ops.studio_bootstrap.list_mcp_tools", fake_list_mcp_tools)
    user = User.objects.create_user(username="k8s-bootstrap-admin", password="x", is_staff=True)

    result = ensure_kubernetes_studio_mcp_binding(user=user, url="http://mcp-demo:8765/mcp")

    mcp = result["mcp"]
    assert result["ok"] is True
    assert mcp.name == "Kubernetes MCP"
    assert mcp.transport == MCPServerPool.TRANSPORT_SSE
    assert mcp.url == "http://mcp-demo:8765/mcp"
    assert mcp.last_test_ok is True
    assert set(UserAppPermission.objects.filter(user=user, allowed=True).values_list("feature", flat=True)) >= {
        "kubernetes",
        "studio_pipelines",
        "studio_mcp",
    }


@pytest.mark.django_db
def test_ensure_kubernetes_ops_studio_binding_command_marks_missing_tool_failed(monkeypatch):
    async def fake_list_mcp_tools(_mcp):
        return [{"name": "workspace_snapshot"}]

    monkeypatch.setattr("kubernetes_ops.studio_bootstrap.list_mcp_tools", fake_list_mcp_tools)
    user = User.objects.create_user(username="k8s-bootstrap-missing-tool", password="x", is_staff=True)
    out = StringIO()

    with pytest.raises(CommandError, match="kubernetes_describe_workload"):
        call_command(
            "ensure_kubernetes_ops_studio_binding",
            "--username",
            user.username,
            stdout=out,
        )

    mcp = MCPServerPool.objects.get(owner=user, name="Kubernetes MCP")
    assert mcp.last_test_ok is False
    assert "kubernetes_describe_workload" in mcp.last_test_error
