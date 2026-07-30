from __future__ import annotations

from .all_nodes_smoke_branches import (
    LOCAL_WEBHOOK_TARGET,
    STANDARD_BRANCH_TARGET_IDS,
    TELEGRAM_INPUT_TARGET_ID,
    build_probe_nodes,
)
from .all_nodes_smoke_flow import build_collector_nodes, build_entry_nodes, build_smoke_edges
from .mcp.mcp_showcase import ensure_demo_mcp_server
from .models import CURRENT_PIPELINE_GRAPH_VERSION, MCPServerPool, Pipeline
from .services import get_first_owned_server_id, list_owned_server_ids

ALL_NODES_SMOKE_PIPELINE_NAME = "All Nodes Smoke Test"
ALL_NODES_SMOKE_DESCRIPTION = (
    "Большой smoke-пайплайн Studio V2 со всеми встроенными типами узлов. "
    "Он предназначен для ручной проверки, использует только read-only проверки серверов, "
    "локальный webhook POST, короткие ожидания и безопасно отключенные email/telegram-узлы без реальных изменений."
)
ALL_NODES_SMOKE_TAGS = ["studio", "smoke", "all-nodes", "safe", "qa"]

__all__ = [
    "ALL_NODES_SMOKE_DESCRIPTION",
    "ALL_NODES_SMOKE_PIPELINE_NAME",
    "ALL_NODES_SMOKE_TAGS",
    "LOCAL_WEBHOOK_TARGET",
    "build_all_nodes_smoke_edges",
    "build_all_nodes_smoke_nodes",
    "ensure_all_nodes_smoke_pipeline",
]


def _resolve_server_ids(user, *, limit: int = 2) -> list[int]:
    return list_owned_server_ids(user, limit=limit, order_by="id")


def _resolve_ssh_server_id(user) -> int | None:
    return get_first_owned_server_id(user, order_by="id")


def _resolve_mcp_server_id(user) -> int | None:
    if getattr(user, "is_staff", False):
        return ensure_demo_mcp_server(user).id
    return MCPServerPool.objects.filter(owner=user).order_by("id").values_list("id", flat=True).first()


def build_all_nodes_smoke_nodes(
    *,
    server_ids: list[int] | None = None,
    ssh_server_id: int | None = None,
    mcp_server_id: int | None = None,
) -> list[dict]:
    bounded_server_ids = [int(server_id) for server_id in (server_ids or []) if server_id]
    primary_server_ids = bounded_server_ids[:1]
    multi_server_ids = bounded_server_ids[:2]
    return [
        *build_entry_nodes(primary_server_ids=primary_server_ids),
        *build_probe_nodes(
            primary_server_ids=primary_server_ids,
            multi_server_ids=multi_server_ids,
            ssh_server_id=ssh_server_id,
            mcp_server_id=mcp_server_id,
        ),
        *build_collector_nodes(),
    ]


def build_all_nodes_smoke_edges() -> list[dict]:
    return build_smoke_edges(
        standard_branch_targets=STANDARD_BRANCH_TARGET_IDS,
        telegram_input_target=TELEGRAM_INPUT_TARGET_ID,
    )


def ensure_all_nodes_smoke_pipeline(user) -> Pipeline:
    server_ids = _resolve_server_ids(user, limit=2)
    ssh_server_id = _resolve_ssh_server_id(user)
    mcp_server_id = _resolve_mcp_server_id(user)
    pipeline, _ = Pipeline.objects.update_or_create(
        owner=user,
        name=ALL_NODES_SMOKE_PIPELINE_NAME,
        defaults={
            "description": ALL_NODES_SMOKE_DESCRIPTION,
            "icon": "🧰",
            "tags": list(ALL_NODES_SMOKE_TAGS),
            "nodes": build_all_nodes_smoke_nodes(
                server_ids=server_ids,
                ssh_server_id=ssh_server_id,
                mcp_server_id=mcp_server_id,
            ),
            "edges": build_all_nodes_smoke_edges(),
            "graph_version": CURRENT_PIPELINE_GRAPH_VERSION,
            "is_shared": False,
        },
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline
