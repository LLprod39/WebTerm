from __future__ import annotations

from .docker_service_recovery_commands import (
    _build_container_snapshot_command,
    _build_container_verify_command,
)
from .docker_service_recovery_graph import (
    build_docker_service_recovery_edges,
    build_docker_service_recovery_nodes,
)
from .models import CURRENT_PIPELINE_GRAPH_VERSION, Pipeline
from .services import get_first_owned_server_id, get_owned_server_name, has_owned_server

DOCKER_RECOVERY_PIPELINE_TAGS = [
    "studio",
    "monitoring",
    "docker",
    "incident-response",
    "telegram",
    "recovery",
    "ai-first",
]

__all__ = [
    "DOCKER_RECOVERY_PIPELINE_TAGS",
    "_build_container_snapshot_command",
    "_build_container_verify_command",
    "build_docker_service_recovery_edges",
    "build_docker_service_recovery_nodes",
    "ensure_docker_service_recovery_pipeline",
]


def _resolve_server_id(user, requested_server_id: int | None = None) -> int:
    if requested_server_id:
        if not has_owned_server(user, requested_server_id, server_type="ssh"):
            raise ValueError(f"SSH-сервер {requested_server_id} не найден у пользователя {user.username}.")
        return int(requested_server_id)
    server_id = get_first_owned_server_id(user, server_type="ssh", order_by="id")
    if not server_id:
        raise ValueError(f"У пользователя {user.username} нет SSH-серверов для recovery pipeline.")
    return int(server_id)


def _resolve_server_name(user, server_id: int) -> str:
    return get_owned_server_name(user, server_id)


def ensure_docker_service_recovery_pipeline(
    user,
    *,
    container_name: str,
    server_id: int | None = None,
    name: str | None = None,
) -> Pipeline:
    resolved_server_id = _resolve_server_id(user, server_id)
    resolved_server_name = _resolve_server_name(user, resolved_server_id)
    container_label = str(container_name or "").strip()
    if not container_label:
        raise ValueError("container_name is required")

    pipeline_name = name or f"Docker Recovery: {container_label}"
    pipeline_description = (
        "AI-first monitoring recovery pipeline for a Docker container. "
        "When monitoring reports a critical container failure, the pipeline gathers diagnostics, "
        "runs an AI investigation, prepares a recovery plan, sends it to Telegram for approval, "
        "tries AI-driven recovery, and if needed loops through plain-text Telegram instructions "
        "from the operator before producing a final report."
    )

    pipeline, _ = Pipeline.objects.update_or_create(
        owner=user,
        name=pipeline_name,
        defaults={
            "description": pipeline_description,
            "icon": "🚨",
            "tags": list(DOCKER_RECOVERY_PIPELINE_TAGS),
            "nodes": build_docker_service_recovery_nodes(
                server_id=resolved_server_id,
                container_name=container_label,
                server_name=resolved_server_name,
            ),
            "edges": build_docker_service_recovery_edges(),
            "graph_version": CURRENT_PIPELINE_GRAPH_VERSION,
            "is_shared": False,
        },
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline
