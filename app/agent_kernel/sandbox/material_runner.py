"""Docker-only, fail-closed runtime for uploaded shell material."""

from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
from dataclasses import dataclass

from django.conf import settings

_IMMUTABLE_IMAGE = re.compile(r"^(?:[a-z0-9][a-z0-9._:/-]*@)?sha256:[0-9a-f]{64}$")
_RUNNER_ID = re.compile(r"^[0-9a-f]{32}$")


class MaterialRunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class MaterialRunResult:
    stdout: str
    stderr: str
    exit_status: int
    duration_ms: int
    runtime: str = "docker"


def material_runner_image_is_immutable(image: str) -> bool:
    return bool(_IMMUTABLE_IMAGE.fullmatch(str(image or "").strip()))


def build_material_runner_docker_command(*, runner_id: str = "") -> list[str]:
    if not bool(getattr(settings, "AGENT_MATERIAL_RUNNER_ENABLED", False)):
        raise MaterialRunnerError("Isolated material runner is disabled.")
    image = str(getattr(settings, "AGENT_MATERIAL_RUNNER_IMAGE", "") or "").strip()
    if not material_runner_image_is_immutable(image):
        raise MaterialRunnerError("AGENT_MATERIAL_RUNNER_IMAGE must be pinned by immutable sha256 digest.")
    resolved_id = runner_id or secrets.token_hex(16)
    if not _RUNNER_ID.fullmatch(resolved_id):
        raise MaterialRunnerError("Invalid material runner id.")
    network = str(getattr(settings, "AGENT_MATERIAL_RUNNER_DOCKER_NETWORK", "bridge") or "bridge").strip()
    if network == "host" or network.startswith("container:"):
        raise MaterialRunnerError("Material runner cannot use host or container network mode.")
    return [
        str(getattr(settings, "AGENT_MATERIAL_RUNNER_DOCKER_COMMAND", "docker") or "docker"),
        "run", "--rm", "--interactive", "--pull", "never",
        "--name", f"webterm-material-{resolved_id}",
        "--network", network, "--user", "10001:10001", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
        "--pids-limit", str(max(8, int(getattr(settings, "AGENT_MATERIAL_RUNNER_PIDS_LIMIT", 32) or 32))),
        "--cpus", str(getattr(settings, "AGENT_MATERIAL_RUNNER_CPUS", "0.25") or "0.25"),
        "--memory", str(getattr(settings, "AGENT_MATERIAL_RUNNER_MEMORY", "128m") or "128m"),
        "--tmpfs", "/work:rw,exec,nosuid,nodev,size=16m,uid=10001,gid=10001,mode=700",
        "--env", "HOME=/work", "--env", "TMPDIR=/work",
        image,
    ]


async def execute_isolated_material(*, content: str, args: list[str], timeout_seconds: int = 120, language: str = "bash") -> MaterialRunResult:
    if language not in {"bash", "shell", "sh"}:
        raise MaterialRunnerError(f"Unsupported material language: {language}.")
    encoded = json.dumps({
        "schema": "webterm.material-run.v1", "language": language,
        "content": content, "args": args,
        "timeout_seconds": max(1, min(int(timeout_seconds), 300)),
        "output_limit": max(1024, min(int(getattr(settings, "AGENT_MATERIAL_RUNNER_OUTPUT_MAX_CHARS", 50_000) or 50_000), 200_000)),
    }, ensure_ascii=False).encode("utf-8")
    input_limit = max(1024, min(int(getattr(settings, "AGENT_MATERIAL_RUNNER_INPUT_MAX_BYTES", 64_000) or 64_000), 1_048_576))
    if len(encoded) > input_limit:
        raise MaterialRunnerError("Material runner request exceeds the configured input limit.")
    command = build_material_runner_docker_command()
    started = time.monotonic()
    try:
        process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except OSError as exc:
        raise MaterialRunnerError("Docker material runner is unavailable.") from exc
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(encoded), timeout=max(1, min(int(timeout_seconds), 300)) + 10)
    except TimeoutError as exc:
        process.kill(); await process.wait()
        raise MaterialRunnerError("Isolated material runner timed out.") from exc
    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace")[:2000]
        raise MaterialRunnerError(f"Isolated material runner failed: {detail or process.returncode}")
    try:
        payload = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MaterialRunnerError("Isolated material runner returned invalid output.") from exc
    if not isinstance(payload, dict) or payload.get("schema") != "webterm.material-result.v1":
        raise MaterialRunnerError("Isolated material runner returned an unsupported response.")
    return MaterialRunResult(str(payload.get("stdout") or ""), str(payload.get("stderr") or ""), int(payload.get("exit_status", -1)), int(payload.get("duration_ms") or ((time.monotonic() - started) * 1000)))
