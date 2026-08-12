from __future__ import annotations

import json
import socket
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User

from app.tools.ssh_tools import SSHConnectionManager
from core_ui.views.access_views import _apply_access_profile
from servers.models import Server
from servers.services.pilot_destination_policy import (
    PilotDestinationDenied,
    PilotDestinationInvalid,
    validate_pilot_network_config,
    validate_pilot_ssh_destination,
)
from servers.services.server_mutation_policy import decide_server_command, decide_server_mutation
from servers.ssh_host_keys import build_server_connect_kwargs

pytestmark = pytest.mark.django_db


def _enable_policy(monkeypatch) -> None:
    monkeypatch.setenv("PILOT_RESTRICTED_MODE", "true")
    monkeypatch.setenv("PILOT_SSH_ALLOWED_HOSTS", "pilot-ssh,10.20.0.10")
    monkeypatch.setenv("PILOT_SSH_ALLOWED_CIDRS", "10.20.0.0/24")
    monkeypatch.setenv("PILOT_SSH_ALLOWED_PORTS", "22")


def _resolver(addresses: list[str]):
    def resolve(_host, port, *, type):
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port)) for address in addresses]

    return resolve


def test_pilot_destination_policy_allows_only_configured_name_and_all_resolved_addresses(monkeypatch) -> None:
    _enable_policy(monkeypatch)

    validate_pilot_ssh_destination("pilot-ssh", 22, resolver=_resolver(["10.20.0.10"]))

    with pytest.raises(PilotDestinationDenied):
        validate_pilot_ssh_destination("pilot-ssh", 22, resolver=_resolver(["10.20.0.10", "10.30.0.4"]))
    with pytest.raises(PilotDestinationDenied):
        validate_pilot_ssh_destination("unlisted-host", 22, resolver=_resolver(["10.20.0.10"]))


@pytest.mark.parametrize("host", ["169.254.169.254", "127.0.0.1", "redis", "postgres", "backend"])
def test_pilot_destination_policy_blocks_metadata_loopback_and_internal_services(monkeypatch, host) -> None:
    _enable_policy(monkeypatch)

    with pytest.raises(PilotDestinationDenied):
        validate_pilot_ssh_destination(host, 22, resolver=_resolver(["10.20.0.10"]))


def test_bastion_uses_same_host_and_port_allowlist(monkeypatch) -> None:
    _enable_policy(monkeypatch)

    assert validate_pilot_network_config(
        {"network": {"bastion_host": "pilot-ssh:22"}},
        resolver=_resolver(["10.20.0.10"]),
    ) == ("pilot-ssh", 22)

    with pytest.raises(PilotDestinationDenied):
        validate_pilot_network_config({"network": {"bastion_host": "169.254.169.254:22"}})
    with pytest.raises(PilotDestinationDenied):
        validate_pilot_network_config({"network": {"bastion_host": "10.30.0.4:22"}})


@pytest.mark.parametrize(
    "bastion",
    [
        "pilot@10.20.0.10:22",
        "ssh://10.20.0.10:22",
        "10.20.0.10:not-a-port",
        "[10.20.0.10]:22",
        "10.20.0.10:22/path",
    ],
)
def test_bastion_rejects_userinfo_and_malformed_endpoints(monkeypatch, bastion) -> None:
    _enable_policy(monkeypatch)

    with pytest.raises(PilotDestinationInvalid):
        validate_pilot_network_config({"network": {"bastion_host": bastion}})


def test_asyncssh_kwargs_revalidate_bastion_at_runtime(monkeypatch) -> None:
    _enable_policy(monkeypatch)
    server = SimpleNamespace(
        host="10.20.0.10",
        port=22,
        username="pilot",
        auth_method="password",
        network_config={"network": {"bastion_host": "169.254.169.254:22"}},
    )

    with pytest.raises(PilotDestinationDenied):
        build_server_connect_kwargs(server, secret="secret", known_hosts=object())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("network_config", "expected_error"),
    [
        ({"network": {"bastion_host": "pilot@10.20.0.10:22"}}, PilotDestinationInvalid),
        ({"network": {"bastion_host": "169.254.169.254:22"}}, PilotDestinationDenied),
        ({"proxy": {"http_proxy": "http://pilot@10.20.0.10:22"}}, PilotDestinationInvalid),
        ({"proxy": {"http_proxy": "http://169.254.169.254:22"}}, PilotDestinationDenied),
    ],
)
async def test_ssh_connection_manager_rejects_tunnel_before_asyncssh(
    monkeypatch,
    network_config,
    expected_error,
) -> None:
    _enable_policy(monkeypatch)
    manager = SSHConnectionManager()
    server = SimpleNamespace(
        host="10.20.0.10",
        port=22,
        username="pilot",
        auth_method="password",
        network_config=network_config,
    )
    reached_connect = False

    async def fake_known_hosts(_server):
        return object()

    async def fake_connect(**_kwargs):
        nonlocal reached_connect
        reached_connect = True
        raise AssertionError("asyncssh.connect must not be reached")

    monkeypatch.setattr("app.tools.ssh_tools.ensure_server_known_hosts", fake_known_hosts)
    monkeypatch.setattr("app.tools.ssh_tools.asyncssh.connect", fake_connect)

    with pytest.raises(expected_error):
        await manager.connect(
            host=server.host,
            port=server.port,
            username=server.username,
            password="secret",
            network_config=server.network_config,
            server=server,
        )
    assert reached_connect is False


def test_pilot_user_cannot_disable_server_read_only_or_store_sudo(client, monkeypatch) -> None:
    _enable_policy(monkeypatch)
    user = User.objects.create_user("restricted-server-owner", password="x")
    client.force_login(user)
    base = {
        "name": "pilot test host",
        "host": "10.20.0.10",
        "port": 22,
        "username": "pilot",
        "server_type": "ssh",
        "auth_method": "password",
    }

    disable = client.post(
        "/servers/api/create/",
        data=json.dumps({**base, "ai_read_only": False}),
        content_type="application/json",
    )
    string_false = client.post(
        "/servers/api/create/",
        data=json.dumps({**base, "ai_read_only": "false"}),
        content_type="application/json",
    )
    stored_sudo = client.post(
        "/servers/api/create/",
        data=json.dumps({**base, "sudo_auth_mode": "stored_password", "sudo_password": "not-stored"}),
        content_type="application/json",
    )

    assert disable.status_code == 403
    assert disable.json()["code"] == "automation_required"
    assert string_false.status_code == 400
    assert stored_sudo.status_code == 403
    assert Server.objects.count() == 0


def test_server_create_rejects_unsafe_bastion_before_persistence(client, monkeypatch) -> None:
    _enable_policy(monkeypatch)
    user = User.objects.create_user("restricted-bastion-owner", password="x")
    _apply_access_profile(user, "pilot_user")
    client.force_login(user)
    base = {
        "name": "pilot test host",
        "host": "10.20.0.10",
        "port": 22,
        "username": "pilot",
        "server_type": "ssh",
        "auth_method": "password",
    }

    metadata = client.post(
        "/servers/api/create/",
        data=json.dumps({**base, "network_config": {"network": {"bastion_host": "169.254.169.254:22"}}}),
        content_type="application/json",
    )
    userinfo = client.post(
        "/servers/api/create/",
        data=json.dumps({**base, "network_config": {"network": {"bastion_host": "pilot@10.20.0.10:22"}}}),
        content_type="application/json",
    )
    proxy_metadata = client.post(
        "/servers/api/create/",
        data=json.dumps({**base, "network_config": {"proxy": {"http_proxy": "http://169.254.169.254:22"}}}),
        content_type="application/json",
    )

    assert metadata.status_code == 403
    assert metadata.json()["code"] == "pilot_destination_denied"
    assert userinfo.status_code == 400
    assert userinfo.json()["code"] == "invalid_network_config"
    assert proxy_metadata.status_code == 403
    assert proxy_metadata.json()["code"] == "pilot_destination_denied"
    assert Server.objects.count() == 0


def test_raw_execute_endpoint_enforces_read_only_and_sudo_boundary(client, monkeypatch) -> None:
    _enable_policy(monkeypatch)
    user = User.objects.create_user("restricted-raw-exec", password="x")
    _apply_access_profile(user, "pilot_user")
    server = Server.objects.create(
        user=user,
        name="pilot test host",
        host="10.20.0.10",
        port=22,
        username="pilot",
        auth_method="password",
        ai_read_only=True,
    )
    client.force_login(user)
    executed: list[str] = []

    async def fake_connect(**_kwargs):
        return "conn-1"

    async def fake_disconnect(_conn_id):
        return None

    class FakeExecuteTool:
        async def execute(self, **kwargs):
            executed.append(kwargs["command"])
            return {"stdout": "active", "stderr": "", "exit_code": 0}

    monkeypatch.setattr("servers.views.server_ops.ssh_manager.connect", fake_connect)
    monkeypatch.setattr("servers.views.server_ops.ssh_manager.disconnect", fake_disconnect)
    monkeypatch.setattr("servers.views.server_ops.SSHExecuteTool", FakeExecuteTool)

    for command in (
        "touch /tmp/pilot-bypass",
        "mkdir -p /tmp/pilot-bypass",
        "printf owned > /tmp/pilot-bypass",
        "systemctl restart nginx",
        "sudo -n systemctl status nginx",
    ):
        response = client.post(
            f"/servers/api/{server.pk}/execute/",
            data=json.dumps({"command": command, "password": "secret"}),
            content_type="application/json",
        )
        assert response.status_code == 403

    diagnostic = client.post(
        f"/servers/api/{server.pk}/execute/",
        data=json.dumps({"command": "systemctl status nginx", "password": "secret"}),
        content_type="application/json",
    )
    assert diagnostic.status_code == 200
    assert diagnostic.json()["success"] is True
    assert executed == ["systemctl status nginx"]


@pytest.mark.parametrize(
    "suffix",
    ["write/", "chmod/", "chown/", "upload/", "rename/", "delete/", "mkdir/"],
)
def test_pilot_user_cannot_reach_sftp_mutation_endpoints(client, monkeypatch, suffix) -> None:
    _enable_policy(monkeypatch)
    user = User.objects.create_user(f"restricted-sftp-{suffix.rstrip('/')}", password="x")
    _apply_access_profile(user, "pilot_user")
    server = Server.objects.create(
        user=user,
        name="pilot test host",
        host="10.20.0.10",
        port=22,
        username="pilot",
        ai_read_only=True,
    )
    client.force_login(user)

    response = client.post(
        f"/servers/api/{server.pk}/files/{suffix}",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["code"] == "automation_required"


def test_pilot_user_cannot_use_elevated_sftp_read(client, monkeypatch) -> None:
    _enable_policy(monkeypatch)
    user = User.objects.create_user("restricted-sftp-elevated-read", password="x")
    _apply_access_profile(user, "pilot_user")
    server = Server.objects.create(
        user=user,
        name="pilot test host",
        host="10.20.0.10",
        port=22,
        username="pilot",
        ai_read_only=True,
    )
    client.force_login(user)

    response = client.post(
        f"/servers/api/{server.pk}/files/read/",
        data=json.dumps({"path": "/etc/shadow", "elevate": True}),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.json()["code"] == "automation_required"


def test_only_operator_on_writable_server_can_cross_mutation_boundary(monkeypatch) -> None:
    _enable_policy(monkeypatch)
    user = User.objects.create_user("pilot-mutation-policy", password="x")
    writable = Server.objects.create(
        user=user,
        name="writable",
        host="10.20.0.10",
        port=22,
        username="pilot",
        ai_read_only=False,
    )
    read_only = Server.objects.create(
        user=user,
        name="read-only",
        host="10.20.0.10",
        port=22,
        username="pilot",
        ai_read_only=True,
    )

    _apply_access_profile(user, "pilot_user")
    assert decide_server_mutation(user, writable).allowed is False
    assert decide_server_command(user, writable, "sudo -n cat /etc/os-release").allowed is False

    _apply_access_profile(user, "pilot_operator")
    assert decide_server_mutation(user, writable).allowed is True
    assert decide_server_command(user, writable, "sudo -n cat /etc/os-release").allowed is True
    assert decide_server_mutation(user, read_only).allowed is False


def test_server_update_rechecks_read_only_capability_and_destination(client, monkeypatch) -> None:
    _enable_policy(monkeypatch)
    user = User.objects.create_user("restricted-server-update", password="x")
    server = Server.objects.create(
        user=user,
        name="pilot test host",
        host="10.20.0.10",
        port=22,
        username="pilot",
        ai_read_only=True,
    )
    client.force_login(user)

    denied = client.post(
        f"/servers/api/{server.pk}/update/",
        data=json.dumps({"ai_read_only": False}),
        content_type="application/json",
    )
    invalid = client.post(
        f"/servers/api/{server.pk}/update/",
        data=json.dumps({"ai_read_only": "false"}),
        content_type="application/json",
    )
    metadata = client.post(
        f"/servers/api/{server.pk}/update/",
        data=json.dumps({"host": "169.254.169.254"}),
        content_type="application/json",
    )
    bastion_userinfo = client.post(
        f"/servers/api/{server.pk}/update/",
        data=json.dumps({"network_config": {"network": {"bastion_host": "pilot@10.20.0.10:22"}}}),
        content_type="application/json",
    )
    bastion_metadata = client.post(
        f"/servers/api/{server.pk}/update/",
        data=json.dumps({"network_config": {"network": {"bastion_host": "169.254.169.254:22"}}}),
        content_type="application/json",
    )

    assert denied.status_code == 403
    assert invalid.status_code == 400
    assert metadata.status_code == 403
    assert bastion_userinfo.status_code == 400
    assert bastion_metadata.status_code == 403
    server.refresh_from_db()
    assert server.host == "10.20.0.10"
    assert server.ai_read_only is True
    assert server.network_config == {}

    _apply_access_profile(user, "pilot_operator")
    allowed = client.post(
        f"/servers/api/{server.pk}/update/",
        data=json.dumps({"ai_read_only": False}),
        content_type="application/json",
    )
    assert allowed.status_code == 200
    server.refresh_from_db()
    assert server.ai_read_only is False
