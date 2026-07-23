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
from kubernetes_ops.models import (
    K8sAdminAction,
    K8sAdminRecording,
    K8sAdminRecordingEvent,
    K8sAdminSession,
    K8sAuditEvent,
    K8sCluster,
    K8sProvider,
)
from kubernetes_ops.routing import websocket_urlpatterns as kubernetes_websocket_urlpatterns
from kubernetes_ops.services.provider_exec_streams import ProviderExecStreamEvent


def _create_shell_fixture(username: str, *, include_contracts: bool = True) -> tuple[User, str, str, str]:
    labels = {}
    if include_contracts:
        labels = {
            "cluster_terminal_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/webterm-terminal/exec",
            "node_debug_path_template": "/k8s/clusters/{cluster_id}/api/v1/nodes/{node_name}/proxy/debug",
        }
    provider = K8sProvider.objects.create(
        name=f"{username}-rancher",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher.example.test",
        auth_mode=K8sProvider.AUTH_NONE,
        labels=labels,
    )
    cluster = K8sCluster.objects.create(
        name=f"{username}-cluster", environment="test", rancher_provider=provider, rancher_cluster_id="local"
    )
    user = User.objects.create_user(username=username, password="password-123")
    UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)
    UserAppPermission.objects.create(user=user, feature="kubernetes_break_glass", allowed=True)
    terminal_session = K8sAdminSession.objects.create(
        user=user,
        username_snapshot=user.username,
        cluster=cluster,
        namespace="payments",
        mode=K8sAdminSession.MODE_BREAK_GLASS,
        status=K8sAdminSession.STATUS_ACTIVE,
        risk_tier=K8sAdminSession.RISK_CRITICAL,
        reason="incident terminal inspection",
        approval_ref="INC-2026-TERM-WS",
        approved_by=user,
        approved_at=timezone.now(),
        allowed_verbs=["get", "list", "watch", "logs", "yaml", "exec", "port_forward"],
        allowed_kinds=["pod"],
        allowed_namespaces=["payments"],
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    node_session = K8sAdminSession.objects.create(
        user=user,
        username_snapshot=user.username,
        cluster=cluster,
        namespace="",
        mode=K8sAdminSession.MODE_BREAK_GLASS,
        status=K8sAdminSession.STATUS_ACTIVE,
        risk_tier=K8sAdminSession.RISK_CRITICAL,
        reason="incident node debug",
        approval_ref="INC-2026-NODE-WS",
        approved_by=user,
        approved_at=timezone.now(),
        allowed_verbs=["get", "list", "watch", "logs", "yaml", "exec", "port_forward"],
        allowed_kinds=["node"],
        allowed_namespaces=["*"],
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    return user, str(terminal_session.session_id), str(node_session.session_id), f"cluster_{cluster.id}"


async def _connect(path: str, user: User) -> WebsocketCommunicator:
    communicator = WebsocketCommunicator(URLRouter(kubernetes_websocket_urlpatterns), path)
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    assert connected
    return communicator


class _FakeShellStream:
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


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@override_settings(
    KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=True, KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=True
)
async def test_cluster_terminal_websocket_can_use_provider_stream_and_records_transcript():
    user, terminal_session_id, _, _ = await database_sync_to_async(_create_shell_fixture)("k8s-ws-terminal")
    path = f"/ws/kubernetes/admin/terminal/{terminal_session_id}/?provider_stream=1&reason=inspect%20namespace&stdin=1&stream_timeout_seconds=4"
    fake_stream = _FakeShellStream()

    with patch(
        "kubernetes_ops.continuous_interactive_shell_streams.open_provider_interactive_shell_stream",
        return_value=fake_stream,
    ) as open_stream:
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        await communicator.send_json_to({"type": "stdin", "data": "PASSWORD=stdin-secret"})
        stdout = await communicator.receive_json_from(timeout=1)
        stderr = await communicator.receive_json_from(timeout=1)
        stopped = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert started["type"] == "terminal_started"
    assert started["payload"]["policy"]["provider_transport_enabled"] is True
    assert started["payload"]["recording"]["status"] == K8sAdminRecording.STATUS_ACTIVE
    assert open_stream.call_args.kwargs["operation"] == "cluster_terminal"
    assert open_stream.call_args.kwargs["target"] == {"namespace": "payments"}
    assert fake_stream.stdin == ["PASSWORD=stdin-secret"]
    assert fake_stream.closed is True
    assert stdout["type"] == "cluster_terminal_output"
    assert stdout["data"] == "TOKEN=[redacted]"
    assert stderr["stream"] == "stderr"
    assert stopped["type"] == "terminal_stopped"
    assert stopped["summary"]["transcript_stored"] is True
    action = await database_sync_to_async(K8sAdminAction.objects.get)(verb=K8sAdminAction.VERB_CLUSTER_TERMINAL)
    assert action.status == K8sAdminAction.STATUS_COMPLETED
    recording = await database_sync_to_async(K8sAdminRecording.objects.get)(action=action)
    assert recording.status == K8sAdminRecording.STATUS_COMPLETED
    events = await database_sync_to_async(
        lambda: list(K8sAdminRecordingEvent.objects.filter(recording=recording).values("stream", "data", "redacted"))
    )()
    assert {event["stream"] for event in events} == {"stdin", "stdout", "stderr"}
    assert "raw-secret" not in str(events)
    assert "stdin-secret" not in str(events)
    audit_count = await database_sync_to_async(
        K8sAuditEvent.objects.filter(action="k8s.admin_terminal.stream_stopped").count
    )()
    assert audit_count == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@override_settings(KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=True, KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED=True)
async def test_node_debug_websocket_can_use_provider_stream_and_records_transcript():
    user, _, node_session_id, _ = await database_sync_to_async(_create_shell_fixture)("k8s-ws-node-debug")
    path = f"/ws/kubernetes/admin/node-debug/{node_session_id}/?provider_stream=1&node=worker-1&reason=debug%20node&stream_timeout_seconds=4"
    fake_stream = _FakeShellStream()

    with patch(
        "kubernetes_ops.continuous_interactive_shell_streams.open_provider_interactive_shell_stream",
        return_value=fake_stream,
    ) as open_stream:
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        stdout = await communicator.receive_json_from(timeout=1)
        stderr = await communicator.receive_json_from(timeout=1)
        stopped = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert started["type"] == "node_debug_started"
    assert started["payload"]["policy"]["provider_transport_enabled"] is True
    assert open_stream.call_args.kwargs["operation"] == "node_debug"
    assert open_stream.call_args.kwargs["target"] == {"kind": "Node", "name": "worker-1"}
    assert fake_stream.closed is True
    assert stdout["type"] == "node_debug_output"
    assert stdout["data"] == "TOKEN=[redacted]"
    assert stderr["stream"] == "stderr"
    assert stopped["type"] == "node_debug_stopped"
    action = await database_sync_to_async(K8sAdminAction.objects.get)(verb=K8sAdminAction.VERB_NODE_DEBUG)
    assert action.status == K8sAdminAction.STATUS_COMPLETED
    recording = await database_sync_to_async(K8sAdminRecording.objects.get)(action=action)
    assert recording.status == K8sAdminRecording.STATUS_COMPLETED
    assert recording.transcript_stored is True


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@override_settings(
    KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=True, KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=True
)
async def test_cluster_terminal_websocket_blocks_before_action_without_provider_contract():
    user, terminal_session_id, _, _ = await database_sync_to_async(_create_shell_fixture)(
        "k8s-ws-terminal-no-contract", include_contracts=False
    )
    path = f"/ws/kubernetes/admin/terminal/{terminal_session_id}/?provider_stream=1&reason=inspect%20namespace"

    with patch(
        "kubernetes_ops.continuous_interactive_shell_streams.open_provider_interactive_shell_stream"
    ) as open_stream:
        communicator = await _connect(path, user)
        rejected = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert rejected["type"] == "terminal_rejected"
    assert rejected["code"] == "interactive_transport_prerequisites_required"
    assert "provider_contract_required" in rejected["payload"]["blockers"]
    open_stream.assert_not_called()
    action_count = await database_sync_to_async(K8sAdminAction.objects.count)()
    assert action_count == 0
