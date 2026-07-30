"""Session manager: one long-lived stdio MCP process per session key.

A session is spawned on first use, initialized once (MCP handshake), then reused
for every subsequent tools/list and tools/call. Idle sessions are reaped after a
TTL and the least-recently-used session is evicted when the pool is full.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from mcp_runner.config import RunnerConfig

logger = logging.getLogger(__name__)

SUPPORTED_PROTOCOL_VERSION = "2025-06-18"


class RunnerError(RuntimeError):
    """A recoverable error while talking to an MCP session."""


def _json_rpc(method: str, params: dict[str, Any] | None = None, *, request_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        payload["id"] = request_id
    if params is not None:
        payload["params"] = params
    return payload


def _unwrap_result(message: dict[str, Any], request_id: str) -> dict[str, Any]:
    if message.get("id") != request_id:
        raise RunnerError("MCP server returned a mismatched response id")
    if "error" in message:
        error = message.get("error") or {}
        message_text = error.get("message") if isinstance(error, dict) else str(error)
        raise RunnerError(str(message_text or "MCP server returned an error"))
    result = message.get("result")
    if not isinstance(result, dict):
        raise RunnerError("MCP server returned an invalid result payload")
    return result


@dataclass
class _Session:
    key: str
    fingerprint: str
    proc: asyncio.subprocess.Process
    server_info: dict[str, Any]
    capabilities: dict[str, Any]
    protocol_version: str
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used: float = field(default_factory=time.monotonic)

    @property
    def alive(self) -> bool:
        return self.proc.returncode is None


def spec_fingerprint(spec: dict[str, Any]) -> str:
    """Identity of a spawn spec — changing command/args/env spawns a fresh process."""
    return json.dumps(
        {
            "command": spec.get("command") or "",
            "args": list(spec.get("args") or []),
            "env": {str(k): str(v) for k, v in (spec.get("env") or {}).items()},
        },
        sort_keys=True,
        ensure_ascii=False,
    )


class SessionManager:
    def __init__(self, config: RunnerConfig) -> None:
        self.config = config
        self._sessions: dict[str, _Session] = {}
        self._registry_lock = asyncio.Lock()

    async def rpc(
        self,
        session_key: str,
        spec: dict[str, Any],
        method: str,
        params: dict[str, Any] | None = None,
        *,
        notify: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any] | None:
        session = await self._get_or_create(session_key, spec)
        async with session.lock:
            if not session.alive:
                # Died between acquisition and use — rebuild once.
                await self._discard(session_key, session)
                session = await self._get_or_create(session_key, spec)
        async with session.lock:
            session.last_used = time.monotonic()
            if method == "initialize":
                return {
                    "protocolVersion": session.protocol_version,
                    "serverInfo": session.server_info,
                    "capabilities": session.capabilities,
                }
            if notify:
                await self._notify(session, method, params)
                return None
            return await self._request(session, method, params, timeout=timeout)

    async def _get_or_create(self, session_key: str, spec: dict[str, Any]) -> _Session:
        fingerprint = spec_fingerprint(spec)
        async with self._registry_lock:
            existing = self._sessions.get(session_key)
            if existing is not None and existing.alive and existing.fingerprint == fingerprint:
                return existing
            if existing is not None:
                await self._terminate(existing)
                self._sessions.pop(session_key, None)
            await self._evict_if_full()
            session = await self._spawn(session_key, spec, fingerprint)
            self._sessions[session_key] = session
            return session

    async def _evict_if_full(self) -> None:
        while len(self._sessions) >= self.config.max_sessions and self._sessions:
            victim_key = min(self._sessions, key=lambda key: self._sessions[key].last_used)
            victim = self._sessions.pop(victim_key)
            await self._terminate(victim)

    async def _spawn(self, session_key: str, spec: dict[str, Any], fingerprint: str) -> _Session:
        command = str(spec.get("command") or "").strip()
        if not command:
            raise RunnerError("MCP command is required")
        env = self.config.build_child_env(spec.get("env"))
        try:
            proc = await asyncio.create_subprocess_exec(
                command,
                *(str(arg) for arg in (spec.get("args") or [])),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            raise RunnerError(f"MCP command not found: {command}") from exc
        session = _Session(
            key=session_key,
            fingerprint=fingerprint,
            proc=proc,
            server_info={},
            capabilities={},
            protocol_version=SUPPORTED_PROTOCOL_VERSION,
        )
        try:
            await self._initialize(session)
        except BaseException:
            await self._terminate(session)
            raise
        return session

    async def _initialize(self, session: _Session) -> None:
        result = await self._request(
            session,
            "initialize",
            {
                "protocolVersion": SUPPORTED_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "WebTerm MCP Runner", "version": "1.0"},
            },
            timeout=self.config.initialize_timeout_seconds,
            allow_initialize=True,
        )
        session.server_info = result.get("serverInfo") or {}
        session.capabilities = result.get("capabilities") or {}
        session.protocol_version = str(result.get("protocolVersion") or SUPPORTED_PROTOCOL_VERSION)
        await self._notify(session, "notifications/initialized")

    async def _request(
        self,
        session: _Session,
        method: str,
        params: dict[str, Any] | None,
        *,
        timeout: float | None = None,
        allow_initialize: bool = False,
    ) -> dict[str, Any]:
        proc = session.proc
        if not proc.stdin or not proc.stdout:
            raise RunnerError("MCP process has no stdio pipes")
        request_id = secrets.token_hex(8)
        payload = _json_rpc(method, params, request_id=request_id)
        effective_timeout = float(timeout if timeout is not None else self.config.request_timeout_seconds)

        proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        await proc.stdin.drain()

        deadline = time.monotonic() + effective_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RunnerError(f"MCP request '{method}' timed out")
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            if not line:
                raise RunnerError(await self._death_reason(session))
            try:
                message = json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict) or message.get("id") != request_id:
                continue
            return _unwrap_result(message, request_id)

    async def _notify(self, session: _Session, method: str, params: dict[str, Any] | None = None) -> None:
        proc = session.proc
        if not proc.stdin:
            return
        payload = _json_rpc(method, params)
        proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        await proc.stdin.drain()

    async def _death_reason(self, session: _Session) -> str:
        stderr = ""
        if session.proc.stderr:
            try:
                stderr = (await asyncio.wait_for(session.proc.stderr.read(), timeout=0.2)).decode(
                    "utf-8", errors="replace"
                )
            except Exception:
                stderr = ""
        return stderr.strip() or "MCP server closed the stdio stream"

    async def _discard(self, session_key: str, session: _Session) -> None:
        async with self._registry_lock:
            if self._sessions.get(session_key) is session:
                self._sessions.pop(session_key, None)
        await self._terminate(session)

    async def _terminate(self, session: _Session) -> None:
        proc = session.proc
        if proc.returncode is not None:
            return
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=self.config.terminate_timeout_seconds)
        except (TimeoutError, ProcessLookupError):
            with_kill = getattr(proc, "kill", None)
            if with_kill:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
        except Exception:
            logger.warning("MCP subprocess termination failed", exc_info=True)

    async def reap_idle(self) -> int:
        now = time.monotonic()
        ttl = self.config.session_ttl_seconds
        reaped = 0
        async with self._registry_lock:
            stale_keys = [
                key for key, session in self._sessions.items() if not session.alive or (now - session.last_used) > ttl
            ]
            victims = [self._sessions.pop(key) for key in stale_keys]
        for victim in victims:
            await self._terminate(victim)
            reaped += 1
        return reaped

    async def shutdown(self) -> None:
        async with self._registry_lock:
            victims = list(self._sessions.values())
            self._sessions.clear()
        for victim in victims:
            await self._terminate(victim)

    def stats(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            "sessions": len(self._sessions),
            "max_sessions": self.config.max_sessions,
            "items": [
                {
                    "session": key,
                    "alive": session.alive,
                    "idle_seconds": round(now - session.last_used, 1),
                    "server": session.server_info.get("name") if isinstance(session.server_info, dict) else None,
                }
                for key, session in self._sessions.items()
            ],
        }
