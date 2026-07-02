from __future__ import annotations

import asyncio
import os
from typing import Any

from django.contrib.auth import get_user_model
from django.utils import timezone

from core_ui.models import UserAppPermission
from studio.mcp_client import list_mcp_tools
from studio.models import MCPServerPool

DEFAULT_KUBERNETES_MCP_NAME = "Kubernetes MCP"
DEFAULT_KUBERNETES_MCP_URL = "http://mcp-demo:8765/mcp"
REQUIRED_STUDIO_FEATURES = ("kubernetes", "studio_pipelines", "studio_mcp")
REQUIRED_KUBERNETES_MCP_TOOL = "kubernetes_describe_workload"


def resolve_kubernetes_mcp_url(raw_url: str | None = None) -> str:
    return (raw_url or os.getenv("KUBERNETES_OPS_MCP_URL") or DEFAULT_KUBERNETES_MCP_URL).strip()


def resolve_kubernetes_mcp_user(username: str | None = None):
    User = get_user_model()
    if username:
        return User.objects.filter(username=username).first()
    return User.objects.filter(is_active=True, is_staff=True).order_by("-is_superuser", "id").first()


def grant_kubernetes_studio_features(user) -> list[str]:
    granted: list[str] = []
    for feature in REQUIRED_STUDIO_FEATURES:
        _permission, created = UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )
        if created:
            granted.append(feature)
    return granted


def _tool_names(tools: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("name") or "").strip() for item in tools if isinstance(item, dict)}


def ensure_kubernetes_studio_mcp_binding(
    *,
    user,
    url: str | None = None,
    name: str = DEFAULT_KUBERNETES_MCP_NAME,
    test_connection: bool = True,
) -> dict[str, Any]:
    mcp_url = resolve_kubernetes_mcp_url(url)
    granted_features = grant_kubernetes_studio_features(user)
    mcp, created = MCPServerPool.objects.update_or_create(
        owner=user,
        name=name,
        defaults={
            "description": "Read-only Kubernetes MCP binding for WebTerm Kubernetes Ops diagnosis drafts.",
            "transport": MCPServerPool.TRANSPORT_SSE,
            "command": "",
            "args": [],
            "env": {},
            "url": mcp_url,
            "is_shared": False,
        },
    )

    tool_names: set[str] = set()
    test_error = ""
    if test_connection:
        try:
            tools = asyncio.run(list_mcp_tools(mcp))
            tool_names = _tool_names(tools)
            if REQUIRED_KUBERNETES_MCP_TOOL not in tool_names:
                test_error = f"MCP server does not expose `{REQUIRED_KUBERNETES_MCP_TOOL}`."
                mcp.last_test_ok = False
            else:
                mcp.last_test_ok = True
        except Exception as exc:
            test_error = str(exc)
            mcp.last_test_ok = False
        mcp.last_test_at = timezone.now()
        mcp.last_test_error = test_error
        mcp.save(update_fields=["last_test_ok", "last_test_at", "last_test_error"])

    return {
        "created": created,
        "mcp": mcp,
        "url": mcp_url,
        "granted_features": granted_features,
        "test_connection": test_connection,
        "tool_names": sorted(tool_names),
        "required_tool": REQUIRED_KUBERNETES_MCP_TOOL,
        "ok": mcp.last_test_ok,
        "error": test_error,
    }
