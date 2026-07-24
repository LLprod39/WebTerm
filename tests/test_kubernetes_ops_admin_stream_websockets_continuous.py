from datetime import timedelta
from unittest.mock import patch

import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminSession, K8sCluster, K8sProvider
from kubernetes_ops.routing import websocket_urlpatterns as kubernetes_websocket_urlpatterns
from kubernetes_ops.services.admin_streams import start_admin_log_stream as real_start_admin_log_stream
from kubernetes_ops.services.admin_streams import start_admin_watch_stream as real_start_admin_watch_stream
from kubernetes_ops.services.provider_log_streams import ProviderLogStreamBatch
from kubernetes_ops.services.provider_watch_streams import ProviderWatchStreamBatch


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


class _FakeContinuousLogStream:
    def __init__(self):
        self.closed = False
        self.batches = [
            ProviderLogStreamBatch(lines=["boot ok"], eof=False),
            ProviderLogStreamBatch(lines=["api_key=raw-secret"], eof=True),
        ]

    def read_batch(self, *, max_lines: int, max_bytes: int):
        assert max_lines == 1
        return self.batches.pop(0) if self.batches else ProviderLogStreamBatch(lines=[], eof=True)

    def close(self):
        self.closed = True


class _FakeIdleContinuousLogStream:
    def __init__(self):
        self.closed = False

    def read_batch(self, *, max_lines: int, max_bytes: int):
        return ProviderLogStreamBatch(lines=[], eof=False)

    def close(self):
        self.closed = True


class _FakeContinuousWatchStream:
    def __init__(self):
        self.closed = False
        self.batches = [
            ProviderWatchStreamBatch(
                events=[
                    {
                        "type": "ADDED",
                        "object": {
                            "apiVersion": "apps/v1",
                            "kind": "Deployment",
                            "metadata": {
                                "name": "payments-api",
                                "resourceVersion": "42",
                                "annotations": {"password": "raw-secret"},
                            },
                        },
                    }
                ],
                eof=False,
            ),
            ProviderWatchStreamBatch(
                events=[{"type": "BOOKMARK", "object": {"metadata": {"resourceVersion": "43"}}}], eof=True
            ),
        ]

    def read_batch(self, *, max_events: int, max_bytes: int):
        assert max_events == 1
        return self.batches.pop(0) if self.batches else ProviderWatchStreamBatch(events=[], eof=True)

    def close(self):
        self.closed = True


class _FakeIdleContinuousWatchStream:
    def __init__(self):
        self.closed = False

    def read_batch(self, *, max_events: int, max_bytes: int):
        return ProviderWatchStreamBatch(events=[], eof=False)

    def close(self):
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_log_follow_websocket_can_use_provider_continuous_stream():
    user, session_id, cluster_id = await database_sync_to_async(_create_read_fixture)("k8s-ws-log-continuous")
    path = (
        f"/ws/kubernetes/admin/logs/{session_id}/"
        f"?follow=1&provider_stream=continuous&cluster_id={cluster_id}&namespace=payments&pod=payments-api-abc123"
        "&max_batches=5&batch_lines=1&stream_timeout_seconds=3"
    )
    fake_stream = _FakeContinuousLogStream()

    with (
        patch(
            "kubernetes_ops.continuous_log_streams.open_provider_log_line_stream",
            return_value=fake_stream,
        ) as open_stream,
        patch("kubernetes_ops.consumers.get_admin_pod_log_stream_batch") as stream_batch,
    ):
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        first_batch = await communicator.receive_json_from(timeout=1)
        second_batch = await communicator.receive_json_from(timeout=1)
        stopped = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert started["type"] == "stream_started"
    assert first_batch["payload"]["source"] == "provider_stream_continuous"
    assert first_batch["payload"]["policy"]["stream_transport"] == "provider_native_continuous"
    assert first_batch["payload"]["lines"] == ["boot ok"]
    assert second_batch["payload"]["lines"] == ["api_key=[redacted]"]
    assert second_batch["payload"]["stream_eof"] is True
    assert stopped["summary"]["close_reason"] == "provider_eof"
    assert stopped["summary"]["batch_count"] == 2
    assert fake_stream.closed is True
    stream_batch.assert_not_called()
    assert open_stream.call_args.kwargs["timeout"] == 3


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_watch_follow_websocket_can_use_provider_continuous_stream():
    user, session_id, cluster_id = await database_sync_to_async(_create_read_fixture)("k8s-ws-watch-continuous")
    path = (
        f"/ws/kubernetes/admin/watch/{session_id}/"
        f"?follow=1&provider_stream=continuous&cluster_id={cluster_id}&api_version=apps/v1&kind=Deployment&namespace=payments"
        "&max_batches=5&batch_events=1&timeout_seconds=4"
    )
    fake_stream = _FakeContinuousWatchStream()

    with (
        patch(
            "kubernetes_ops.continuous_watch_streams.open_provider_watch_event_stream",
            return_value=fake_stream,
        ) as open_stream,
        patch("kubernetes_ops.consumers.get_admin_resource_watch_stream_batch") as stream_batch,
    ):
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        first_batch = await communicator.receive_json_from(timeout=1)
        second_batch = await communicator.receive_json_from(timeout=1)
        stopped = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert started["type"] == "stream_started"
    assert first_batch["type"] == "watch_batch"
    assert first_batch["payload"]["source"] == "provider_watch_stream_continuous"
    assert first_batch["payload"]["policy"]["stream_transport"] == "provider_native_continuous"
    assert first_batch["payload"]["events"][0]["resource_version"] == "42"
    assert first_batch["payload"]["events"][0]["object"]["metadata"]["annotations"]["password"] == "[redacted]"
    assert second_batch["payload"]["event_count"] == 0
    assert second_batch["payload"]["latest_resource_version"] == "43"
    assert second_batch["payload"]["stream_eof"] is True
    assert stopped["summary"]["close_reason"] == "provider_eof"
    assert stopped["summary"]["batch_count"] == 2
    assert stopped["summary"]["latest_resource_version"] == "43"
    assert fake_stream.closed is True
    stream_batch.assert_not_called()
    assert open_stream.call_args.kwargs["timeout"] == 4


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_log_follow_continuous_stream_closes_on_idle_timeout():
    user, session_id, cluster_id = await database_sync_to_async(_create_read_fixture)("k8s-ws-log-continuous-idle")
    path = (
        f"/ws/kubernetes/admin/logs/{session_id}/"
        f"?follow=1&provider_stream=continuous&cluster_id={cluster_id}&namespace=payments&pod=payments-api-abc123"
        "&max_batches=5&batch_lines=1&idle_timeout_seconds=1&empty_read_sleep_seconds=0.05"
    )
    fake_stream = _FakeIdleContinuousLogStream()

    with patch("kubernetes_ops.continuous_log_streams.open_provider_log_line_stream", return_value=fake_stream):
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        stopped = await communicator.receive_json_from(timeout=3)
        await communicator.disconnect()

    assert started["type"] == "stream_started"
    assert stopped["type"] == "stream_stopped"
    assert stopped["summary"]["close_reason"] == "idle_timeout"
    assert stopped["summary"]["batch_count"] == 0
    assert fake_stream.closed is True


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_watch_follow_continuous_stream_closes_on_idle_timeout():
    user, session_id, cluster_id = await database_sync_to_async(_create_read_fixture)("k8s-ws-watch-continuous-idle")
    path = (
        f"/ws/kubernetes/admin/watch/{session_id}/"
        f"?follow=1&provider_stream=continuous&cluster_id={cluster_id}&api_version=apps/v1&kind=Deployment&namespace=payments"
        "&max_batches=5&batch_events=1&idle_timeout_seconds=1&empty_read_sleep_seconds=0.05"
    )
    fake_stream = _FakeIdleContinuousWatchStream()

    with patch("kubernetes_ops.continuous_watch_streams.open_provider_watch_event_stream", return_value=fake_stream):
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        stopped = await communicator.receive_json_from(timeout=3)
        await communicator.disconnect()

    assert started["type"] == "stream_started"
    assert stopped["type"] == "stream_stopped"
    assert stopped["summary"]["close_reason"] == "idle_timeout"
    assert stopped["summary"]["batch_count"] == 0
    assert fake_stream.closed is True


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_watch_follow_websocket_can_use_provider_stream_batch_reader():
    user, session_id, cluster_id = await database_sync_to_async(_create_read_fixture)("k8s-ws-watch-provider-stream")
    path = (
        f"/ws/kubernetes/admin/watch/{session_id}/"
        f"?follow=1&provider_stream=1&cluster_id={cluster_id}&api_version=apps/v1&kind=Deployment&namespace=payments"
        "&max_batches=1&timeout_seconds=4"
    )
    payload = {
        "target": {"api_version": "apps/v1", "kind": "Deployment", "namespace": "payments", "name": ""},
        "source": "provider_watch_stream_batch",
        "available": True,
        "events": [{"type": "ADDED", "resource_version": "42", "object": {"metadata": {"resourceVersion": "42"}}}],
        "event_count": 1,
        "truncated": False,
        "latest_resource_version": "42",
        "policy": {"streaming": True},
    }

    with (
        patch("kubernetes_ops.consumers.get_admin_resource_watch_stream_batch", return_value=payload) as stream_batch,
        patch("kubernetes_ops.consumers.get_admin_resource_watch_preview") as preview,
    ):
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        batch = await communicator.receive_json_from(timeout=1)
        stopped = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert started["type"] == "stream_started"
    assert batch["type"] == "watch_batch"
    assert batch["payload"]["source"] == "provider_watch_stream_batch"
    assert batch["payload"]["policy"]["streaming"] is True
    assert stopped["summary"]["close_reason"] == "max_batches"
    preview.assert_not_called()
    assert stream_batch.call_args.kwargs["timeout_seconds"] == "4"
