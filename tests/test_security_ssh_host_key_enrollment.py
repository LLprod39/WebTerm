"""Regression tests for explicit SSH host-key enrollment."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import asyncssh
import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client

from servers.chat_server_provider import DjangoChatServerProvider
from servers.models import Server
from servers.services import ansible_setup
from servers.ssh_host_keys import (
    SSHHostKeyEnrollmentRequired,
    SSHHostKeyFingerprintMismatch,
    SSHHostKeyVerificationError,
    ensure_server_known_hosts,
    verified_known_hosts_for_host,
)
from servers.views import server_ops


def _host_key_record() -> dict[str, str]:
    key = asyncssh.generate_private_key("ssh-ed25519")
    public_key = key.export_public_key("openssh")
    if isinstance(public_key, bytes):
        public_key = public_key.decode("utf-8")
    parsed = asyncssh.import_public_key(public_key)
    return {
        "public_key": public_key.strip(),
        "algorithm": parsed.get_algorithm(),
        "fingerprint_sha256": parsed.get_fingerprint("sha256"),
        "trusted_at": "2026-07-29T00:00:00+00:00",
    }


@pytest.mark.django_db
def test_first_connection_fails_closed_without_persisting_network_key(monkeypatch):
    owner = User.objects.create_user(username="ssh-first-contact", password="x")
    server = Server.objects.create(
        user=owner,
        name="first-contact",
        host="192.0.2.10",
        username="root",
        auth_method="key",
        key_path="/tmp/id_ed25519",
    )
    network_calls = 0

    async def fake_get_server_host_key(**_kwargs):
        nonlocal network_calls
        network_calls += 1
        return asyncssh.generate_private_key("ssh-ed25519")

    monkeypatch.setattr("servers.ssh_host_keys.asyncssh.get_server_host_key", fake_get_server_host_key)

    with pytest.raises(SSHHostKeyVerificationError, match="подтвержд|enroll|trusted"):
        async_to_sync(ensure_server_known_hosts)(server)

    server.refresh_from_db()
    assert network_calls == 0
    assert server.trusted_host_keys == []


def test_ad_hoc_host_requires_out_of_band_fingerprint(monkeypatch):
    record = _host_key_record()
    parsed_key = asyncssh.import_public_key(record["public_key"])
    network_calls = 0

    async def fake_get_server_host_key(**_kwargs):
        nonlocal network_calls
        network_calls += 1
        return parsed_key

    monkeypatch.setattr("servers.ssh_host_keys.asyncssh.get_server_host_key", fake_get_server_host_key)

    with pytest.raises(SSHHostKeyEnrollmentRequired):
        async_to_sync(verified_known_hosts_for_host)(
            "192.0.2.15",
            22,
            expected_fingerprint="",
        )
    assert network_calls == 0

    with pytest.raises(SSHHostKeyFingerprintMismatch):
        async_to_sync(verified_known_hosts_for_host)(
            "192.0.2.15",
            22,
            expected_fingerprint="SHA256:wrong",
        )
    assert network_calls == 1

    known_hosts, observed = async_to_sync(verified_known_hosts_for_host)(
        "192.0.2.15",
        22,
        expected_fingerprint=record["fingerprint_sha256"],
    )
    assert observed["fingerprint_sha256"] == record["fingerprint_sha256"]
    assert len(known_hosts.match("192.0.2.15", None, 22)[0]) == 1


def test_ansible_inventory_rejects_every_target_without_trusted_key(tmp_path):
    server = SimpleNamespace(
        id=91,
        name="untrusted-target",
        host="192.0.2.91",
        port=22,
        username="root",
        auth_method="key",
        key_path="",
        group=None,
        trusted_host_keys=[],
    )

    with pytest.raises(SSHHostKeyVerificationError, match="untrusted-target"):
        ansible_setup._write_inventory(Path(tmp_path), [server])

    assert not (Path(tmp_path) / "inventory.ini").exists()
    assert not (Path(tmp_path) / "known_hosts").exists()


@pytest.mark.django_db
def test_chat_server_context_never_bypasses_host_key_or_embeds_credentials():
    owner = User.objects.create_user(username="ssh-chat-owner", password="x")
    Server.objects.create(
        user=owner,
        name="chat-target",
        host="192.0.2.31",
        username="root",
        auth_method="password",
        encrypted_password="do-not-place-in-prompt",
    )

    context = DjangoChatServerProvider().get_servers_context_for_prompt(owner.id)

    assert "server_id=" in context
    assert "host_key=enrollment_required" in context
    assert "do-not-place-in-prompt" not in context
    assert "sshpass" not in context
    assert "StrictHostKeyChecking=no" not in context


@pytest.mark.django_db
def test_connection_test_requires_exact_owner_confirmed_fingerprint(monkeypatch):
    owner = User.objects.create_user(username="ssh-enrollment-owner", password="x")
    server = Server.objects.create(
        user=owner,
        name="enrollment-target",
        host="192.0.2.20",
        username="root",
        auth_method="key",
        key_path="/tmp/id_ed25519",
    )
    candidate = _host_key_record()
    connect_calls: list[dict] = []

    async def fake_probe(_server, **_kwargs):
        return dict(candidate)

    async def fake_connect(**kwargs):
        connect_calls.append(dict(kwargs))
        return "conn-enrolled"

    async def fake_disconnect(_conn_id):
        return None

    monkeypatch.setattr(server_ops, "probe_server_host_key", fake_probe, raising=False)
    monkeypatch.setattr("servers.ssh_host_keys.probe_server_host_key", fake_probe)
    monkeypatch.setattr(server_ops.ssh_manager, "connect", fake_connect)
    monkeypatch.setattr(server_ops.ssh_manager, "disconnect", fake_disconnect)

    client = Client()
    client.force_login(owner)
    preview = client.post(
        f"/servers/api/{server.id}/test/",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert preview.status_code == 200
    assert preview.json()["success"] is False
    assert preview.json()["code"] == "host_key_confirmation_required"
    assert preview.json()["host_key"]["fingerprint_sha256"] == candidate["fingerprint_sha256"]
    assert connect_calls == []
    server.refresh_from_db()
    assert server.trusted_host_keys == []

    wrong = client.post(
        f"/servers/api/{server.id}/test/",
        data=json.dumps(
            {
                "enroll_host_key": True,
                "expected_host_key_fingerprint": "SHA256:not-the-candidate",
            }
        ),
        content_type="application/json",
    )
    assert wrong.status_code == 200
    assert wrong.json()["code"] == "host_key_fingerprint_mismatch"
    assert connect_calls == []
    server.refresh_from_db()
    assert server.trusted_host_keys == []

    confirmed = client.post(
        f"/servers/api/{server.id}/test/",
        data=json.dumps(
            {
                "enroll_host_key": True,
                "expected_host_key_fingerprint": candidate["fingerprint_sha256"],
            }
        ),
        content_type="application/json",
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["success"] is True
    assert len(connect_calls) == 1
    server.refresh_from_db()
    assert server.trusted_host_keys[0]["fingerprint_sha256"] == candidate["fingerprint_sha256"]


@pytest.mark.django_db
def test_changed_host_key_blocks_credentials_until_explicit_rotation(monkeypatch):
    owner = User.objects.create_user(username="ssh-rotation-owner", password="x")
    trusted = _host_key_record()
    candidate = _host_key_record()
    server = Server.objects.create(
        user=owner,
        name="rotation-target",
        host="192.0.2.40",
        username="root",
        auth_method="key",
        key_path="/tmp/id_ed25519",
        trusted_host_keys=[trusted],
    )
    connect_calls: list[dict] = []

    async def fake_probe(_server, **_kwargs):
        return dict(candidate)

    async def fake_connect(**kwargs):
        connect_calls.append(dict(kwargs))
        return "conn-rotated"

    async def fake_disconnect(_conn_id):
        return None

    monkeypatch.setattr(server_ops, "probe_server_host_key", fake_probe)
    monkeypatch.setattr("servers.ssh_host_keys.probe_server_host_key", fake_probe)
    monkeypatch.setattr(server_ops.ssh_manager, "connect", fake_connect)
    monkeypatch.setattr(server_ops.ssh_manager, "disconnect", fake_disconnect)

    client = Client()
    client.force_login(owner)
    preview = client.post(
        f"/servers/api/{server.id}/test/",
        data=json.dumps({}),
        content_type="application/json",
    )

    assert preview.status_code == 200
    assert preview.json()["code"] == "host_key_rotation_confirmation_required"
    assert preview.json()["host_key"]["fingerprint_sha256"] == candidate["fingerprint_sha256"]
    assert preview.json()["trusted_fingerprints"] == [trusted["fingerprint_sha256"]]
    assert connect_calls == []
    server.refresh_from_db()
    assert server.trusted_host_keys[0]["fingerprint_sha256"] == trusted["fingerprint_sha256"]

    ambiguous_confirmation = client.post(
        f"/servers/api/{server.id}/test/",
        data=json.dumps(
            {
                "enroll_host_key": True,
                "expected_host_key_fingerprint": candidate["fingerprint_sha256"],
                "replace_host_key": "false",
            }
        ),
        content_type="application/json",
    )

    assert ambiguous_confirmation.status_code == 409
    assert ambiguous_confirmation.json()["code"] == "host_key_enrollment_rejected"
    assert connect_calls == []
    server.refresh_from_db()
    assert server.trusted_host_keys[0]["fingerprint_sha256"] == trusted["fingerprint_sha256"]

    confirmed = client.post(
        f"/servers/api/{server.id}/test/",
        data=json.dumps(
            {
                "enroll_host_key": True,
                "expected_host_key_fingerprint": candidate["fingerprint_sha256"],
                "replace_host_key": True,
            }
        ),
        content_type="application/json",
    )

    assert confirmed.status_code == 200
    assert confirmed.json()["success"] is True
    assert len(connect_calls) == 1
    server.refresh_from_db()
    assert server.trusted_host_keys[0]["fingerprint_sha256"] == candidate["fingerprint_sha256"]
