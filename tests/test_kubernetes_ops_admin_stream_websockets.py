from datetime import timedelta
from unittest.mock import patch

import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.routing import websocket_urlpatterns as kubernetes_websocket_urlpatterns
from kubernetes_ops.services.admin_streams import start_admin_log_stream as real_start_admin_log_stream
from kubernetes_ops.services.admin_streams import start_admin_watch_stream as real_start_admin_watch_stream


def _create_read_fixture(username: str) -> tuple[User, str, str]:
    provider = K8sProvider.objects.create(
        name=f"{username}-rancher",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher.example.test",
        auth_mode=K8sProvider.AUTH_NONE,
        labels={
            "pod_logs_path_template": "/v3/pods/{namespace}:{pod_name}/logs?tail={tail}",
            "pod_logs_stream_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/{pod_name}/log?follow=1&tailLines={tail}",
        },
    )
    cluster = K8sCluster.objects.create(
        name=f"{username}-cluster",
        environment="test",
        rancher_provider=provider,
        rancher_cluster_id="local",
    )
    user = User.objects.create_user(username=username, password="password-123")
    UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
    UserAppPermission.objects.create(user=user, feature="kubernetes_admin_read", allowed=True)
    session = K8sAdminSession.objects.create(
        user=user,
        username_snapshot=user.username,
        cluster=cluster,
        mode=K8sAdminSession.MODE_READ,
        status=K8sAdminSession.STATUS_ACTIVE,
        risk_tier=K8sAdminSession.RISK_LOW,
        allowed_verbs=["get", "list", "watch", "logs", "yaml"],
        allowed_kinds=["*"],
        allowed_namespaces=["*"],
        expires_at=timezone.now() + timedelta(hours=1),
    )
    return user, str(session.session_id), f"cluster_{cluster.id}"


def _expire_stream_session_after_log_start(*args, **kwargs) -> dict:
    stream = real_start_admin_log_stream(*args, **kwargs)
    K8sAdminSession.objects.filter(pk=stream["session_pk"]).update(expires_at=timezone.now() - timedelta(minutes=1))
    return stream


def _close_stream_session_after_watch_start(*args, **kwargs) -> dict:
    stream = real_start_admin_watch_stream(*args, **kwargs)
    K8sAdminSession.objects.filter(pk=stream["session_pk"]).update(
        status=K8sAdminSession.STATUS_CLOSED, closed_at=timezone.now()
    )
    return stream


async def _connect(path: str, user: User) -> WebsocketCommunicator:
    communicator = WebsocketCommunicator(URLRouter(kubernetes_websocket_urlpatterns), path)
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    assert connected
    return communicator


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_log_follow_websocket_stops_when_session_expires_before_next_batch():
    user, session_id, cluster_id = await database_sync_to_async(_create_read_fixture)("k8s-ws-log-expired")
    path = (
        f"/ws/kubernetes/admin/logs/{session_id}/"
        f"?follow=1&cluster_id={cluster_id}&namespace=payments&pod=payments-api-abc123&max_batches=2"
    )

    with (
        patch("kubernetes_ops.consumers.start_admin_log_stream", side_effect=_expire_stream_session_after_log_start),
        patch("kubernetes_ops.consumers.get_admin_pod_log_snapshot") as snapshot,
    ):
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        stopped = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert started["type"] == "stream_started"
    assert stopped["type"] == "stream_stopped"
    assert stopped["summary"]["close_reason"] == "admin_session_expired"
    assert stopped["summary"]["session_status"] == K8sAdminSession.STATUS_EXPIRED
    snapshot.assert_not_called()
    stopped_events = await database_sync_to_async(
        K8sAuditEvent.objects.filter(action="k8s.admin_stream.logs_stopped").count
    )()
    assert stopped_events == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_watch_follow_websocket_stops_when_session_is_closed_before_next_batch():
    user, session_id, cluster_id = await database_sync_to_async(_create_read_fixture)("k8s-ws-watch-closed")
    path = (
        f"/ws/kubernetes/admin/watch/{session_id}/"
        f"?follow=1&cluster_id={cluster_id}&api_version=apps/v1&kind=Deployment&namespace=payments&max_batches=2"
    )

    with (
        patch("kubernetes_ops.consumers.start_admin_watch_stream", side_effect=_close_stream_session_after_watch_start),
        patch("kubernetes_ops.consumers.get_admin_resource_watch_preview") as snapshot,
    ):
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        stopped = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert started["type"] == "stream_started"
    assert stopped["type"] == "stream_stopped"
    assert stopped["summary"]["close_reason"] == "admin_session_not_active"
    assert stopped["summary"]["session_status"] == K8sAdminSession.STATUS_CLOSED
    snapshot.assert_not_called()
    stopped_events = await database_sync_to_async(
        K8sAuditEvent.objects.filter(action="k8s.admin_stream.watch_stopped").count
    )()
    assert stopped_events == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_watch_follow_websocket_advances_resource_version_between_batches():
    user, session_id, cluster_id = await database_sync_to_async(_create_read_fixture)("k8s-ws-watch-rv")
    path = (
        f"/ws/kubernetes/admin/watch/{session_id}/"
        f"?follow=1&cluster_id={cluster_id}&api_version=apps/v1&kind=Deployment&namespace=payments"
        "&max_batches=2&poll_interval_seconds=0.25"
    )
    payloads = [
        {
            "target": {"api_version": "apps/v1", "kind": "Deployment", "namespace": "payments", "name": ""},
            "source": "provider_watch_preview",
            "available": True,
            "events": [{"type": "ADDED", "resource_version": "42", "object": {"metadata": {"resourceVersion": "42"}}}],
            "event_count": 1,
            "truncated": False,
            "latest_resource_version": "42",
        },
        {
            "target": {"api_version": "apps/v1", "kind": "Deployment", "namespace": "payments", "name": ""},
            "source": "provider_watch_preview",
            "available": True,
            "events": [
                {"type": "MODIFIED", "resource_version": "43", "object": {"metadata": {"resourceVersion": "43"}}}
            ],
            "event_count": 1,
            "truncated": False,
            "latest_resource_version": "43",
        },
    ]

    with patch("kubernetes_ops.consumers.get_admin_resource_watch_preview", side_effect=payloads) as preview:
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        first_batch = await communicator.receive_json_from(timeout=1)
        heartbeat = await communicator.receive_json_from(timeout=1)
        second_batch = await communicator.receive_json_from(timeout=1)
        stopped = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert started["type"] == "stream_started"
    assert first_batch["type"] == "watch_batch"
    assert first_batch["payload"]["latest_resource_version"] == "42"
    assert heartbeat["type"] == "stream_heartbeat"
    assert second_batch["type"] == "watch_batch"
    assert second_batch["payload"]["latest_resource_version"] == "43"
    assert stopped["type"] == "stream_stopped"
    assert stopped["summary"]["close_reason"] == "max_batches"
    assert preview.call_args_list[0].kwargs["resource_version"] == ""
    assert preview.call_args_list[1].kwargs["resource_version"] == "42"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_log_follow_websocket_sends_only_new_suffix_for_overlapping_snapshots():
    user, session_id, cluster_id = await database_sync_to_async(_create_read_fixture)("k8s-ws-log-delta")
    path = (
        f"/ws/kubernetes/admin/logs/{session_id}/"
        f"?follow=1&cluster_id={cluster_id}&namespace=payments&pod=payments-api-abc123"
        "&max_batches=3&poll_interval_seconds=0.25"
    )
    payloads = [
        {
            "target": {"namespace": "payments", "name": "payments-api-abc123"},
            "source": "provider_snapshot",
            "available": True,
            "lines": ["boot", "ready"],
            "line_count": 2,
            "truncated": False,
        },
        {
            "target": {"namespace": "payments", "name": "payments-api-abc123"},
            "source": "provider_snapshot",
            "available": True,
            "lines": ["boot", "ready", "serving"],
            "line_count": 3,
            "truncated": False,
        },
        {
            "target": {"namespace": "payments", "name": "payments-api-abc123"},
            "source": "provider_snapshot",
            "available": True,
            "lines": ["ready", "serving", "done"],
            "line_count": 3,
            "truncated": True,
        },
    ]

    with patch("kubernetes_ops.consumers.get_admin_pod_log_snapshot", side_effect=payloads):
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        first_batch = await communicator.receive_json_from(timeout=1)
        first_heartbeat = await communicator.receive_json_from(timeout=1)
        second_batch = await communicator.receive_json_from(timeout=1)
        second_heartbeat = await communicator.receive_json_from(timeout=1)
        third_batch = await communicator.receive_json_from(timeout=1)
        stopped = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert started["type"] == "stream_started"
    assert first_batch["payload"]["lines"] == ["boot", "ready"]
    assert "follow_delta" not in first_batch["payload"]
    assert first_heartbeat["type"] == "stream_heartbeat"
    assert second_batch["payload"]["lines"] == ["serving"]
    assert second_batch["payload"]["line_count"] == 1
    assert second_batch["payload"]["deduped_line_count"] == 2
    assert second_heartbeat["type"] == "stream_heartbeat"
    assert third_batch["payload"]["lines"] == ["done"]
    assert third_batch["payload"]["line_count"] == 1
    assert third_batch["payload"]["deduped_line_count"] == 2
    assert stopped["type"] == "stream_stopped"
    assert stopped["summary"]["close_reason"] == "max_batches"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_log_follow_websocket_can_use_provider_stream_batch_reader():
    user, session_id, cluster_id = await database_sync_to_async(_create_read_fixture)("k8s-ws-log-provider-stream")
    path = (
        f"/ws/kubernetes/admin/logs/{session_id}/"
        f"?follow=1&provider_stream=1&cluster_id={cluster_id}&namespace=payments&pod=payments-api-abc123"
        "&max_batches=1&stream_timeout_seconds=3"
    )
    payload = {
        "target": {"namespace": "payments", "name": "payments-api-abc123"},
        "source": "provider_stream_batch",
        "available": True,
        "lines": ["streamed"],
        "line_count": 1,
        "truncated": False,
    }

    with (
        patch("kubernetes_ops.consumers.get_admin_pod_log_stream_batch", return_value=payload) as stream_batch,
        patch("kubernetes_ops.consumers.get_admin_pod_log_snapshot") as snapshot,
    ):
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        batch = await communicator.receive_json_from(timeout=1)
        stopped = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert started["type"] == "stream_started"
    assert batch["type"] == "log_batch"
    assert batch["payload"]["source"] == "provider_stream_batch"
    assert batch["payload"]["lines"] == ["streamed"]
    assert stopped["summary"]["close_reason"] == "max_batches"
    snapshot.assert_not_called()
    assert stream_batch.call_args.kwargs["timeout_seconds"] == "3"
