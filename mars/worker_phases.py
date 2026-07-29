from __future__ import annotations

import asyncio
import contextlib
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone

from mars.models import MarsRun
from mars.services import (
    build_mars_agent_docker_command,
    cli_path_for_command,
    docker_container_child_path,
    docker_workspace_path,
    record_event,
    subprocess_env_for_cli,
)
from mars.verification import verification_command


def _command_prefix(value: Any, default: str) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    raw = str(value or default).strip()
    return [raw] if raw else [default]


def _run_dir(run_id: int) -> Path:
    path = Path(settings.MEDIA_ROOT) / "mars_runs" / str(run_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _codex_prefix(role: str, docker_runtime: bool) -> list[str]:
    role_name = role.upper()
    if docker_runtime:
        configured = getattr(settings, f"MARS_AGENT_DOCKER_CODEX_{role_name}_COMMAND", None)
        configured = configured or getattr(settings, "MARS_AGENT_DOCKER_CODEX_COMMAND", "codex")
    else:
        configured = getattr(settings, f"MARS_CODEX_{role_name}_COMMAND", None)
        configured = configured or getattr(settings, "MARS_CODEX_COMMAND", None)
    return _command_prefix(configured, "codex")


def _gemini_prefix(role: str, docker_runtime: bool) -> list[str]:
    role_name = role.upper()
    if docker_runtime:
        configured = getattr(settings, f"MARS_AGENT_DOCKER_GEMINI_{role_name}_COMMAND", None)
        configured = configured or getattr(settings, "MARS_AGENT_DOCKER_GEMINI_COMMAND", "gemini")
    else:
        configured = getattr(settings, f"MARS_GEMINI_{role_name}_COMMAND", None)
        configured = configured or getattr(settings, "MARS_GEMINI_COMMAND", None)
    return _command_prefix(configured, "gemini")


def _codex_timeout(role: str) -> int:
    role_name = role.upper()
    return int(
        getattr(settings, f"MARS_CODEX_{role_name}_TIMEOUT_SECONDS", None)
        or getattr(settings, "MARS_CODEX_TIMEOUT_SECONDS", 1800)
    )


def _gemini_timeout(role: str) -> int:
    role_name = role.upper()
    return int(
        getattr(settings, f"MARS_GEMINI_{role_name}_TIMEOUT_SECONDS", None)
        or getattr(settings, "MARS_GEMINI_TIMEOUT_SECONDS", 900)
    )


async def _save_instance(instance, update_fields: list[str]) -> None:
    await sync_to_async(instance.save, thread_sensitive=True)(update_fields=update_fields)


async def _stop_requested(run_id: int) -> bool:
    run = await sync_to_async(lambda: MarsRun.objects.filter(pk=run_id).only("runtime_control", "status").first())()
    if run is None:
        return True
    if run.status == MarsRun.STATUS_STOPPED:
        return True
    return bool((run.runtime_control or {}).get("stop_requested"))


def _stop_requested_sync(run_id: int) -> bool:
    run = MarsRun.objects.filter(pk=run_id).only("runtime_control", "status").first()
    if run is None:
        return True
    if run.status == MarsRun.STATUS_STOPPED:
        return True
    return bool((run.runtime_control or {}).get("stop_requested"))


def _record_stream_line(run: MarsRun, event_prefix: str, stream_name: str, text: str) -> None:
    payload: dict[str, Any] = {"stream": stream_name, "text": text[:4000]}
    with contextlib.suppress(json.JSONDecodeError):
        payload["json"] = json.loads(text)
    record_event(run, f"{event_prefix}_{stream_name}", text[:1000], payload)


def _stream_process_threaded(
    run: MarsRun,
    *,
    command: list[str],
    cwd: str,
    stdin_text: str,
    event_prefix: str,
    timeout_seconds: int,
    env: dict[str, str] | None,
) -> tuple[int, str]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE if stdin_text else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    if stdin_text and process.stdin is not None:
        process.stdin.write(stdin_text)
        process.stdin.close()

    output_chunks: list[str] = []
    stop_event = threading.Event()

    def read_stream(stream, stream_name: str) -> None:
        if stream is None:
            return
        for raw_line in iter(stream.readline, ""):
            text = raw_line.rstrip()
            output_chunks.append(text)
            _record_stream_line(run, event_prefix, stream_name, text)
            if _stop_requested_sync(run.id) and not stop_event.is_set():
                stop_event.set()
                with contextlib.suppress(Exception):
                    process.terminate()
                record_event(run, "mars_run_stop_requested", "Stop requested")
                break

    stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, "stdout"), daemon=True)
    stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, "stderr"), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    while process.poll() is None:
        if time.monotonic() >= deadline:
            timed_out = True
            with contextlib.suppress(Exception):
                process.kill()
            break
        time.sleep(0.05)

    if timed_out:
        record_event(run, f"{event_prefix}_timeout", f"{event_prefix} timed out")

    with contextlib.suppress(Exception):
        process.wait(timeout=2)
    stdout_thread.join(timeout=2)
    stderr_thread.join(timeout=2)

    exit_code = int(process.returncode or 0)
    record_event(run, f"{event_prefix}_finished", f"{event_prefix} exited {exit_code}", {"exit_code": exit_code})
    return exit_code, "\n".join(output_chunks)[-120_000:]


async def _stream_process(
    run: MarsRun,
    *,
    command: list[str],
    cwd: str,
    stdin_text: str = "",
    event_prefix: str,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    await sync_to_async(record_event)(run, f"{event_prefix}_started", f"Starting {event_prefix}", {"command": command})
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE if stdin_text else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except NotImplementedError:
        return await asyncio.to_thread(
            _stream_process_threaded,
            run,
            command=command,
            cwd=cwd,
            stdin_text=stdin_text,
            event_prefix=event_prefix,
            timeout_seconds=timeout_seconds,
            env=env,
        )
    if stdin_text and process.stdin:
        process.stdin.write(stdin_text.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

    output_chunks: list[str] = []

    async def read_stream(stream: asyncio.StreamReader | None, stream_name: str) -> None:
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            output_chunks.append(text)
            payload: dict[str, Any] = {"stream": stream_name, "text": text[:4000]}
            with contextlib.suppress(json.JSONDecodeError):
                payload["json"] = json.loads(text)
            await sync_to_async(record_event)(run, f"{event_prefix}_{stream_name}", text[:1000], payload)
            if await _stop_requested(run.id):
                process.terminate()
                await sync_to_async(record_event)(run, "mars_run_stop_requested", "Stop requested")
                break

    stdout_task = asyncio.create_task(read_stream(process.stdout, "stdout"))
    stderr_task = asyncio.create_task(read_stream(process.stderr, "stderr"))
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
    except TimeoutError:
        process.kill()
        await sync_to_async(record_event)(run, f"{event_prefix}_timeout", f"{event_prefix} timed out")
        await process.wait()
    finally:
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

    exit_code = int(process.returncode or 0)
    await sync_to_async(record_event)(
        run, f"{event_prefix}_finished", f"{event_prefix} exited {exit_code}", {"exit_code": exit_code}
    )
    return exit_code, "\n".join(output_chunks)[-120_000:]


async def _run_codex_phase(
    run: MarsRun,
    *,
    role: str,
    prompt: str,
    event_prefix: str,
    output_path: Path,
    workspace_root: Path,
    run_dir: Path,
    docker_runtime: bool,
) -> tuple[int, str, str]:
    codex_prefix = _codex_prefix(role, docker_runtime)
    codex_output_path = (
        docker_container_child_path("/mars-run", run_dir, output_path)
        if docker_runtime
        else cli_path_for_command(codex_prefix, output_path)
    )
    codex_inner_cmd = codex_prefix + [
        "--ask-for-approval",
        "never",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--json",
        "--cd",
        docker_workspace_path() if docker_runtime else cli_path_for_command(codex_prefix, workspace_root),
        "--sandbox",
        "workspace-write",
        "--output-last-message",
        codex_output_path,
        "-",
    ]
    codex_cmd = (
        build_mars_agent_docker_command(
            phase=f"{event_prefix}-{run.id}",
            workspace_root=workspace_root,
            workspace_mode="rw",
            inner_command=codex_inner_cmd,
            extra_mounts=[(run_dir, "/mars-run", "rw")],
            include_codex_home=True,
            allow_network=True,
            include_provider_credentials=True,
        )
        if docker_runtime
        else codex_inner_cmd
    )
    exit_code, output = await _stream_process(
        run,
        command=codex_cmd,
        cwd=str(workspace_root),
        stdin_text=prompt,
        event_prefix=event_prefix,
        timeout_seconds=_codex_timeout(role),
        env=None if docker_runtime else subprocess_env_for_cli(codex_prefix),
    )
    final_text = output_path.read_text(encoding="utf-8", errors="replace") if output_path.exists() else output[-12000:]
    return exit_code, output, final_text


async def _run_gemini_phase(
    run: MarsRun,
    *,
    role: str,
    prompt: str,
    event_prefix: str,
    workspace_root: Path,
    docker_runtime: bool,
) -> tuple[int, str]:
    gemini_prefix = _gemini_prefix(role, docker_runtime)
    gemini_inner_cmd = gemini_prefix + [
        "--prompt",
        prompt,
        "--approval-mode",
        "plan",
        "--output-format",
        "stream-json",
        "--include-directories",
        docker_workspace_path() if docker_runtime else cli_path_for_command(gemini_prefix, workspace_root),
    ]
    gemini_cmd = (
        build_mars_agent_docker_command(
            phase=f"{event_prefix}-{run.id}",
            workspace_root=workspace_root,
            workspace_mode="ro",
            inner_command=gemini_inner_cmd,
            include_gemini_home=True,
            allow_network=True,
            include_provider_credentials=True,
        )
        if docker_runtime
        else gemini_inner_cmd
    )
    return await _stream_process(
        run,
        command=gemini_cmd,
        cwd=str(workspace_root),
        event_prefix=event_prefix,
        timeout_seconds=_gemini_timeout(role),
    )


async def _safe_gemini_phase(
    run: MarsRun,
    *,
    role: str,
    prompt: str,
    event_prefix: str,
    workspace_root: Path,
    docker_runtime: bool,
    required: bool = False,
) -> tuple[int, str]:
    try:
        return await _run_gemini_phase(
            run,
            role=role,
            prompt=prompt,
            event_prefix=event_prefix,
            workspace_root=workspace_root,
            docker_runtime=docker_runtime,
        )
    except Exception as exc:
        await sync_to_async(record_event)(
            run,
            f"{event_prefix}_failed",
            f"{role} phase failed: {exc}",
            {"error": str(exc)},
        )
        if required:
            raise
        return -1, ""


async def _run_verification(
    run: MarsRun,
    *,
    workspace_root: Path,
    docker_runtime: bool,
    verification_profile: str,
    event_prefix: str,
) -> tuple[int | None, str]:
    test_parts = verification_command(verification_profile)
    if not test_parts:
        await sync_to_async(record_event)(run, "tests_skipped", "No verification command configured")
        return None, ""

    test_cmd = (
        build_mars_agent_docker_command(
            phase=f"{event_prefix}-{run.id}",
            workspace_root=workspace_root,
            workspace_mode="rw",
            inner_command=test_parts,
        )
        if docker_runtime
        else test_parts
    )
    test_exit, test_output = await _stream_process(
        run,
        command=test_cmd,
        cwd=str(workspace_root),
        event_prefix=event_prefix,
        timeout_seconds=int(getattr(settings, "MARS_TEST_TIMEOUT_SECONDS", 900)),
    )
    if test_exit != 0:
        await sync_to_async(record_event)(
            run, f"{event_prefix}_failed", "Configured verification failed", {"exit_code": test_exit}
        )
    else:
        await sync_to_async(record_event)(run, f"{event_prefix}_passed", "Configured verification passed")
    return test_exit, test_output


def _test_history_entry(label: str, exit_code: int | None, output: str) -> str:
    if exit_code is None:
        return f"## {label}\nNo verification command configured."
    return f"## {label}\nexit_code={exit_code}\n{output}".strip()


async def _check_stop_and_finish(run: MarsRun) -> bool:
    if not await _stop_requested(run.id):
        return False
    run.status = MarsRun.STATUS_STOPPED
    run.completed_at = timezone.now()
    await _save_instance(run, ["status", "completed_at"])
    return True
