import io
import json

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from core_ui.models import UserAppPermission
from servers.models import Server, ServerAgent
from studio.models import Pipeline


@pytest.mark.django_db
def test_seed_multi_user_smoke_creates_domain_objects_through_providers():
    stdout = io.StringIO()

    call_command(
        "seed_multi_user_smoke",
        users=1,
        prefix="provider-smoke",
        password="SmokePass123!",
        ssh_host="smoke-host",
        ssh_port=2200,
        ssh_username="smoke",
        ssh_password="smoke-secret",
        json=True,
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    seeded_user = payload["users"][0]

    user = User.objects.get(username="provider-smoke-01")
    assert seeded_user["username"] == user.username

    assert set(UserAppPermission.objects.filter(user=user, allowed=True).values_list("feature", flat=True)) == {
        "servers",
        "studio",
        "agents",
    }

    server = Server.objects.get(pk=seeded_user["server_id"])
    assert server.user_id == user.id
    assert server.name == "Smoke SSH 01"
    assert server.host == "smoke-host"
    assert server.port == 2200
    assert server.username == "smoke"
    assert server.auth_method == "password"
    assert server.server_type == "ssh"
    assert server.trusted_host_keys == []

    pipeline = Pipeline.objects.get(pk=seeded_user["pipeline_id"])
    assert pipeline.owner_id == user.id
    assert pipeline.name == "Smoke Pipeline 01"
    assert pipeline.nodes[1]["data"]["server_id"] == server.id

    agent = ServerAgent.objects.get(pk=seeded_user["agent_id"])
    assert agent.user_id == user.id
    assert agent.name == "Smoke Agent 01"
    assert agent.servers.filter(pk=server.id).exists()


@pytest.mark.django_db
def test_seed_multi_user_smoke_enrolls_only_the_confirmed_host_key(monkeypatch):
    observed: dict[str, object] = {}

    async def fake_enroll(server, *, expected_fingerprint, allow_replace, connect_timeout=10):
        observed.update(
            server_id=server.id,
            expected_fingerprint=expected_fingerprint,
            allow_replace=allow_replace,
        )
        return {"fingerprint_sha256": expected_fingerprint}

    monkeypatch.setattr("servers.smoke_seed_provider.enroll_server_host_key", fake_enroll)

    call_command(
        "seed_multi_user_smoke",
        users=1,
        prefix="trusted-smoke",
        password="SmokePass123!",
        ssh_host="smoke-host",
        ssh_port=2200,
        ssh_username="smoke",
        ssh_password="smoke-secret",
        ssh_host_key_fingerprint="SHA256:confirmed-smoke-key",
        json=True,
        stdout=io.StringIO(),
    )

    server = Server.objects.get(user__username="trusted-smoke-01")
    assert observed == {
        "server_id": server.id,
        "expected_fingerprint": "SHA256:confirmed-smoke-key",
        "allow_replace": True,
    }
