from datetime import timedelta
from unittest.mock import patch

import pytest
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone

from core_ui.models import UserAppPermission
from kubernetes_ops.models import K8sAdminAction, K8sAdminRecording, K8sAdminRecordingEvent, K8sAdminSession, K8sAuditEvent, K8sCluster, K8sProvider
from kubernetes_ops.routing import websocket_urlpatterns as kubernetes_websocket_urlpatterns
from kubernetes_ops.services.provider_exec_streams import ProviderExecStreamEvent


def _create_exec_fixture(username: str) -> tuple[User, str, str]:
    provider = K8sProvider.objects.create(
        name=f"{username}-rancher",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher.example.test",
        auth_mode=K8sProvider.AUTH_NONE,
        labels={"pod_exec_stream_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/{pod_name}/exec"},
    )
    cluster = K8sCluster.objects.create(name=f"{username}-cluster", environment="test", rancher_provider=provider, rancher_cluster_id="local")
    user = User.objects.create_user(username=username, password="password-123")
    UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
    UserAppPermission.objects.create(user=user, feature="kubernetes_break_glass", allowed=True)
    session = K8sAdminSession.objects.create(
        user=user,
        username_snapshot=user.username,
        cluster=cluster,
        namespace="payments",
        mode=K8sAdminSession.MODE_BREAK_GLASS,
        status=K8sAdminSession.STATUS_ACTIVE,
        risk_tier=K8sAdminSession.RISK_CRITICAL,
        reason="incident exec inspection",
        approval_ref="INC-2026-EXEC",
        approved_by=user,
        approved_at=timezone.now(),
        allowed_verbs=["get", "list", "watch", "logs", "yaml", "exec"],
        allowed_kinds=["pod"],
        allowed_namespaces=["payments"],
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    return user, str(session.session_id), f"cluster_{cluster.id}"


async def _connect(path: str, user: User) -> WebsocketCommunicator:
    communicator = WebsocketCommunicator(URLRouter(kubernetes_websocket_urlpatterns), path)
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    assert connected
    return communicator


class _FakeExecStream:
    supports_stdin = True

    def __init__(self):
        self.closed = False
        self.stdin = []
        self.events = [
            ProviderExecStreamEvent(stream="stdout", data="TOKEN=raw-secret"),
            ProviderExecStreamEvent(stream="stderr", data="warning"),
            ProviderExecStreamEvent(stream="status", exit_code=0, eof=True),
        ]

    def read_event(self, *, max_bytes: int):
        return self.events.pop(0) if self.events else ProviderExecStreamEvent(stream="status", eof=True)

    def write_stdin(self, data: str) -> bool:
        self.stdin.append(data)
        return True

    def close(self):
        self.closed = True


class _FakeHeartbeatExecStream:
    def __init__(self):
        self.closed = False

    def read_event(self, *, max_bytes: int):
        return ProviderExecStreamEvent(stream="heartbeat")

    def write_stdin(self, data: str) -> bool:
        return True

    def close(self):
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@override_settings(KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True, KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=True, KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=True)
async def test_exec_websocket_can_use_provider_stream_and_records_redacted_transcript_events():
    user, session_id, cluster_id = await database_sync_to_async(_create_exec_fixture)("k8s-ws-exec-stream")
    path = (
        f"/ws/kubernetes/admin/exec/{session_id}/"
        f"?provider_stream=1&cluster_id={cluster_id}&namespace=payments&pod=payments-api-abc123"
        "&container=api&command=env&reason=inspect%20pod%20env&stream_timeout_seconds=4&stdin=1"
    )
    fake_stream = _FakeExecStream()

    with patch("kubernetes_ops.continuous_exec_streams.open_provider_exec_stream", return_value=fake_stream) as open_stream:
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        await communicator.send_json_to({"type": "stdin", "data": "PASSWORD=stdin-secret"})
        stdout = await communicator.receive_json_from(timeout=1)
        stderr = await communicator.receive_json_from(timeout=1)
        stopped = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert started["type"] == "exec_started"
    assert started["payload"]["policy"]["provider_streaming_enabled"] is True
    assert started["payload"]["policy"]["recording_policy"]["enabled"] is True
    assert started["payload"]["recording"]["status"] == K8sAdminRecording.STATUS_ACTIVE
    assert stdout["type"] == "exec_output"
    assert stdout["stream"] == "stdout"
    assert stdout["data"] == "TOKEN=[redacted]"
    assert stderr["stream"] == "stderr"
    assert stopped["type"] == "exec_stopped"
    assert stopped["summary"]["stdout_count"] == 1
    assert stopped["summary"]["stderr_count"] == 1
    assert stopped["summary"]["exit_code"] == 0
    assert stopped["summary"]["transcript_stored"] is True
    assert stopped["summary"]["recording"]["event_count"] == 3
    assert stopped["summary"]["recording_policy"]["enabled"] is True
    assert fake_stream.closed is True
    assert fake_stream.stdin == ["PASSWORD=stdin-secret"]
    assert open_stream.call_args.kwargs["timeout"] == 4
    action = await database_sync_to_async(K8sAdminAction.objects.get)(verb=K8sAdminAction.VERB_EXEC)
    assert action.status == K8sAdminAction.STATUS_COMPLETED
    assert action.exit_code == 0
    assert "raw-secret" not in str(action.request_payload_sanitized)
    assert "raw-secret" not in str(action.response_summary)
    recording = await database_sync_to_async(K8sAdminRecording.objects.get)(action=action)
    assert recording.status == K8sAdminRecording.STATUS_COMPLETED
    assert recording.transcript_required is True
    assert recording.transcript_stored is True
    assert recording.payload_stored is False
    assert "raw-secret" not in str(recording.summary)
    assert stopped["summary"]["recording"]["id"] == str(recording.recording_id)
    events = await database_sync_to_async(
        lambda: list(
            K8sAdminRecordingEvent.objects.filter(recording=recording)
            .order_by("sequence", "id")
            .values("stream", "data", "redacted", "metadata")
        )
    )()
    events_by_stream = {event["stream"]: event for event in events}
    assert set(events_by_stream) == {"stdin", "stdout", "stderr"}
    assert events_by_stream["stdin"]["data"] == "PASSWORD=[redacted]"
    assert events_by_stream["stdin"]["redacted"] is True
    assert events_by_stream["stdout"]["data"] == "TOKEN=[redacted]"
    assert events_by_stream["stdout"]["redacted"] is True
    assert events_by_stream["stdout"]["metadata"] == {"source": "provider_exec_stream"}
    assert "stdin-secret" not in str(events)
    assert "raw-secret" not in str(events)
    audit_count = await database_sync_to_async(K8sAuditEvent.objects.filter(action="k8s.admin_stream.exec_stopped").count)()
    assert audit_count == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@override_settings(KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True, KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=False)
async def test_exec_websocket_streaming_requires_separate_flag_before_action():
    user, session_id, cluster_id = await database_sync_to_async(_create_exec_fixture)("k8s-ws-exec-stream-disabled")
    path = f"/ws/kubernetes/admin/exec/{session_id}/?provider_stream=1&cluster_id={cluster_id}&namespace=payments&pod=payments-api-abc123&command=env&reason=inspect%20pod%20env"

    with patch("kubernetes_ops.continuous_exec_streams.open_provider_exec_stream") as open_stream:
        communicator = await _connect(path, user)
        rejected = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert rejected["type"] == "exec_rejected"
    assert rejected["code"] == "exec_streaming_disabled"
    open_stream.assert_not_called()
    action_count = await database_sync_to_async(K8sAdminAction.objects.count)()
    assert action_count == 0


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@override_settings(KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True, KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=True, KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=False)
async def test_exec_websocket_streaming_requires_recording_before_action():
    user, session_id, cluster_id = await database_sync_to_async(_create_exec_fixture)("k8s-ws-exec-recording-required")
    path = f"/ws/kubernetes/admin/exec/{session_id}/?provider_stream=1&cluster_id={cluster_id}&namespace=payments&pod=payments-api-abc123&command=env&reason=inspect%20pod%20env"

    with patch("kubernetes_ops.continuous_exec_streams.open_provider_exec_stream") as open_stream:
        communicator = await _connect(path, user)
        rejected = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert rejected["type"] == "exec_rejected"
    assert rejected["code"] == "exec_recording_required"
    assert rejected["payload"]["recording_policy"]["enabled"] is False
    open_stream.assert_not_called()
    action_count = await database_sync_to_async(K8sAdminAction.objects.count)()
    assert action_count == 0


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@override_settings(KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=True, KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=True, KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=True)
async def test_exec_websocket_disconnect_closes_provider_stream():
    user, session_id, cluster_id = await database_sync_to_async(_create_exec_fixture)("k8s-ws-exec-disconnect")
    path = (
        f"/ws/kubernetes/admin/exec/{session_id}/"
        f"?provider_stream=1&cluster_id={cluster_id}&namespace=payments&pod=payments-api-abc123"
        "&command=env&reason=inspect%20pod%20env&empty_read_sleep_seconds=0.05"
    )
    fake_stream = _FakeHeartbeatExecStream()

    with patch("kubernetes_ops.continuous_exec_streams.open_provider_exec_stream", return_value=fake_stream):
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert started["type"] == "exec_started"
    assert fake_stream.closed is True
    action = await database_sync_to_async(K8sAdminAction.objects.get)(verb=K8sAdminAction.VERB_EXEC)
    assert action.status == K8sAdminAction.STATUS_COMPLETED
    assert action.response_summary["close_reason"] == "client_disconnect"
    recording = await database_sync_to_async(K8sAdminRecording.objects.get)(action=action)
    assert recording.status == K8sAdminRecording.STATUS_COMPLETED
