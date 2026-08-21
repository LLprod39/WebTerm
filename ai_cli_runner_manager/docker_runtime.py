"""Hardened ephemeral provider-container lifecycle."""

from __future__ import annotations

import asyncio
import json
import re
import secrets
from collections.abc import AsyncGenerator
from typing import Any

from app.ai_runtime import ProviderEventType, ProviderEventV1

from .config import RunnerManagerConfig
from .protocol import RunnerProtocolError, RunnerRequestV1, error_event

_RUNNER_ID = re.compile(r"^[0-9a-f]{32}$")
_CONNECTION_REF = re.compile(r"^[a-z0-9][a-z0-9_-]{7,79}$")
_INPUT_LIMIT = 1024 * 1024


class CliRunnerRuntimeError(RuntimeError):
    pass


def build_cli_runner_docker_command(
    config: RunnerManagerConfig,
    request: RunnerRequestV1,
    *,
    runner_id: str = "",
) -> list[str]:
    resolved_runner_id = runner_id or secrets.token_hex(16)
    if not _RUNNER_ID.fullmatch(resolved_runner_id):
        raise CliRunnerRuntimeError("Runner id must contain 32 lowercase hexadecimal characters")
    credential_volume = f"{config.credential_volume_prefix}{request.connection_ref}"
    target_home = "/credentials/codex" if request.target_id == "codex_subscription" else "/credentials/grok"
    home_env = "CODEX_HOME" if request.target_id == "codex_subscription" else "GROK_HOME"
    command = [
        config.docker_command,
        "run",
        "--rm",
        "--interactive",
        "--pull",
        "never",
        "--name",
        f"webterm-ai-cli-{resolved_runner_id}",
        "--user",
        "10001:10001",
        "--read-only",
        "--cgroupns",
        "private",
        "--network",
        config.docker_network,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m",
        "--tmpfs",
        "/workspace:rw,noexec,nosuid,nodev,size=64m",
        "--mount",
        f"type=volume,src={credential_volume},dst=/credentials",
        "--env",
        f"{home_env}={target_home}",
        "--env",
        f"WEBTERM_AI_CLI_TARGET={request.target_id}",
        "--env",
        f"HTTP_PROXY={config.egress_proxy_url}",
        "--env",
        f"HTTPS_PROXY={config.egress_proxy_url}",
        "--label",
        "webtrerm.runtime=ai-cli",
        "--label",
        f"webtrerm.invocation={request.invocation_id}",
        "--label",
        f"webtrerm.connection={request.connection_ref}",
        "--cpus",
        config.cpus,
        "--memory",
        config.memory,
        "--pids-limit",
        str(config.pids_limit),
        config.runner_image_for(request.target_id),
    ]
    return command


class DockerCliRuntime:
    def __init__(self, config: RunnerManagerConfig) -> None:
        self.config = config
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._process_connections: dict[str, str] = {}
        self._runner_names: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def stream(self, request: RunnerRequestV1) -> AsyncGenerator[ProviderEventV1, None]:
        runner_id = secrets.token_hex(16)
        runner_name = f"webterm-ai-cli-{runner_id}"
        command = build_cli_runner_docker_command(self.config, request, runner_id=runner_id)
        encoded = json.dumps(request.to_dict(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > _INPUT_LIMIT:
            yield error_event("provider_request_too_large", "CLI runner request exceeds 1 MiB")
            return
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        async with self._lock:
            if request.invocation_id in self._processes:
                await _stop_process(process, drain_stderr=True)
                yield error_event("provider_invocation_conflict", "Invocation is already running")
                return
            self._processes[request.invocation_id] = process
            self._process_connections[request.invocation_id] = request.connection_ref
            self._runner_names[request.invocation_id] = runner_name
        total_output = 0
        stderr_task: asyncio.Task[bool] | None = None
        stderr_exceeded = asyncio.Event()
        try:
            assert process.stdin is not None
            assert process.stdout is not None
            assert process.stderr is not None
            stderr_task = asyncio.create_task(
                _drain_bounded(
                    process.stderr,
                    limit=self.config.output_limit_bytes,
                    exceeded_event=stderr_exceeded,
                )
            )
            process.stdin.write(encoded + b"\n")
            await process.stdin.drain()
            process.stdin.close()
            while True:
                line = await _await_or_stderr_limit(
                    process.stdout.readline(),
                    stderr_exceeded=stderr_exceeded,
                    timeout=self.config.request_timeout_seconds,
                )
                if not line:
                    break
                total_output += len(line)
                if total_output > self.config.output_limit_bytes:
                    raise CliRunnerRuntimeError("CLI runner output limit exceeded")
                yield _parse_event(line)
            return_code = await _await_or_stderr_limit(
                process.wait(),
                stderr_exceeded=stderr_exceeded,
                timeout=15,
            )
            stderr_exceeded = await stderr_task
            stderr_task = None
            if stderr_exceeded:
                yield error_event("provider_protocol_error", "CLI runner stderr output limit exceeded")
                return
            if return_code != 0:
                yield error_event("provider_runner_failed", "CLI runner exited unsuccessfully")
        except TimeoutError:
            await _stop_process(process, drain_stderr=stderr_task is None)
            yield error_event("provider_timeout", "CLI runner timed out", retryable=True)
        except asyncio.CancelledError:
            if process.returncode is None:
                await _stop_process(
                    process,
                    graceful=True,
                    drain_stderr=stderr_task is None,
                )
            raise
        except (CliRunnerRuntimeError, RunnerProtocolError, ValueError, asyncio.LimitOverrunError):
            if process.returncode is None:
                await _stop_process(process, drain_stderr=stderr_task is None)
            yield error_event("provider_protocol_error", "CLI runner returned an invalid or oversized event")
        finally:
            if stderr_task is not None:
                stderr_task.cancel()
                await asyncio.gather(stderr_task, return_exceptions=True)
            if process.returncode is None:
                await _stop_process(process, drain_stderr=True)
            await self._remove_runner_container(runner_name)
            async with self._lock:
                self._processes.pop(request.invocation_id, None)
                self._process_connections.pop(request.invocation_id, None)
                self._runner_names.pop(request.invocation_id, None)

    async def cancel(self, invocation_id: str) -> bool:
        async with self._lock:
            process = self._processes.get(invocation_id)
            runner_name = self._runner_names.get(invocation_id)
        if process is None or process.returncode is not None:
            return False
        if runner_name:
            await self._remove_runner_container(runner_name)
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()
        return True

    async def revoke_connection(self, connection_ref: str) -> bool:
        normalized = connection_ref.strip().lower()
        if not _CONNECTION_REF.fullmatch(normalized):
            raise CliRunnerRuntimeError("Connection reference has an invalid format")
        async with self._lock:
            processes = [
                (process, self._runner_names.get(invocation_id))
                for invocation_id, process in self._processes.items()
                if self._process_connections.get(invocation_id) == normalized and process.returncode is None
            ]
        for process, runner_name in processes:
            if runner_name:
                await self._remove_runner_container(runner_name)
            process.terminate()
        for process, _runner_name in processes:
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()

        volume_name = f"{self.config.credential_volume_prefix}{normalized}"
        process = await asyncio.create_subprocess_exec(
            self.config.docker_command,
            "volume",
            "rm",
            volume_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            return await asyncio.wait_for(process.wait(), timeout=15) == 0
        except TimeoutError:
            process.kill()
            await process.wait()
            return False

    async def _remove_runner_container(self, runner_name: str) -> bool:
        if _RUNNER_ID.fullmatch(runner_name.removeprefix("webterm-ai-cli-")) is None:
            return False
        process = await asyncio.create_subprocess_exec(
            self.config.docker_command,
            "rm",
            "--force",
            runner_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            return await asyncio.wait_for(process.wait(), timeout=15) == 0
        except TimeoutError:
            process.kill()
            await process.wait()
            return False


def _parse_event(line: bytes) -> ProviderEventV1:
    try:
        payload: Any = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerProtocolError("Invalid provider event JSON") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise RunnerProtocolError("Unsupported provider event")
    event_payload = payload.get("payload")
    if not isinstance(event_payload, dict):
        raise RunnerProtocolError("Provider event payload must be an object")
    return ProviderEventV1(ProviderEventType(payload.get("type")), event_payload)


async def _drain_bounded(
    stream: asyncio.StreamReader,
    *,
    limit: int,
    exceeded_event: asyncio.Event | None = None,
) -> bool:
    """Drain a subprocess pipe concurrently without retaining secret-bearing stderr."""
    total = 0
    exceeded = False
    while chunk := await stream.read(64 * 1024):
        total += len(chunk)
        if total > limit:
            exceeded = True
            if exceeded_event is not None:
                exceeded_event.set()
    return exceeded


async def _await_or_stderr_limit(
    awaitable,
    *,
    stderr_exceeded: asyncio.Event,
    timeout: float,
):
    """Wait for runner progress while making stderr overflow an immediate fence."""
    operation = asyncio.create_task(awaitable)
    overflow = asyncio.create_task(stderr_exceeded.wait())
    try:
        done, _pending = await asyncio.wait(
            {operation, overflow},
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if overflow in done and overflow.result():
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            raise CliRunnerRuntimeError("CLI runner stderr output limit exceeded")
        if operation not in done:
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            raise TimeoutError
        return operation.result()
    finally:
        overflow.cancel()
        await asyncio.gather(overflow, return_exceptions=True)


async def _stop_process(
    process: asyncio.subprocess.Process,
    *,
    graceful: bool = False,
    drain_stderr: bool = False,
) -> None:
    """Stop a child while draining pipes so `wait()` cannot deadlock on full buffers."""
    drainers: list[asyncio.Task[bytes]] = []
    if process.stdout is not None:
        drainers.append(asyncio.create_task(process.stdout.read()))
    if drain_stderr and process.stderr is not None:
        drainers.append(asyncio.create_task(process.stderr.read()))
    if process.returncode is None:
        (process.terminate if graceful else process.kill)()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        if process.returncode is None:
            process.kill()
        await asyncio.wait_for(process.wait(), timeout=5)
    finally:
        if drainers:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*drainers, return_exceptions=True),
                    timeout=5,
                )
            except TimeoutError:
                for drainer in drainers:
                    drainer.cancel()
                await asyncio.gather(*drainers, return_exceptions=True)
