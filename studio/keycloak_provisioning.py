from __future__ import annotations

from .keycloak_ops_approval import build_keycloak_ops_edges
from .keycloak_ops_graph import build_keycloak_ops_nodes
from .keycloak_provisioning_config import (
    KEYCLOAK_CLIENT_DISCOVERY_TOOLS,
    KEYCLOAK_GROUP_ROLE_DISCOVERY_TOOLS,
    KEYCLOAK_IDENTITY_EXECUTION_TOOLS,
    KEYCLOAK_IDENTITY_VERIFY_TOOLS,
    KEYCLOAK_MCP_NAME,
    KEYCLOAK_MCP_URL,
    KEYCLOAK_OPS_PIPELINE_SPECS,
    KEYCLOAK_PIPELINE_DESCRIPTION,
    KEYCLOAK_PIPELINE_NAME,
    KEYCLOAK_PLATFORM_EXECUTION_TOOLS,
    KEYCLOAK_PLATFORM_VERIFY_TOOLS,
    KEYCLOAK_PROTOCOL_MAPPER_DISCOVERY_TOOLS,
    KEYCLOAK_USER_DISCOVERY_TOOLS,
    SAMPLE_BULK_TASK_CONTEXT,
    SAMPLE_MANUAL_CONTEXT,
    SAMPLE_TASK_CONTEXT,
    TASK_WEBHOOK_CONTEXT_MAP,
    WEBHOOK_CONTEXT_MAP,
)
from .keycloak_provisioning_graph import build_keycloak_edges, build_keycloak_nodes
from .models import CURRENT_PIPELINE_GRAPH_VERSION, MCPServerPool, Pipeline


def ensure_keycloak_mcp_server(user) -> MCPServerPool:
    server, _ = MCPServerPool.objects.update_or_create(
        owner=user,
        name=KEYCLOAK_MCP_NAME,
        defaults={
            "description": (
                "URL-based Keycloak admin MCP for user, role, client, and group provisioning. "
                "Recommended to run as docker-compose service mcp-keycloak."
            ),
            "transport": MCPServerPool.TRANSPORT_SSE,
            "command": "",
            "args": [],
            "env": {},
            "url": KEYCLOAK_MCP_URL,
            "is_shared": False,
        },
    )
    return server


def ensure_keycloak_pipeline(user, mcp_server: MCPServerPool) -> Pipeline:
    pipeline, _ = Pipeline.objects.update_or_create(
        owner=user,
        name=KEYCLOAK_PIPELINE_NAME,
        defaults={
            "description": KEYCLOAK_PIPELINE_DESCRIPTION,
            "icon": "KEY",
            "tags": ["mcp", "keycloak", "iam", "approval", "provisioning", "studio"],
            "nodes": build_keycloak_nodes(mcp_server.id),
            "edges": build_keycloak_edges(),
            "graph_version": CURRENT_PIPELINE_GRAPH_VERSION,
            "is_shared": False,
        },
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline


def ensure_keycloak_ops_pipeline(user, mcp_server: MCPServerPool, *, profile_name: str) -> Pipeline:
    spec = KEYCLOAK_OPS_PIPELINE_SPECS[profile_name]
    pipeline, _ = Pipeline.objects.update_or_create(
        owner=user,
        name=spec["name"],
        defaults={
            "description": spec["description"],
            "icon": "KEY",
            "tags": ["mcp", "keycloak", "iam", "direct", "studio", profile_name],
            "nodes": build_keycloak_ops_nodes(
                mcp_server.id,
                fixed_profile=profile_name,
                environment_label=spec["label"],
            ),
            "edges": build_keycloak_ops_edges(),
            "graph_version": CURRENT_PIPELINE_GRAPH_VERSION,
            "is_shared": False,
        },
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline


def ensure_keycloak_ops_pipelines(user, mcp_server: MCPServerPool) -> dict[str, Pipeline]:
    return {
        profile_name: ensure_keycloak_ops_pipeline(user, mcp_server, profile_name=profile_name)
        for profile_name in KEYCLOAK_OPS_PIPELINE_SPECS
    }


__all__ = [
    "KEYCLOAK_CLIENT_DISCOVERY_TOOLS",
    "KEYCLOAK_GROUP_ROLE_DISCOVERY_TOOLS",
    "KEYCLOAK_IDENTITY_EXECUTION_TOOLS",
    "KEYCLOAK_IDENTITY_VERIFY_TOOLS",
    "KEYCLOAK_MCP_NAME",
    "KEYCLOAK_MCP_URL",
    "KEYCLOAK_OPS_PIPELINE_SPECS",
    "KEYCLOAK_PIPELINE_DESCRIPTION",
    "KEYCLOAK_PIPELINE_NAME",
    "KEYCLOAK_PLATFORM_EXECUTION_TOOLS",
    "KEYCLOAK_PLATFORM_VERIFY_TOOLS",
    "KEYCLOAK_PROTOCOL_MAPPER_DISCOVERY_TOOLS",
    "KEYCLOAK_USER_DISCOVERY_TOOLS",
    "SAMPLE_BULK_TASK_CONTEXT",
    "SAMPLE_MANUAL_CONTEXT",
    "SAMPLE_TASK_CONTEXT",
    "TASK_WEBHOOK_CONTEXT_MAP",
    "WEBHOOK_CONTEXT_MAP",
    "build_keycloak_edges",
    "build_keycloak_nodes",
    "build_keycloak_ops_edges",
    "build_keycloak_ops_nodes",
    "ensure_keycloak_mcp_server",
    "ensure_keycloak_ops_pipeline",
    "ensure_keycloak_ops_pipelines",
    "ensure_keycloak_pipeline",
]
