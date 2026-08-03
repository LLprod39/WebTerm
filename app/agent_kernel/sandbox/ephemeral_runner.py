"""Fail-closed runtime for isolated SSH command execution."""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncssh
from django.conf import settings

_IMMUTABLE_IMAGE = re.compile(r"^(?:[a-z0-9][a-z0-9._:/-]*@)?sha256:[0-9a-f]{64}$")
_RUNNER_ID = re.compile(r"^[0-9a-f]{32}$")
_RUNNER_INPUT_LIMIT = 1024 * 1024


class AgentCommandRuntimeError(RuntimeError):
    """The isolated command runner could not safely execute the request."""


@dataclass(frozen=True)
class AgentCommandResult:
    stdout: str
    stderr: str
    exit_status: int
    duration_ms: int
    runtime: str


def agent_command_uses_docker() -> bool:
    runtime = str(getattr(settings, "AGENT_COMMAND_RUNTIME", "docker") or "docker").strip().lower()
    if runtime in {"docker", "container", "containers"}:
        return True
    unsafe_test_mode = bool(getattr(settings, "AGENT_COMMAND_ALLOW_UNSAFE_HOST_RUNTIME_FOR_TESTS", False))
    if runtime == "host" and bool(getattr(settings, "TESTING", False)) and unsafe_test_mode:
        return False
    raise AgentCommandRuntimeError(
        "Agent commands require the isolated Docker runtime; host SSH execution is allowed only in tests."
    )


def agent_command_image_is_immutable(image: str) -> bool:
    return bool(_IMMUTABLE_IMAGE.fullmatch(str(image or "").strip()))


def _bind_mount(source: str | Path, target: str) -> str:
    resolved = Path(source).expanduser().resolve(strict=True)
    return f"type=bind,src={resolved},dst={target},readonly"


def build_agent_command_docker_command(*, ssh_agent_socket: str = "", runner_id: str = "") -> list[str]:
    image = str(getattr(settings, "AGENT_COMMAND_RUNNER_IMAGE", "") or "").strip()
    if not agent_command_image_is_immutable(image):
        raise AgentCommandRuntimeError(
            "AGENT_COMMAND_RUNNER_IMAGE must be an immutable sha256 image ID or repository@sha256 digest."
        )

    resolved_runner_id = runner_id or secrets.token_hex(16)
    if not _RUNNER_ID.fullmatch(resolved_runner_id):
        raise AgentCommandRuntimeError("Agent command runner id must be 32 lowercase hexadecimal characters.")
    command = [
        str(getattr(settings, "AGENT_COMMAND_DOCKER_COMMAND", "docker") or "docker"),
        "run",
        "--rm",
        "--interactive",
        "--pull",
        "never",
        "--name",
        f"webterm-agent-command-{resolved_runner_id}",
        "--user",
        "10001:10001",
        "--read-only",
        "--cgroupns",
        "private",
        "--network",
        str(getattr(settings, "AGENT_COMMAND_DOCKER_NETWORK", "bridge") or "bridge"),
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=32m",
        "--label",
        "webtrerm.runtime=agent-command",
    ]
    cpus = str(getattr(settings, "AGENT_COMMAND_DOCKER_CPUS", "0.5") or "").strip()
    memory = str(getattr(settings, "AGENT_COMMAND_DOCKER_MEMORY", "256m") or "").strip()
    pids_limit = int(getattr(settings, "AGENT_COMMAND_DOCKER_PIDS_LIMIT", 64) or 0)
    if cpus:
        command.extend(["--cpus", cpus])
    if memory:
        command.extend(["--memory", memory])
    if pids_limit > 0:
        command.extend(["--pids-limit", str(pids_limit)])
    if ssh_agent_socket:
        command.extend(["--mount", _bind_mount(ssh_agent_socket, "/run/ssh-agent.sock")])
    command.append(image)
    return command


def _bounded(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "\n...[truncated by WebTerm]"


async def _execute_on_host_for_tests(
    connect_kwargs: dict[str, Any],
    command: str,
    *,
    input_text: str | None,
    timeout_seconds: int,
    output_limit: int,
) -> AgentCommandResult:
    started = time.monotonic()
    async with asyncssh.connect(**connect_kwargs) as connection:
        run_kwargs: dict[str, Any] = {}
        if input_text is not None:
            run_kwargs["input"] = input_text
        result = await asyncio.wait_for(connection.run(command, **run_kwargs), timeout=timeout_seconds)
    return AgentCommandResult(
        stdout=_bounded(result.stdout, output_limit),
        stderr=_bounded(result.stderr, output_limit),
        exit_status=int(result.exit_status),
        duration_ms=int((time.monotonic() - started) * 1000),
        runtime="host-test",
    )


async def _resolve_private_key_text(private_key: str, key_path: str) -> str:
    resolved = str(private_key or "")
    if resolved or not key_path:
        return resolved
    try:
        return await asyncio.to_thread(Path(key_path).expanduser().read_text, encoding="utf-8")
    except OSError as exc:
        raise AgentCommandRuntimeError("Configured SSH private key cannot be read by the agent runner.") from exc


async def execute_ephemeral_ssh_command(
    *,
    connect_kwargs: dict[str, Any],
    command: str,
    known_hosts_text: str = "",
    key_path: str = "",
    private_key: str = "",
    input_text: str | None = None,
    timeout_seconds: int | None = None,
) -> AgentCommandResult:
    timeout = max(
        1,
        int(timeout_seconds or getattr(settings, "AGENT_COMMAND_TIMEOUT_SECONDS", 120) or 120),
    )
    output_limit = max(1024, int(getattr(settings, "AGENT_COMMAND_OUTPUT_MAX_CHARS", 100_000) or 100_000))
    if not agent_command_uses_docker():
        return await _execute_on_host_for_tests(
            connect_kwargs,
            command,
            input_text=input_text,
            timeout_seconds=timeout,
            output_limit=output_limit,
        )

    ssh_agent_socket = str(os.environ.get("SSH_AUTH_SOCK") or "").strip()
    if ssh_agent_socket and not Path(ssh_agent_socket).exists():
        ssh_agent_socket = ""
    resolved_private_key = await _resolve_private_key_text(private_key, key_path)
    docker_command = build_agent_command_docker_command(ssh_agent_socket=ssh_agent_socket)
    payload = {
        "schema": "webterm.agent-command.v1",
        "host": str(connect_kwargs.get("host") or ""),
        "port": int(connect_kwargs.get("port") or 22),
        "username": str(connect_kwargs.get("username") or ""),
        "password": str(connect_kwargs.get("password") or ""),
        "passphrase": str(connect_kwargs.get("passphrase") or ""),
        "private_key": resolved_private_key,
        "known_hosts": known_hosts_text,
        "tunnel": str(connect_kwargs.get("tunnel") or ""),
        "agent_forwarded": bool(ssh_agent_socket),
        "command": str(command),
        "input": input_text,
        "connect_timeout": int(connect_kwargs.get("connect_timeout") or 10),
        "login_timeout": int(connect_kwargs.get("login_timeout") or 20),
        "command_timeout": timeout,
        "output_limit": output_limit,
    }
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(encoded) > _RUNNER_INPUT_LIMIT:
        raise AgentCommandRuntimeError("Agent command runner request exceeds the 1 MiB input limit.")

    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *docker_command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(encoded), timeout=timeout + 15)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise AgentCommandRuntimeError(f"Ephemeral agent command runner timed out after {timeout}s.") from exc
    if process.returncode != 0:
        detail = _bounded(stderr.decode("utf-8", errors="replace"), 2000)
        if not detail:
            try:
                error_payload = json.loads(stdout.decode("utf-8"))
                detail = _bounded(error_payload.get("error"), 2000) if isinstance(error_payload, dict) else ""
            except (UnicodeDecodeError, json.JSONDecodeError):
                detail = ""
        raise AgentCommandRuntimeError(f"Ephemeral agent command runner failed: {detail or process.returncode}")
    try:
        result = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgentCommandRuntimeError("Ephemeral agent command runner returned an invalid response.") from exc
    if not isinstance(result, dict) or result.get("schema") != "webterm.agent-command-result.v1":
        raise AgentCommandRuntimeError("Ephemeral agent command runner returned an unsupported response.")
    return AgentCommandResult(
        stdout=_bounded(result.get("stdout"), output_limit),
        stderr=_bounded(result.get("stderr"), output_limit),
        exit_status=int(result.get("exit_status", -1)),
        duration_ms=int(result.get("duration_ms") or int((time.monotonic() - started) * 1000)),
        runtime="docker",
    )
