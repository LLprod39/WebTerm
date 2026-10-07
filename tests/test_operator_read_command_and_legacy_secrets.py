"""Operator read_command + legacy encrypted_password SSH fallback."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from app.assistant_actions import AssistantActionContext
from core_ui.services.operator_tools import is_auto_executable_read, specs_to_tools
from servers.encryption import PasswordEncryption
from servers.models_inventory import Server
from servers.operator.mutate_exec import is_operator_safe_read_command, read_command
from servers.secret_utils import (
    get_server_auth_secret,
    has_managed_server_secret,
    server_secret_storage_mode,
)


pytestmark = pytest.mark.django_db


def _server(user: User, name: str = "prom-01") -> Server:
    return Server.objects.create(
        user=user,
        name=name,
        host="10.0.0.55",
        username="root",
        auth_method="password",
    )


def test_legacy_encrypted_password_falls_back_and_promotes(monkeypatch):
    user = User.objects.create_user("legacy-ssh-user", password="x")
    server = _server(user)
    master = "legacy-master"
    salt = PasswordEncryption.generate_salt()
    Server.objects.filter(pk=server.pk).update(
        encrypted_password=PasswordEncryption.encrypt_password("prom-secret", master, salt),
        salt=salt,
    )
    server.refresh_from_db()
    assert not has_managed_server_secret(server)
    assert server_secret_storage_mode(server) == "legacy"

    monkeypatch.setenv("MASTER_PASSWORD", master)
    secret = get_server_auth_secret(server)
    assert secret == "prom-secret"
    server.refresh_from_db()
    assert has_managed_server_secret(server)
    assert server.encrypted_password == ""
    assert server_secret_storage_mode(server) == "managed"
    assert get_server_auth_secret(server) == "prom-secret"


def test_is_operator_safe_read_command_allows_journalctl_rejects_follow():
    assert is_operator_safe_read_command("journalctl -n 200 --no-pager -p err")
    assert is_operator_safe_read_command("docker logs --tail 100 nginx")
    assert is_operator_safe_read_command("systemctl status nginx")
    assert not is_operator_safe_read_command("journalctl -f")
    assert not is_operator_safe_read_command("rm -rf /var/log")
    assert not is_operator_safe_read_command("systemctl restart nginx")


def test_is_auto_executable_read_for_safe_run_command():
    assert is_auto_executable_read("operator.read_command", {"command": "df -h"})
    assert is_auto_executable_read(
        "operator.run_command",
        {"server_id": 1, "command": "journalctl -n 50 --no-pager"},
    )
    assert not is_auto_executable_read(
        "operator.run_command",
        {"server_id": 1, "command": "systemctl restart nginx"},
    )


def test_read_command_rejects_mutating_and_executes_safe(monkeypatch):
    user = User.objects.create_user("read-cmd-user", password="x")
    from core_ui.views.access_views import _apply_access_profile

    _apply_access_profile(user, "pilot_operator")
    server = _server(user)

    with pytest.raises(Exception) as exc:
        read_command(
            AssistantActionContext(
                user=user,
                input_payload={"server_id": server.pk, "command": "systemctl restart nginx"},
            )
        )
    assert "read-only" in str(exc.value).lower()

    captured: dict = {}

    def fake_execute(ctx, srv, command, *, allow_destructive):
        captured["command"] = command
        captured["server_id"] = srv.pk
        return {
            "ok": True,
            "server_id": srv.pk,
            "server_name": srv.name,
            "exit_code": 0,
            "output": "error lines",
        }

    monkeypatch.setattr("servers.operator.mutate_exec._execute_on_server", fake_execute)
    result = read_command(
        AssistantActionContext(
            user=user,
            input_payload={
                "server_id": server.pk,
                "command": "journalctl -n 100 --no-pager -p err",
            },
        )
    )
    assert result["ok"] is True
    assert result["read_only"] is True
    assert captured["command"].startswith("journalctl")


def test_specs_include_read_command_for_log_audit():
    user = User.objects.create_user("tools-user", password="x")
    from core_ui.views.access_views import _apply_access_profile

    _apply_access_profile(user, "pilot_operator")
    from servers.operator.mutate_tools import register_operator_mutate_tools

    register_operator_mutate_tools()
    tools = specs_to_tools(user, message="проверь логи на ошибки @prom-01")
    action_types = {t.get("action_type") for t in tools}
    assert "operator.read_command" in action_types
