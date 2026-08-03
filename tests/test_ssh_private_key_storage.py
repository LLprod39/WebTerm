from __future__ import annotations

import io
import os
import stat
from pathlib import Path

import asyncssh
import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings

from core_ui.managed_secrets import SERVER_SSH_PRIVATE_KEY_NAMESPACE
from core_ui.models.secrets import ManagedSecret
from servers.models_inventory import Server
from servers.ssh_host_keys import build_known_hosts, build_server_connect_kwargs
from servers.ssh_private_keys import (
    get_server_private_key_text,
    is_managed_private_key_reference,
    store_uploaded_private_key,
    write_ephemeral_private_key,
)


def _private_key_text() -> str:
    exported = asyncssh.generate_private_key("ssh-ed25519").export_private_key("openssh")
    return exported.decode("utf-8") if isinstance(exported, bytes) else exported


def _server(*, username: str = "managed-key-user") -> Server:
    user = User.objects.create_user(username=username, password="x")
    return Server.objects.create(
        user=user,
        name="managed-key-server",
        host="192.0.2.50",
        username="deploy",
        auth_method="key",
    )


@pytest.mark.django_db
def test_uploaded_private_key_is_encrypted_in_managed_secret_store(tmp_path: Path) -> None:
    server = _server()
    private_key = _private_key_text()

    with override_settings(SSH_PRIVATE_KEYS_DIR=tmp_path / "ssh_keys"):
        server.key_path = store_uploaded_private_key(server, private_key)
        server.save(update_fields=["key_path"])

        assert is_managed_private_key_reference(server.key_path, server_id=server.id)
        assert get_server_private_key_text(server) == private_key.strip() + "\n"
        assert not list((tmp_path / "ssh_keys").rglob("*.key"))

    stored = ManagedSecret.objects.get(namespace=SERVER_SSH_PRIVATE_KEY_NAMESPACE, object_id=server.id)
    assert stored.ciphertext.startswith("v2:")
    assert "PRIVATE KEY" not in stored.ciphertext
    assert private_key.strip() not in stored.ciphertext


@pytest.mark.django_db
def test_managed_private_key_is_imported_in_memory_for_asyncssh() -> None:
    server = _server(username="managed-key-runtime")
    private_key = _private_key_text()
    server.key_path = store_uploaded_private_key(server, private_key)
    server.save(update_fields=["key_path"])

    host_public_key = asyncssh.generate_private_key("ssh-ed25519").export_public_key("openssh")
    if isinstance(host_public_key, bytes):
        host_public_key = host_public_key.decode("utf-8")
    known_hosts = build_known_hosts(
        server.host,
        server.port,
        [{"public_key": host_public_key.strip()}],
    )
    kwargs = build_server_connect_kwargs(
        server,
        known_hosts=known_hosts,
        private_key_text=get_server_private_key_text(server),
    )

    assert kwargs["client_keys"]
    assert not isinstance(kwargs["client_keys"][0], (str, Path))
    assert kwargs["client_keys"][0].get_algorithm() == "ssh-ed25519"


def test_ephemeral_private_key_writer_enforces_os_permissions(tmp_path: Path) -> None:
    private_key = _private_key_text()
    key_path = write_ephemeral_private_key(tmp_path / "runtime-key", private_key)

    assert key_path.read_text(encoding="utf-8") == private_key.strip() + "\n"
    if os.name != "nt":
        assert stat.S_IMODE(key_path.stat().st_mode) == 0o600


@pytest.mark.django_db
def test_plaintext_key_migration_is_idempotent_and_removes_legacy_file(tmp_path: Path) -> None:
    server = _server(username="legacy-key-migration")
    key_root = tmp_path / "ssh_keys"
    key_file = key_root / f"user-{server.user_id}" / f"server-{server.id}-legacy.key"
    key_file.parent.mkdir(parents=True)
    private_key = _private_key_text()
    key_file.write_text(private_key, encoding="utf-8")
    orphan_file = key_root / "user-999" / "server-999-orphan.key"
    orphan_file.parent.mkdir(parents=True)
    orphan_file.write_text(_private_key_text(), encoding="utf-8")
    server.key_path = f"/workspace/data/ssh_keys/user-{server.user_id}/{key_file.name}"
    server.save(update_fields=["key_path"])

    with override_settings(SSH_PRIVATE_KEYS_DIR=key_root):
        first_output = io.StringIO()
        call_command("migrate_ssh_private_keys", "--apply", stdout=first_output)
        server.refresh_from_db()

        assert is_managed_private_key_reference(server.key_path, server_id=server.id)
        assert get_server_private_key_text(server) == private_key.strip() + "\n"
        assert not key_file.exists()
        assert not orphan_file.exists()
        assert "migrated=1" in first_output.getvalue()
        assert "orphans_removed=1" in first_output.getvalue()

        second_output = io.StringIO()
        call_command("migrate_ssh_private_keys", "--apply", stdout=second_output)
        assert "migrated=0" in second_output.getvalue()
        assert "already_managed=1" in second_output.getvalue()


@pytest.mark.django_db(transaction=True)
def test_deleting_server_deletes_managed_private_key() -> None:
    server = _server(username="managed-key-delete")
    server.key_path = store_uploaded_private_key(server, _private_key_text())
    server.save(update_fields=["key_path"])
    server_id = server.id

    server.delete()

    assert not ManagedSecret.objects.filter(
        namespace=SERVER_SSH_PRIVATE_KEY_NAMESPACE,
        object_id=server_id,
    ).exists()
