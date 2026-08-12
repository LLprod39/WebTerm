from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from core_ui.models import ProjectMembership, UserActivityLog, UserAppPermission
from core_ui.projects import ensure_default_project
from core_ui.views.access_views import _apply_access_profile
from servers.consumers.ssh_terminal import SSHTerminalConsumer
from servers.models import (
    Server,
    ServerBulkOperation,
    ServerConnection,
    ServerGroup,
    ServerGroupMember,
    ServerShare,
)
from servers.services.server_bulk_operations import claim_bulk_operation, process_bulk_operation
from tests.servers_api_smoke_harness import grant_feature, json_payload


def _project_operator(project, user):
    return ProjectMembership.objects.create(project=project, user=user, role=ProjectMembership.ROLE_OPERATOR)


@pytest.mark.django_db(transaction=True)
def test_server_owner_transfer_preserves_server_and_revokes_old_runtime_access(monkeypatch):
    owner = User.objects.create_user(username="owner-transfer", password="x")
    target = User.objects.create_user(username="target-transfer", password="x")
    grant_feature(owner, "servers")
    project = ensure_default_project(owner)
    _project_operator(project, target)
    group = ServerGroup.objects.create(user=owner, name="owner-only-group")
    ServerGroupMember.objects.create(group=group, user=owner, role="owner")
    server = Server.objects.create(
        user=owner,
        project=project,
        group=group,
        name="durable-server",
        host="10.1.2.3",
        username="root",
    )
    ServerShare.objects.create(server=server, user=target, shared_by=owner, can_connect_terminal=True)
    connection = ServerConnection.objects.create(
        server=server,
        user=owner,
        connection_id="ownership-transfer-live",
        status="connected",
    )
    invalidated: list[int] = []
    broadcast: list[int] = []
    monkeypatch.setattr("servers.services.ssh_pool.invalidate_ssh_connections", invalidated.append)
    monkeypatch.setattr("servers.services.server_ownership._broadcast_access_revoked", broadcast.append)

    client = Client()
    client.force_login(owner)
    response = client.post(
        f"/servers/api/{server.pk}/transfer-owner/",
        data=json_payload({"target_user_id": target.pk}),
        content_type="application/json",
    )

    assert response.status_code == 200
    server.refresh_from_db()
    connection.refresh_from_db()
    assert server.user_id == target.id
    assert server.project_id == project.id
    assert server.group_id is None
    assert connection.status == "disconnected"
    assert connection.disconnected_at is not None
    assert not ServerShare.objects.filter(server=server, user=target).exists()
    assert invalidated and set(invalidated) == {server.id}
    assert broadcast == [server.id]
    event = UserActivityLog.objects.get(action="server_owner_transfer", entity_id=str(server.id))
    assert event.metadata["old_owner_id"] == owner.id
    assert event.metadata["new_owner_id"] == target.id
    assert event.metadata["closed_connection_count"] == 1


@pytest.mark.django_db
def test_server_owner_transfer_rejects_viewer_and_non_owner():
    owner = User.objects.create_user(username="owner-transfer-denied", password="x")
    viewer = User.objects.create_user(username="viewer-transfer-denied", password="x")
    outsider = User.objects.create_user(username="outsider-transfer-denied", password="x")
    grant_feature(owner, "servers")
    grant_feature(outsider, "servers")
    project = ensure_default_project(owner)
    ProjectMembership.objects.create(project=project, user=viewer, role=ProjectMembership.ROLE_VIEWER)
    server = Server.objects.create(
        user=owner,
        project=project,
        name="protected-server",
        host="10.1.2.4",
        username="root",
    )

    owner_client = Client()
    owner_client.force_login(owner)
    viewer_response = owner_client.post(
        f"/servers/api/{server.pk}/transfer-owner/",
        data=json_payload({"target_user_id": viewer.pk}),
        content_type="application/json",
    )
    assert viewer_response.status_code == 400

    outsider_client = Client()
    outsider_client.force_login(outsider)
    outsider_response = outsider_client.post(
        f"/servers/api/{server.pk}/transfer-owner/",
        data=json_payload({"target_user_id": viewer.pk}),
        content_type="application/json",
    )
    assert outsider_response.status_code == 403
    server.refresh_from_db()
    assert server.user_id == owner.id


@pytest.mark.django_db
def test_group_bulk_action_reports_progress_and_resumes_expired_lease():
    owner = User.objects.create_user(username="bulk-owner", password="x")
    grant_feature(owner, "servers")
    project = ensure_default_project(owner)
    group = ServerGroup.objects.create(user=owner, name="bulk-group")
    ServerGroupMember.objects.create(group=group, user=owner, role="owner")
    servers = [
        Server.objects.create(
            user=owner,
            project=project,
            group=group,
            name=f"bulk-{index}",
            host=f"10.2.0.{index}",
            username="root",
            is_active=True,
        )
        for index in range(1, 4)
    ]
    client = Client()
    client.force_login(owner)
    queued = client.post(
        f"/servers/api/groups/{group.pk}/bulk-actions/",
        data=json_payload({"action": "set_active", "parameters": {"value": False}}),
        content_type="application/json",
    )
    assert queued.status_code == 202
    operation_id = queued.json()["operation"]["id"]

    claimed = claim_bulk_operation(worker_id="worker-a", lease_seconds=30)
    assert claimed is not None and claimed.pk == operation_id
    partial = process_bulk_operation(claimed, worker_id="worker-a", lease_seconds=30, max_items=1)
    assert partial.status == ServerBulkOperation.STATUS_RUNNING
    assert partial.processed_count == 1
    ServerBulkOperation.objects.filter(pk=operation_id).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
    reclaimed = claim_bulk_operation(worker_id="worker-b", lease_seconds=30)
    assert reclaimed is not None and reclaimed.pk == operation_id
    completed = process_bulk_operation(reclaimed, worker_id="worker-b", lease_seconds=30)
    assert completed.status == ServerBulkOperation.STATUS_COMPLETED
    assert completed.processed_count == 3
    assert completed.succeeded_count == 3
    assert not Server.objects.filter(pk__in=[server.pk for server in servers], is_active=True).exists()

    detail = client.get(f"/servers/api/bulk-actions/{operation_id}/")
    assert detail.status_code == 200
    payload = detail.json()["operation"]
    assert payload["progress_percent"] == 100.0
    assert payload["status"] == "completed"


@pytest.mark.django_db
def test_group_bulk_cannot_disable_read_only_without_live_automation_capability():
    owner = User.objects.create_user(username="bulk-read-only-owner", password="x")
    grant_feature(owner, "servers")
    project = ensure_default_project(owner)
    group = ServerGroup.objects.create(user=owner, name="bulk-read-only-group")
    ServerGroupMember.objects.create(group=group, user=owner, role="owner")
    server = Server.objects.create(
        user=owner,
        project=project,
        group=group,
        name="bulk-read-only",
        host="10.2.1.10",
        username="root",
        ai_read_only=True,
    )
    client = Client()
    client.force_login(owner)
    payload = {"action": "set_ai_read_only", "parameters": {"value": False}}

    denied = client.post(
        f"/servers/api/groups/{group.pk}/bulk-actions/",
        data=json_payload(payload),
        content_type="application/json",
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "automation_required"
    assert not ServerBulkOperation.objects.exists()

    _apply_access_profile(owner, "pilot_operator")
    queued = client.post(
        f"/servers/api/groups/{group.pk}/bulk-actions/",
        data=json_payload(payload),
        content_type="application/json",
    )
    assert queued.status_code == 202
    operation = claim_bulk_operation(worker_id="policy-worker", lease_seconds=30)
    UserAppPermission.objects.filter(user=owner, feature="automation").delete()

    result = process_bulk_operation(operation, worker_id="policy-worker", lease_seconds=30)

    assert result.status == ServerBulkOperation.STATUS_FAILED
    server.refresh_from_db()
    assert server.ai_read_only is True


def test_terminal_access_revocation_event_closes_matching_socket(monkeypatch):
    consumer = SSHTerminalConsumer()
    consumer.server = SimpleNamespace(id=91)
    sent: list[dict] = []
    disconnected: list[bool] = []
    closed: list[int] = []

    async def safe_send(payload):
        sent.append(payload)

    async def disconnect_ssh():
        disconnected.append(True)

    async def close(*, code):
        closed.append(code)

    monkeypatch.setattr(consumer.terminal_transport, "_safe_send_json", safe_send)
    monkeypatch.setattr(consumer.terminal_transport, "_disconnect_ssh", disconnect_ssh)
    monkeypatch.setattr(consumer, "close", close)

    async_to_sync(consumer.terminal_transport.server_access_revoked)({"server_id": 91})

    assert sent[0]["code"] == "server_access_revoked"
    assert disconnected == [True]
    assert closed == [4403]
