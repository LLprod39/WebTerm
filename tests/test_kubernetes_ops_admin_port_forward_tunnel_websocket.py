import asyncio
import base64
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
    K8sAdminSession,
    K8sAuditEvent,
    K8sCluster,
    K8sProvider,
)
from kubernetes_ops.routing import websocket_urlpatterns as kubernetes_websocket_urlpatterns
from kubernetes_ops.services.provider_port_forward_tunnels import ProviderPortForwardTunnelEvent


def _create_port_forward_fixture(username: str) -> tuple[User, str, str]:
    provider = K8sProvider.objects.create(
        name=f"{username}-rancher",
        kind=K8sProvider.KIND_RANCHER,
        base_url="https://rancher.example.test",
        auth_mode=K8sProvider.AUTH_NONE,
        labels={
            "port_forward_tunnel_path_template": "/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/services/{name}/portforward"
        },
    )
    cluster = K8sCluster.objects.create(
        name=f"{username}-cluster", environment="test", rancher_provider=provider, rancher_cluster_id="local"
    )
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
        reason="incident port-forward inspection",
        approval_ref="INC-2026-PF",
        approved_by=user,
        approved_at=timezone.now(),
        allowed_verbs=["get", "list", "watch", "logs", "yaml", "exec", "port_forward"],
        allowed_kinds=["service", "pod"],
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


class _FakePortForwardTunnel:
    supports_client_data = True

    def __init__(self):
        self.closed = False
        self.client_chunks = []
        self.sent = False

    def read_event(self, *, max_bytes: int):
        if not self.client_chunks:
            return ProviderPortForwardTunnelEvent()
        if not self.sent:
            self.sent = True
            return ProviderPortForwardTunnelEvent(data=b"HTTP/1.1 200 OK\r\n")
        return ProviderPortForwardTunnelEvent(eof=True)

    def write_client_data(self, data: bytes) -> bool:
        self.client_chunks.append(data)
        return True

    def close(self):
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@override_settings(
    KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
)
async def test_port_forward_websocket_can_use_provider_tunnel_and_records_metadata_only():
    user, session_id, cluster_id = await database_sync_to_async(_create_port_forward_fixture)("k8s-ws-pf-tunnel")
    path = (
        f"/ws/kubernetes/admin/port-forward/{session_id}/"
        f"?provider_stream=1&cluster_id={cluster_id}&api_version=v1&kind=Service&namespace=payments&name=payments-api"
        "&remote_port=8080&local_port=18080&duration_seconds=120&reason=debug%20service%20tunnel&empty_read_sleep_seconds=0.05"
    )
    fake_tunnel = _FakePortForwardTunnel()

    with patch(
        "kubernetes_ops.continuous_port_forward_tunnels.open_provider_port_forward_tunnel", return_value=fake_tunnel
    ) as open_tunnel:
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        await communicator.send_json_to(
            {
                "type": "port_forward_data",
                "encoding": "base64",
                "data": base64.b64encode(b"GET / HTTP/1.1\r\n\r\n").decode("ascii"),
            }
        )
        data = await communicator.receive_json_from(timeout=2)
        stopped = await communicator.receive_json_from(timeout=2)
        await communicator.disconnect()
        for _ in range(20):
            if fake_tunnel.closed:
                break
            await asyncio.sleep(0.01)

    assert started["type"] == "port_forward_started"
    assert started["payload"]["policy"]["provider_tunnel_enabled"] is True
    assert started["payload"]["policy"]["recording_policy"]["enabled"] is True
    assert started["payload"]["recording"]["status"] == K8sAdminRecording.STATUS_ACTIVE
    assert open_tunnel.call_args.kwargs["target"]["remote_port"] == 8080
    assert fake_tunnel.client_chunks == [b"GET / HTTP/1.1\r\n\r\n"]
    assert fake_tunnel.closed is True
    assert data["type"] == "port_forward_data"
    assert base64.b64decode(data["data"]) == b"HTTP/1.1 200 OK\r\n"
    assert stopped["type"] == "port_forward_stopped"
    assert stopped["summary"]["bytes_from_client"] == len(b"GET / HTTP/1.1\r\n\r\n")
    assert stopped["summary"]["bytes_to_client"] == len(b"HTTP/1.1 200 OK\r\n")
    assert stopped["summary"]["payload_stored"] is False
    assert stopped["summary"]["recording_policy"]["enabled"] is True
    action = await database_sync_to_async(K8sAdminAction.objects.get)(verb=K8sAdminAction.VERB_PORT_FORWARD)
    assert action.status == K8sAdminAction.STATUS_COMPLETED
    assert action.response_summary["payload_stored"] is False
    recording = await database_sync_to_async(K8sAdminRecording.objects.get)(action=action)
    assert recording.status == K8sAdminRecording.STATUS_COMPLETED
    assert recording.transcript_required is False
    assert recording.payload_stored is False
    assert stopped["summary"]["recording"]["id"] == str(recording.recording_id)
    stopped_events = await database_sync_to_async(
        K8sAuditEvent.objects.filter(action="k8s.admin_stream.port_forward_stopped").count
    )()
    assert stopped_events == 1


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@override_settings(
    KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=False,
    KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
)
async def test_port_forward_websocket_tunnel_requires_separate_flag_before_action():
    user, session_id, cluster_id = await database_sync_to_async(_create_port_forward_fixture)(
        "k8s-ws-pf-tunnel-disabled"
    )
    path = f"/ws/kubernetes/admin/port-forward/{session_id}/?provider_stream=1&cluster_id={cluster_id}&namespace=payments&kind=Service&name=payments-api&remote_port=8080&reason=debug%20service"

    with patch("kubernetes_ops.continuous_port_forward_tunnels.open_provider_port_forward_tunnel") as open_tunnel:
        communicator = await _connect(path, user)
        rejected = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert rejected["type"] == "port_forward_rejected"
    assert rejected["code"] == "port_forward_tunnel_disabled"
    open_tunnel.assert_not_called()
    action_count = await database_sync_to_async(K8sAdminAction.objects.count)()
    assert action_count == 0


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@override_settings(
    KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=False,
    KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
)
async def test_port_forward_websocket_tunnel_requires_recording_before_action():
    user, session_id, cluster_id = await database_sync_to_async(_create_port_forward_fixture)(
        "k8s-ws-pf-recording-required"
    )
    path = f"/ws/kubernetes/admin/port-forward/{session_id}/?provider_stream=1&cluster_id={cluster_id}&namespace=payments&kind=Service&name=payments-api&remote_port=8080&reason=debug%20service"

    with patch("kubernetes_ops.continuous_port_forward_tunnels.open_provider_port_forward_tunnel") as open_tunnel:
        communicator = await _connect(path, user)
        rejected = await communicator.receive_json_from(timeout=1)
        await communicator.disconnect()

    assert rejected["type"] == "port_forward_rejected"
    assert rejected["code"] == "port_forward_recording_required"
    assert rejected["payload"]["recording_policy"]["enabled"] is False
    open_tunnel.assert_not_called()
    action_count = await database_sync_to_async(K8sAdminAction.objects.count)()
    assert action_count == 0


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
@override_settings(
    KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=True,
    KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=["payments/service/payments-api:8080"],
)
async def test_port_forward_websocket_tunnel_stops_when_session_expires():
    user, session_id, cluster_id = await database_sync_to_async(_create_port_forward_fixture)("k8s-ws-pf-expired")
    path = (
        f"/ws/kubernetes/admin/port-forward/{session_id}/"
        f"?provider_stream=1&cluster_id={cluster_id}&api_version=v1&kind=Service&namespace=payments&name=payments-api"
        "&remote_port=8080&duration_seconds=120&reason=debug%20service%20tunnel&empty_read_sleep_seconds=0.05"
    )
    fake_tunnel = _FakePortForwardTunnel()

    with patch(
        "kubernetes_ops.continuous_port_forward_tunnels.open_provider_port_forward_tunnel", return_value=fake_tunnel
    ):
        communicator = await _connect(path, user)
        started = await communicator.receive_json_from(timeout=1)
        await database_sync_to_async(K8sAdminSession.objects.filter(session_id=session_id).update)(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        stopped = await communicator.receive_json_from(timeout=2)
        await communicator.disconnect()

    assert started["type"] == "port_forward_started"
    assert stopped["type"] == "port_forward_stopped"
    assert stopped["summary"]["close_reason"] == "admin_session_expired"
    assert fake_tunnel.closed is True
    action = await database_sync_to_async(K8sAdminAction.objects.get)(verb=K8sAdminAction.VERB_PORT_FORWARD)
    assert action.status == K8sAdminAction.STATUS_COMPLETED
    assert action.response_summary["close_reason"] == "admin_session_expired"
    recording = await database_sync_to_async(K8sAdminRecording.objects.get)(action=action)
    assert recording.status == K8sAdminRecording.STATUS_COMPLETED
