"""Single-shot SSH client for the WebTrerm agent command container."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import asyncssh

INPUT_LIMIT = 1024 * 1024


def _bounded(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "\n...[truncated by runner]"


async def _run(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    known_hosts = str(payload.get("known_hosts") or "")
    if not known_hosts:
        raise RuntimeError("Trusted SSH host keys are required.")
    known_hosts_path = Path("/tmp/known_hosts")
    known_hosts_path.write_text(known_hosts, encoding="utf-8")

    kwargs: dict[str, Any] = {
        "host": str(payload.get("host") or ""),
        "port": int(payload.get("port") or 22),
        "username": str(payload.get("username") or ""),
        "known_hosts": str(known_hosts_path),
        "connect_timeout": max(1, int(payload.get("connect_timeout") or 10)),
        "login_timeout": max(1, int(payload.get("login_timeout") or 20)),
    }
    if payload.get("password"):
        kwargs["password"] = str(payload["password"])
    private_key = str(payload.get("private_key") or "")
    if private_key:
        kwargs["client_keys"] = [
            asyncssh.import_private_key(private_key, passphrase=str(payload.get("passphrase") or "") or None)
        ]
    if payload.get("agent_forwarded"):
        kwargs["agent_path"] = "/run/ssh-agent.sock"
    if payload.get("tunnel"):
        kwargs["tunnel"] = str(payload["tunnel"])

    command_timeout = max(1, int(payload.get("command_timeout") or 120))
    run_kwargs: dict[str, Any] = {"check": False}
    if payload.get("input") is not None:
        run_kwargs["input"] = str(payload["input"])
    async with asyncssh.connect(**kwargs) as connection:
        result = await asyncio.wait_for(
            connection.run(str(payload.get("command") or ""), **run_kwargs),
            timeout=command_timeout,
        )
    output_limit = max(1024, int(payload.get("output_limit") or 100_000))
    return {
        "schema": "webterm.agent-command-result.v1",
        "stdout": _bounded(result.stdout, output_limit),
        "stderr": _bounded(result.stderr, output_limit),
        "exit_status": int(result.exit_status),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def main() -> int:
    raw = sys.stdin.buffer.read(INPUT_LIMIT + 1)
    if len(raw) > INPUT_LIMIT:
        print(json.dumps({"error": "input_limit_exceeded"}))
        return 2
    try:
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != "webterm.agent-command.v1":
            raise ValueError("unsupported request schema")
        response = asyncio.run(_run(payload))
    except Exception as exc:  # noqa: BLE001 - isolated process boundary
        print(json.dumps({"error": str(exc)[:2000]}))
        return 1
    print(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
