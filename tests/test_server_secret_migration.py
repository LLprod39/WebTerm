from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import RequestFactory

from servers.encryption import PasswordEncryption
from servers.models_inventory import Server
from servers.secret_utils import (
    get_server_auth_secret,
    get_server_sudo_secret,
    server_secret_storage_mode,
    store_server_auth_secret,
    store_server_sudo_secret,
)
from servers.views.server_helpers import _resolve_server_secret

pytestmark = pytest.mark.django_db


def _server(username: str) -> Server:
    user = User.objects.create_user(username=username, password="x")
    return Server.objects.create(
        user=user,
        name=f"{username}-server",
        host="10.0.0.70",
        username="root",
        auth_method="password",
        sudo_auth_mode="stored_password",
    )


def test_migration_command_reports_migrates_and_clears_legacy_fields():
    server = _server("legacy-secret-migration")
    master_password = "legacy-master-password"
    auth_salt = PasswordEncryption.generate_salt()
    sudo_salt = PasswordEncryption.generate_salt()
    Server.objects.filter(pk=server.pk).update(
        encrypted_password=PasswordEncryption.encrypt_password("auth-secret", master_password, auth_salt),
        salt=auth_salt,
        encrypted_sudo_password=PasswordEncryption.encrypt_password("sudo-secret", master_password, sudo_salt),
        sudo_salt=sudo_salt,
    )

    dry_output = io.StringIO()
    call_command(
        "migrate_legacy_server_secrets",
        master_password=master_password,
        stdout=dry_output,
    )
    assert "would migrate" in dry_output.getvalue()
    assert Server.objects.get(pk=server.pk).encrypted_password

    output = io.StringIO()
    call_command(
        "migrate_legacy_server_secrets",
        master_password=master_password,
        apply=True,
        clear_legacy=True,
        stdout=output,
    )
    server.refresh_from_db()
    assert get_server_auth_secret(server) == "auth-secret"
    assert get_server_sudo_secret(server) == "sudo-secret"
    assert server_secret_storage_mode(server) == "managed"
    assert server.encrypted_password == ""
    assert server.salt is None
    assert server.encrypted_sudo_password == ""
    assert server.sudo_salt is None
    assert "migrated=1" in output.getvalue()
    assert "cleared=1" in output.getvalue()


def test_managed_secret_write_and_connection_read_do_not_run_pbkdf2():
    server = _server("managed-secret-no-pbkdf2")
    with (
        patch.object(PasswordEncryption, "generate_salt", side_effect=AssertionError("PBKDF2 path used")),
        patch.object(PasswordEncryption, "encrypt_password", side_effect=AssertionError("PBKDF2 path used")),
        patch.object(PasswordEncryption, "decrypt_password", side_effect=AssertionError("PBKDF2 path used")),
    ):
        store_server_auth_secret(server, secret_value="managed-auth", master_password="ignored")
        store_server_sudo_secret(server, secret_value="managed-sudo", master_password="ignored")
        request = RequestFactory().post("/servers/connect/")
        request.user = server.user
        assert _resolve_server_secret(server, request, {}) == "managed-auth"
        assert get_server_sudo_secret(server) == "managed-sudo"


def test_migration_command_without_legacy_rows_needs_no_master_password():
    _server("no-legacy-secret")
    output = io.StringIO()
    call_command("migrate_legacy_server_secrets", stdout=output)
    assert "migrated=0" in output.getvalue()
    assert "failed=0" in output.getvalue()
