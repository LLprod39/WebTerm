from __future__ import annotations

from app.agent_kernel.sandbox.runtime_errors import (
    KIND_CONTROL_PLANE,
    KIND_SSH,
    classify_agent_runtime_detail,
    format_control_plane_message,
    format_runtime_error,
    is_control_plane_text,
)


def test_docker_sock_permission_is_control_plane():
    detail = "permission denied while trying to connect to the docker API at unix:///var/run/docker.sock"
    assert classify_agent_runtime_detail(detail) == KIND_CONTROL_PLANE
    assert is_control_plane_text(detail)
    message = format_runtime_error(KIND_CONTROL_PLANE, detail)
    assert "CONTROL_PLANE" in message
    assert "SSH" not in message.split("Docker")[0] or "целевом сервере не запускались" in message
    assert "nikitavm" not in message.lower()


def test_plain_command_output_is_not_control_plane():
    assert not is_control_plane_text("ssh_execute nginx active")


def test_ssh_auth_failure_is_not_control_plane():
    detail = "Permission denied (publickey)."
    assert classify_agent_runtime_detail(detail) == KIND_SSH
    assert not is_control_plane_text(detail)
    assert "SSH:" in format_runtime_error(KIND_SSH, detail)


def test_control_plane_message_mentions_gid(monkeypatch):
    monkeypatch.setenv("DOCKER_SOCKET_GID", "998")
    text = format_control_plane_message("docker.sock")
    assert "DOCKER_SOCKET_GID=998" in text
    assert "agent-execution" in text
