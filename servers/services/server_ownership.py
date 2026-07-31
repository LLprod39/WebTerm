"""Transactional server ownership transfer and access revocation."""

from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from core_ui.projects import user_can_write_project
from servers.models_inventory import Server, ServerConnection, ServerShare


class ServerOwnershipTransferError(ValueError):
    pass


def server_access_group_name(server_id: int) -> str:
    return f"server_access_{int(server_id)}"


def _broadcast_access_revoked(server_id: int) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        server_access_group_name(server_id),
        {
            "type": "server.access.revoked",
            "server_id": int(server_id),
            "reason": "server_owner_changed",
        },
    )


@transaction.atomic
def transfer_server_ownership(*, server_id: int, actor, target_user_id: int) -> dict:
    # of=("self",) is required: Server.group is nullable, so select_related emits a
    # LEFT OUTER JOIN and PostgreSQL refuses a bare FOR UPDATE over it. The transfer
    # only needs the server row locked.
    server = (
        Server.objects.select_for_update(of=("self",)).select_related("group", "project").filter(pk=server_id).first()
    )
    if server is None:
        raise ServerOwnershipTransferError("server not found")
    if not (getattr(actor, "is_staff", False) or server.user_id == getattr(actor, "id", None)):
        raise ServerOwnershipTransferError("only the current owner or staff may transfer this server")
    if server.user_id == int(target_user_id):
        raise ServerOwnershipTransferError("target user already owns this server")

    target = get_user_model().objects.select_for_update().filter(pk=target_user_id, is_active=True).first()
    if target is None:
        raise ServerOwnershipTransferError("active target user not found")
    if not user_can_write_project(target, server.project):
        raise ServerOwnershipTransferError("target user must be an owner, admin, or operator in the server project")

    old_owner_id = server.user_id
    cleared_group_id = None
    if server.group_id and server.group.user_id != target.id:
        cleared_group_id = server.group_id
        server.group = None

    # A share is redundant for the new owner. A stale share for the former
    # owner would accidentally preserve access after the transfer.
    ServerShare.objects.filter(server=server, user_id__in=[target.id, old_owner_id]).delete()
    detached_agent_count = server.agents.exclude(user_id=target.id).count()
    if detached_agent_count:
        for agent in server.agents.exclude(user_id=target.id).only("id"):
            agent.servers.remove(server)

    server.user = target
    server.save(update_fields=["user", "group", "updated_at"])
    disconnected_at = timezone.now()
    closed_connections = (
        ServerConnection.objects.filter(server=server)
        .exclude(status="disconnected")
        .update(
            status="disconnected",
            disconnected_at=disconnected_at,
            last_seen_at=disconnected_at,
        )
    )

    def revoke_runtime_access() -> None:
        from servers.services.ssh_pool import invalidate_ssh_connections

        invalidate_ssh_connections(server.pk)
        _broadcast_access_revoked(server.pk)

    transaction.on_commit(revoke_runtime_access)
    return {
        "server": server,
        "old_owner_id": old_owner_id,
        "new_owner_id": target.id,
        "cleared_group_id": cleared_group_id,
        "closed_connection_count": closed_connections,
        "detached_agent_count": detached_agent_count,
    }
