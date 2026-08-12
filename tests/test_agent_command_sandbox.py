from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import override_settings

from app.agent_kernel.sandbox.ephemeral_runner import (
    AgentCommandResult,
    AgentCommandRuntimeError,
    agent_command_uses_docker,
    build_agent_command_docker_command,
    execute_ephemeral_ssh_command,
)
from servers.agents import mini_executor
from servers.agents.agent_sessions import AgentSessionManager
from servers.checks import agent_command_runtime_deploy_check
from servers.models_agents import ServerAgent
from servers.models_inventory import Server
from studio.pipeline import pipeline_agent_runtime_ssh

IMMUTABLE_IMAGE = "registry.example/webterm-agent-command@sha256:" + "a" * 64


def test_host_agent_command_runtime_is_test_only_and_fail_closed() -> None:
    with (
        override_settings(
            AGENT_COMMAND_RUNTIME="host",
            TESTING=False,
            AGENT_COMMAND_ALLOW_UNSAFE_HOST_RUNTIME_FOR_TESTS=True,
        ),
        pytest.raises(AgentCommandRuntimeError, match="allowed only in tests"),
    ):
        agent_command_uses_docker()


def test_deploy_check_rejects_host_runtime_and_mutable_image() -> None:
    with override_settings(DEBUG=False, AGENT_COMMAND_RUNTIME="host"):
        errors = agent_command_runtime_deploy_check(None)
    assert [error.id for error in errors] == ["servers.E002"]

    with override_settings(
        DEBUG=False,
        AGENT_COMMAND_RUNTIME="docker",
        AGENT_COMMAND_RUNNER_IMAGE="webterm-agent-command:latest",
    ):
        errors = agent_command_runtime_deploy_check(None)
    assert [error.id for error in errors] == ["servers.E003"]

    with override_settings(
        DEBUG=False,
        AGENT_COMMAND_RUNTIME="docker",
        AGENT_COMMAND_RUNNER_IMAGE=IMMUTABLE_IMAGE,
    ):
        assert agent_command_runtime_deploy_check(None) == []


@pytest.mark.parametrize(
    "image",
    ["", "webterm-agent-command:latest", "runner@sha256:abc", "runner@sha256:" + "A" * 64],
)
def test_agent_command_runner_rejects_mutable_images(image: str) -> None:
    with (
        override_settings(AGENT_COMMAND_RUNNER_IMAGE=image),
        pytest.raises(AgentCommandRuntimeError, match="immutable"),
    ):
        build_agent_command_docker_command()


def test_agent_command_runner_accepts_immutable_local_image_id() -> None:
    with override_settings(AGENT_COMMAND_RUNNER_IMAGE="sha256:" + "b" * 64):
        command = build_agent_command_docker_command(runner_id="1" * 32)
    assert command[-1] == "sha256:" + "b" * 64


def test_agent_command_container_is_hardened_and_mounts_agent_socket(tmp_path: Path) -> None:
    agent_socket = tmp_path / "agent.sock"
    agent_socket.write_text("socket-placeholder", encoding="utf-8")

    with override_settings(
        AGENT_COMMAND_RUNNER_IMAGE=IMMUTABLE_IMAGE,
        AGENT_COMMAND_DOCKER_NETWORK="agent-egress",
        AGENT_COMMAND_DOCKER_CPUS="0.25",
        AGENT_COMMAND_DOCKER_MEMORY="128m",
        AGENT_COMMAND_DOCKER_PIDS_LIMIT=32,
    ):
        command = build_agent_command_docker_command(
            ssh_agent_socket=str(agent_socket),
            runner_id="0" * 32,
        )

    assert command[:4] == ["docker", "run", "--rm", "--interactive"]
    assert "--read-only" in command
    assert command[command.index("--pull") + 1] == "never"
    assert command[command.index("--name") + 1] == "webterm-agent-command-" + "0" * 32
    assert command[command.index("--user") + 1] == "10001:10001"
    assert command[command.index("--cgroupns") + 1] == "private"
    assert command[command.index("--network") + 1] == "agent-egress"
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--security-opt") + 1] == "no-new-privileges:true"
    assert command[command.index("--pids-limit") + 1] == "32"
    mounts = [command[index + 1] for index, value in enumerate(command) if value == "--mount"]
    assert any("dst=/run/ssh-agent.sock" in mount and mount.endswith("readonly") for mount in mounts)
    assert command[-1] == IMMUTABLE_IMAGE


@pytest.mark.asyncio
async def test_agent_command_secrets_are_sent_only_on_stdin(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    private_key = tmp_path / "id_ed25519"
    private_key.write_text("private-key-secret-value", encoding="utf-8")

    class FakeProcess:
        returncode = 0

        async def communicate(self, payload: bytes):
            captured["stdin"] = payload
            response = {
                "schema": "webterm.agent-command-result.v1",
                "stdout": "ok",
                "stderr": "",
                "exit_status": 0,
                "duration_ms": 7,
            }
            return json.dumps(response).encode(), b""

    async def fake_spawn(*args, **kwargs):
        captured["args"] = list(args)
        captured["kwargs"] = dict(kwargs)
        return FakeProcess()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_spawn)
    with override_settings(
        AGENT_COMMAND_RUNTIME="docker",
        AGENT_COMMAND_RUNNER_IMAGE=IMMUTABLE_IMAGE,
    ):
        result = await execute_ephemeral_ssh_command(
            connect_kwargs={
                "host": "prod.example",
                "port": 22,
                "username": "deploy",
                "password": "ssh-secret-value",
                "passphrase": "key-secret-value",
            },
            command="printf command-secret-value",
            known_hosts_text="prod.example ssh-ed25519 AAAATEST\n",
            key_path=str(private_key),
            input_text="sudo-secret-value\n",
        )

    args_text = " ".join(str(item) for item in captured["args"])
    kwargs_text = json.dumps(captured["kwargs"], default=str)
    for secret in (
        "ssh-secret-value",
        "private-key-secret-value",
        "key-secret-value",
        "sudo-secret-value",
        "command-secret-value",
    ):
        assert secret not in args_text
        assert secret not in kwargs_text
    stdin_payload = json.loads(bytes(captured["stdin"]).decode())
    assert stdin_payload["password"] == "ssh-secret-value"
    assert stdin_payload["private_key"] == "private-key-secret-value"
    assert stdin_payload["passphrase"] == "key-secret-value"
    assert stdin_payload["input"] == "sudo-secret-value\n"
    assert stdin_payload["command"] == "printf command-secret-value"
    assert result.runtime == "docker"
    assert result.exit_status == 0


@pytest.mark.asyncio
async def test_full_agent_open_does_not_connect_from_backend_in_docker_mode(monkeypatch) -> None:
    server = SimpleNamespace(id=7, name="prod", host="prod.example", port=22, user=None, group=None)
    manager = AgentSessionManager([server])

    async def forbidden_connect_kwargs(_server):
        raise AssertionError("backend must not prepare a direct SSH session")

    monkeypatch.setattr("servers.agents.agent_sessions._build_connect_kwargs", forbidden_connect_kwargs)
    with override_settings(AGENT_COMMAND_RUNTIME="docker"):
        await manager.open(server)

    assert manager.connections[7].conn is None
    assert manager.connections[7].proc is None


def test_mini_and_studio_agent_paths_have_no_direct_ssh_connect() -> None:
    assert "asyncssh.connect" not in inspect.getsource(mini_executor)
    assert "asyncssh.connect" not in inspect.getsource(pipeline_agent_runtime_ssh)


@pytest.mark.django_db(transaction=True)
def test_mini_agent_executes_each_command_through_isolated_runner(monkeypatch) -> None:
    user = User.objects.create_user(username="mini-sandbox-user", password="x")
    server = Server.objects.create(
        user=user,
        name="mini-prod",
        host="prod.example",
        username="deploy",
        auth_method="password",
        ai_read_only=True,
    )
    agent = ServerAgent.objects.create(
        user=user,
        name="Mini isolated",
        mode=ServerAgent.MODE_MINI,
        commands=["uptime"],
    )
    calls: list[tuple[int, str]] = []

    async def fake_run_agent_command(server_obj, command, **_kwargs):
        calls.append((server_obj.id, command))
        return AgentCommandResult("up", "", 0, 4, "docker")

    async def fake_ai_analysis(*_args, **_kwargs):
        return "healthy"

    async def no_async_work(*_args, **_kwargs):
        return None

    monkeypatch.setattr(mini_executor, "run_agent_command", fake_run_agent_command)
    monkeypatch.setattr(mini_executor, "get_ai_analysis", fake_ai_analysis)
    monkeypatch.setattr(mini_executor, "deliver_agent_report_async", no_async_work)
    monkeypatch.setattr(mini_executor, "log_user_activity", lambda **_kwargs: None)
    monkeypatch.setattr(
        "servers.adapters.memory_store.DjangoServerMemoryStore._ingest_event_sync",
        lambda *_args, **_kwargs: None,
    )

    run = async_to_sync(mini_executor.run_agent)(agent, server, user)

    assert run.status == run.STATUS_COMPLETED
    assert calls == [(server.id, "uptime")]
    assert run.commands_output[0]["runtime"] == "docker"
