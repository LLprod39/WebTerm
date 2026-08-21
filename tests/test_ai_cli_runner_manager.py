from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import replace

import pytest

from ai_cli_runner_manager.config import RunnerManagerConfig
from ai_cli_runner_manager.docker_runtime import (
    DockerCliRuntime,
    _drain_bounded,
    build_cli_runner_docker_command,
)
from ai_cli_runner_manager.protocol import RunnerAction, RunnerProtocolError, RunnerRequestV1
from app.ai_runtime import ProviderEventType


def _config() -> RunnerManagerConfig:
    return RunnerManagerConfig(
        token="manager-token",
        codex_runner_image="registry.example/webterm-codex@sha256:" + "a" * 64,
        grok_runner_image="registry.example/webterm-grok@sha256:" + "b" * 64,
        docker_network="webterm-ai-cli-egress",
    )


def _request(**overrides: object) -> RunnerRequestV1:
    values = {
        "action": RunnerAction.RUN,
        "connection_ref": "connection_1234",
        "target_id": "codex_subscription",
        "invocation_id": "invocation_1234",
        "messages": [{"role": "user", "content": "hello"}],
    }
    values.update(overrides)
    return RunnerRequestV1(**values)


def test_protocol_rejects_api_target() -> None:
    with pytest.raises(RunnerProtocolError, match="subscription targets"):
        _request(target_id="openai_api")


def test_protocol_rejects_path_like_connection_reference() -> None:
    with pytest.raises(RunnerProtocolError, match="connection_ref"):
        _request(connection_ref="../auth.json")


def test_auth_start_mounts_only_scoped_credential_volume() -> None:
    config = _config()
    request = _request(action=RunnerAction.AUTH_START)

    command = build_cli_runner_docker_command(config, request, runner_id="1" * 32)

    assert (f"type=volume,src={config.credential_volume_prefix}{request.connection_ref},dst=/credentials") in command


def test_run_command_is_hardened_and_has_no_host_credentials() -> None:
    config = _config()
    request = _request(target_id="grok_subscription")

    command = build_cli_runner_docker_command(config, request, runner_id="2" * 32)
    joined = " ".join(command)

    assert "--read-only" in command
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert "no-new-privileges:true" in command
    assert config.docker_network in command
    assert "GROK_HOME=/credentials/grok" in command
    assert f"HTTPS_PROXY={config.egress_proxy_url}" in command
    assert "OPENAI_API_KEY" not in joined
    assert "GROK_API_KEY" not in joined
    assert "SSH_AUTH_SOCK" not in joined
    assert command[-1] == config.grok_runner_image


def test_config_requires_immutable_runner_image() -> None:
    config = RunnerManagerConfig(
        token="token",
        codex_runner_image="webterm-codex:latest",
        grok_runner_image="registry.example/webterm-grok@sha256:" + "b" * 64,
        docker_network="webterm-ai-cli-egress",
    )
    with pytest.raises(RuntimeError, match="CODEX_RUNNER_IMAGE"):
        config.validate_startup()


def test_config_requires_both_provider_images(monkeypatch) -> None:
    monkeypatch.setenv("AI_CLI_RUNNER_MANAGER_TOKEN", "token")
    monkeypatch.setenv("AI_CLI_CODEX_RUNNER_IMAGE", "registry.example/codex@sha256:" + "a" * 64)
    monkeypatch.delenv("AI_CLI_GROK_RUNNER_IMAGE", raising=False)
    config = RunnerManagerConfig.from_env()

    with pytest.raises(RuntimeError, match="GROK_RUNNER_IMAGE"):
        config.validate_startup()


@pytest.mark.asyncio
async def test_stderr_drain_is_bounded_and_consumes_the_pipe() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"secret-bearing stderr" * 100)
    reader.feed_eof()

    exceeded = await _drain_bounded(reader, limit=128)

    assert exceeded is True
    assert await reader.read() == b""


@pytest.mark.asyncio
async def test_revoke_stops_only_matching_runners_and_removes_exact_volume(monkeypatch) -> None:
    class FakeProcess:
        def __init__(self, return_code: int | None = None) -> None:
            self.returncode = return_code
            self.terminated = False
            self.killed = False

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> int:
            if self.returncode is None:
                self.returncode = 0
            return self.returncode

    volume_process = FakeProcess(0)
    calls: list[tuple[object, ...]] = []

    async def fake_create_subprocess_exec(*args, **_kwargs):
        calls.append(args)
        return volume_process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    runtime = DockerCliRuntime(_config())
    matching = FakeProcess()
    unrelated = FakeProcess()
    runtime._processes = {"run-a": matching, "run-b": unrelated}
    runtime._process_connections = {
        "run-a": "connection_1234",
        "run-b": "connection_9999",
    }

    assert await runtime.revoke_connection("connection_1234") is True
    assert matching.terminated is True
    assert unrelated.terminated is False
    assert calls == [
        (
            _config().docker_command,
            "volume",
            "rm",
            f"{_config().credential_volume_prefix}connection_1234",
        )
    ]


@pytest.mark.asyncio
async def test_stderr_flood_terminates_runner_immediately(monkeypatch) -> None:
    script = "import sys,time; sys.stderr.buffer.write(b'x'*200000); sys.stderr.flush(); time.sleep(30)"
    monkeypatch.setattr(
        "ai_cli_runner_manager.docker_runtime.build_cli_runner_docker_command",
        lambda _config, _request, **_kwargs: [sys.executable, "-c", script],
    )
    runtime = DockerCliRuntime(replace(_config(), output_limit_bytes=1024, request_timeout_seconds=10))

    started = time.monotonic()
    events = [event async for event in runtime.stream(_request())]

    assert time.monotonic() - started < 5
    assert events[-1].type is ProviderEventType.ERROR
    assert events[-1].payload["code"] == "provider_protocol_error"
    assert runtime._processes == {}


@pytest.mark.asyncio
async def test_oversized_non_newline_stdout_is_killed_and_translated(monkeypatch) -> None:
    script = "import sys,time; sys.stdout.buffer.write(b'x'*200000); sys.stdout.flush(); time.sleep(30)"
    monkeypatch.setattr(
        "ai_cli_runner_manager.docker_runtime.build_cli_runner_docker_command",
        lambda _config, _request, **_kwargs: [sys.executable, "-c", script],
    )
    runtime = DockerCliRuntime(replace(_config(), output_limit_bytes=1024, request_timeout_seconds=10))

    started = time.monotonic()
    events = [event async for event in runtime.stream(_request())]

    assert time.monotonic() - started < 5
    assert events[-1].type is ProviderEventType.ERROR
    assert events[-1].payload["code"] == "provider_protocol_error"
    assert runtime._processes == {}
