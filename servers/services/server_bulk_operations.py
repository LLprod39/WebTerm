"""Durable execution for safe, group-wide server field updates."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from servers.agents.agent_pilot_policy import user_can_automate
from servers.models_bulk import ServerBulkOperation
from servers.models_inventory import Server

DEFAULT_LEASE_SECONDS = 90


class ServerBulkOperationError(ValueError):
    pass


def normalize_bulk_parameters(action: str, parameters: Any) -> dict[str, Any]:
    params = parameters if isinstance(parameters, dict) else {}
    if action == ServerBulkOperation.ACTION_SET_ACTIVE:
        if not isinstance(params.get("value"), bool):
            raise ServerBulkOperationError("set_active requires a boolean value")
        return {"value": params["value"]}
    if action == ServerBulkOperation.ACTION_SET_AI_READ_ONLY:
        if not isinstance(params.get("value"), bool):
            raise ServerBulkOperationError("set_ai_read_only requires a boolean value")
        return {"value": params["value"]}
    if action == ServerBulkOperation.ACTION_SET_TAGS:
        value = params.get("value")
        if not isinstance(value, str):
            raise ServerBulkOperationError("set_tags requires a string value")
        if len(value) > 500:
            raise ServerBulkOperationError("tags must not exceed 500 characters")
        return {"value": value}
    raise ServerBulkOperationError("unsupported bulk action")


def create_bulk_operation(*, group, project, requested_by, action: str, parameters: Any) -> ServerBulkOperation:
    normalized = normalize_bulk_parameters(action, parameters)
    if (
        action == ServerBulkOperation.ACTION_SET_AI_READ_ONLY
        and normalized["value"] is False
        and not user_can_automate(requested_by)
    ):
        raise ServerBulkOperationError("disabling AI read-only requires automation access")
    target_ids = list(Server.objects.filter(group=group, project=project).order_by("id").values_list("id", flat=True))
    if not target_ids:
        raise ServerBulkOperationError("group has no servers in the active project")
    return ServerBulkOperation.objects.create(
        group=group,
        project=project,
        requested_by=requested_by,
        action=action,
        parameters=normalized,
        target_server_ids=target_ids,
        total_count=len(target_ids),
    )


@transaction.atomic
def claim_bulk_operation(*, worker_id: str, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> ServerBulkOperation | None:
    now = timezone.now()
    operation = (
        ServerBulkOperation.objects.select_for_update()
        .filter(
            Q(status=ServerBulkOperation.STATUS_QUEUED)
            | Q(status=ServerBulkOperation.STATUS_RUNNING, lease_expires_at__lte=now)
        )
        .order_by("created_at", "id")
        .first()
    )
    if operation is None:
        return None
    operation.status = ServerBulkOperation.STATUS_RUNNING
    operation.claimed_by = str(worker_id)[:160]
    operation.started_at = operation.started_at or now
    operation.heartbeat_at = now
    operation.lease_expires_at = now + timedelta(seconds=max(30, int(lease_seconds)))
    operation.save(
        update_fields=[
            "status",
            "claimed_by",
            "started_at",
            "heartbeat_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    return operation


def _update_values(operation: ServerBulkOperation) -> dict[str, Any]:
    value = operation.parameters.get("value")
    if operation.action == ServerBulkOperation.ACTION_SET_ACTIVE:
        return {"is_active": bool(value)}
    if operation.action == ServerBulkOperation.ACTION_SET_AI_READ_ONLY:
        return {"ai_read_only": bool(value)}
    if operation.action == ServerBulkOperation.ACTION_SET_TAGS:
        return {"tags": str(value)}
    raise ServerBulkOperationError("unsupported bulk action")


def _process_one(*, operation_id: int, worker_id: str, server_id: int, lease_seconds: int) -> bool:
    """Apply one idempotent update and persist its cursor in the same transaction."""
    with transaction.atomic():
        operation = ServerBulkOperation.objects.select_for_update().get(pk=operation_id)
        if operation.status != ServerBulkOperation.STATUS_RUNNING or operation.claimed_by != worker_id:
            raise ServerBulkOperationError("bulk operation lease lost")
        server = (
            Server.objects.select_for_update()
            .filter(pk=server_id, group_id=operation.group_id, project_id=operation.project_id)
            .first()
        )
        succeeded = server is not None
        failures = list(operation.failures or [])
        if server is not None:
            Server.objects.filter(pk=server.pk).update(**_update_values(operation))
            operation.succeeded_count += 1
        else:
            operation.failed_count += 1
            if len(failures) < 200:
                failures.append({"server_id": server_id, "error": "server no longer belongs to the group"})
        operation.processed_count += 1
        now = timezone.now()
        operation.failures = failures
        operation.heartbeat_at = now
        operation.lease_expires_at = now + timedelta(seconds=max(30, int(lease_seconds)))
        operation.save(
            update_fields=[
                "processed_count",
                "succeeded_count",
                "failed_count",
                "failures",
                "heartbeat_at",
                "lease_expires_at",
                "updated_at",
            ]
        )
        return succeeded


def process_bulk_operation(
    operation: ServerBulkOperation,
    *,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    max_items: int | None = None,
) -> ServerBulkOperation:
    with transaction.atomic():
        current = (
            ServerBulkOperation.objects.select_for_update(of=("self",))
            .select_related("requested_by")
            .get(pk=operation.pk)
        )
        unsafe_read_only_change = (
            current.action == ServerBulkOperation.ACTION_SET_AI_READ_ONLY and current.parameters.get("value") is False
        )
        if unsafe_read_only_change and not (current.requested_by and user_can_automate(current.requested_by)):
            now = timezone.now()
            current.status = ServerBulkOperation.STATUS_FAILED
            current.failed_count = current.total_count
            current.failures = [
                {
                    "error": "automation capability missing at execution time",
                    "code": "automation_required",
                }
            ]
            current.completed_at = now
            current.heartbeat_at = now
            current.lease_expires_at = now
            current.save(
                update_fields=[
                    "status",
                    "failed_count",
                    "failures",
                    "completed_at",
                    "heartbeat_at",
                    "lease_expires_at",
                    "updated_at",
                ]
            )
            return current
    target_ids = [int(value) for value in (operation.target_server_ids or [])]
    start = max(int(operation.processed_count), 0)
    remaining = target_ids[start:]
    if max_items is not None:
        remaining = remaining[: max(int(max_items), 0)]
    for server_id in remaining:
        _process_one(
            operation_id=operation.pk,
            worker_id=worker_id,
            server_id=server_id,
            lease_seconds=lease_seconds,
        )

    with transaction.atomic():
        current = ServerBulkOperation.objects.select_for_update().get(pk=operation.pk)
        if current.status != ServerBulkOperation.STATUS_RUNNING or current.claimed_by != worker_id:
            raise ServerBulkOperationError("bulk operation lease lost")
        if current.processed_count >= current.total_count:
            now = timezone.now()
            current.status = ServerBulkOperation.STATUS_COMPLETED
            current.completed_at = now
            current.heartbeat_at = now
            current.lease_expires_at = now
            current.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "heartbeat_at",
                    "lease_expires_at",
                    "updated_at",
                ]
            )
        return current


def serialize_bulk_operation(operation: ServerBulkOperation) -> dict[str, Any]:
    total = max(int(operation.total_count), 0)
    processed = min(max(int(operation.processed_count), 0), total)
    progress_percent = round((processed / total) * 100, 1) if total else 100.0
    return {
        "id": operation.pk,
        "group_id": operation.group_id,
        "action": operation.action,
        "parameters": operation.parameters,
        "status": operation.status,
        "total_count": total,
        "processed_count": processed,
        "succeeded_count": operation.succeeded_count,
        "failed_count": operation.failed_count,
        "progress_percent": progress_percent,
        "failures": list(operation.failures or []),
        "created_at": operation.created_at.isoformat(),
        "started_at": operation.started_at.isoformat() if operation.started_at else None,
        "completed_at": operation.completed_at.isoformat() if operation.completed_at else None,
    }
