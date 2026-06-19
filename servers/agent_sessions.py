"""
Multi-server SSH session manager for full ReAct agents.

Manages concurrent SSH connections with PTY processes, output buffering,
signal sending, and pattern-based waiting.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time
from collections import deque
from collections.abc import Callable, Coroutine
from typing import Any

import asyncssh
from asgiref.sync import sync_to_async
from loguru import logger

from app.agent_kernel.sudo_policy import (
    SUDO_AUTH_MODE_NONE,
    SUDO_POLICY_APPROVED,
    command_prefers_controlled_sudo,
    command_uses_sudo,
    normalize_sudo_auth_mode,
    normalize_sudo_policy,
    output_indicates_privilege_error,
    prepare_sudo_command,
    wrap_command_for_controlled_sudo,
)
from servers.secret_utils import get_server_sudo_secret
from servers.monitor import _build_connect_kwargs

BUFFER_MAX_CHARS = 8192
COMMAND_TIMEOUT = 30


class _ServerSession:
    """State for a single SSH connection."""

    __slots__ = (
        "server_id",
        "server_name",
        "conn",
        "proc",
        "output_buffer",
        "connected_at",
        "_reader_task",
        "_forbidden_patterns",
    )

    def __init__(self, server_id: int, server_name: str, forbidden_patterns: list[str]):
        self.server_id = server_id
        self.server_name = server_name
        self.conn: asyncssh.SSHClientConnection | None = None
        self.proc: asyncssh.SSHClientProcess | None = None
        self.output_buffer = deque(maxlen=BUFFER_MAX_CHARS)
        self.connected_at: float = 0
        self._reader_task: asyncio.Task | None = None
        self._forbidden_patterns = forbidden_patterns


class AgentSessionManager:
    """
    Manages multiple SSH sessions for a single agent run.

    Each server gets its own asyncssh connection and PTY process.
    Output is continuously buffered so the agent can read_console at any time.
    """

    def __init__(
        self,
        allowed_servers: list[Any],
        max_connections: int = 5,
        command_timeout: int = COMMAND_TIMEOUT,
        event_callback: Callable[..., Coroutine] | None = None,
        available_skills: list[dict[str, Any]] | None = None,
        sudo_policy: str = "disabled",
    ):
        self.allowed_servers: dict[int, Any] = {s.id: s for s in allowed_servers}
        self.max_connections = max_connections
        self.command_timeout = command_timeout
        self.event_callback = event_callback
        self.user_reply_future: asyncio.Future | None = None
        self.available_skills = [dict(skill) for skill in (available_skills or [])]
        self.sudo_policy = normalize_sudo_policy(sudo_policy)

        self.connections: dict[int, _ServerSession] = {}
        self._name_to_id: dict[str, int] = {}
        for s in allowed_servers:
            self._name_to_id[s.name.lower()] = s.id
            self._name_to_id[str(s.id)] = s.id

        self._skills_by_slug: dict[str, dict[str, Any]] = {}
        self._skill_lookup: dict[str, str] = {}
        for skill in self.available_skills:
            slug = str(skill.get("slug") or "").strip()
            name = str(skill.get("name") or "").strip()
            if not slug:
                continue
            self._skills_by_slug[slug] = skill
            self._skill_lookup[slug.lower()] = slug
            if name:
                self._skill_lookup[name.lower()] = slug

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def open(self, server) -> None:
        if server.id in self.connections:
            return
        if len(self.connections) >= self.max_connections:
            raise RuntimeError(f"Max connections ({self.max_connections}) reached.")

        forbidden = self._collect_forbidden(server)
        session = _ServerSession(server.id, server.name, forbidden)

        kwargs = await _build_connect_kwargs(server)
        session.conn = await asyncssh.connect(**kwargs)
        session.proc = await session.conn.create_process(
            term_type="xterm-256color",
            term_size=(120, 40),
        )
        session.connected_at = time.monotonic()
        session._reader_task = asyncio.create_task(self._read_loop(session))

        self.connections[server.id] = session
        self._name_to_id[server.name.lower()] = server.id

        if self.event_callback:
            await self.event_callback("agent_console", {
                "server_id": server.id,
                "server_name": server.name,
                "event": "connected",
            })

        logger.info("Agent session opened: {} ({})", server.name, server.host)

    async def close(self, server_id: int) -> None:
        session = self.connections.pop(server_id, None)
        if session is None:
            return
        if session._reader_task:
            session._reader_task.cancel()
        if session.proc:
            with contextlib.suppress(Exception):
                session.proc.close()
        if session.conn:
            with contextlib.suppress(Exception):
                session.conn.close()
        logger.info("Agent session closed: {}", session.server_name)

    async def close_all(self) -> None:
        for sid in list(self.connections):
            await self.close(sid)

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    def list_skills(self) -> list[dict[str, Any]]:
        return [
            {
                "slug": skill.get("slug", ""),
                "name": skill.get("name", ""),
                "description": skill.get("description", ""),
                "tags": list(skill.get("tags") or []),
                "service": skill.get("service", ""),
                "category": skill.get("category", ""),
                "safety_level": skill.get("safety_level", ""),
                "ui_hint": skill.get("ui_hint", ""),
                "guardrail_summary": list(skill.get("guardrail_summary") or []),
                "recommended_tools": list(skill.get("recommended_tools") or []),
                "runtime_enforced": bool(skill.get("runtime_policy")),
                "path": skill.get("path", ""),
            }
            for skill in self.available_skills
        ]

    def get_skill(self, skill_ref: str) -> dict[str, Any] | None:
        needle = str(skill_ref or "").strip().lower()
        if not needle:
            return None
        slug = self._skill_lookup.get(needle)
        if slug is None:
            return None
        return self._skills_by_slug.get(slug)

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    async def execute(self, server_id: int, command: str) -> dict[str, Any]:
        """Execute command via PTY stdin/stdout, wait for prompt marker."""
        session = self.connections.get(server_id)
        if session is None or session.proc is None:
            raise RuntimeError(f"Server {server_id} not connected.")

        server_obj = self.allowed_servers.get(server_id)
        if (
            command_uses_sudo(command)
            and getattr(server_obj, "sudo_auth_mode", "none") == "stored_password"
            and session.conn is not None
        ):
            return await self._execute_with_sudo_password(session, server_obj, command)

        if self._can_use_controlled_sudo(server_obj) and command_prefers_controlled_sudo(command):
            return await self._execute_controlled_sudo(
                session,
                server_obj,
                command,
                reason="auto_sudo_privileged_read",
            )

        result = await self._execute_via_pty(session, command)
        if (
            self._can_use_controlled_sudo(server_obj)
            and not command_uses_sudo(command)
            and output_indicates_privilege_error(result.get("stdout", ""), result.get("stderr", ""))
        ):
            return await self._execute_controlled_sudo(
                session,
                server_obj,
                command,
                reason="auto_sudo_after_permission_denied",
                original_result=result,
            )

        return result

    async def _execute_via_pty(self, session: _ServerSession, command: str) -> dict[str, Any]:
        """Execute a plain command through the interactive PTY."""

        marker = f"__AGENT_EXIT_{id(session)}_{int(time.monotonic()*1000)}__"
        full_cmd = f"{command}; echo \"{marker}:$?:\"\n"

        t0 = time.monotonic()

        session.proc.stdin.write(full_cmd)

        exit_code = -1
        stdout_parts = []
        try:
            exit_code, stdout_parts = await asyncio.wait_for(
                self._wait_for_marker(session, marker),
                timeout=self.command_timeout,
            )
        except asyncio.TimeoutError:
            return {
                "stdout": "".join(stdout_parts) if stdout_parts else "(timeout)",
                "stderr": f"Command timed out after {self.command_timeout}s",
                "exit_code": -1,
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }

        duration = int((time.monotonic() - t0) * 1000)

        if self.event_callback:
            output_text = "".join(stdout_parts)[:500]
            await self.event_callback("agent_console", {
                "server_id": server_id,
                "server_name": session.server_name,
                "event": "command_done",
                "command": command,
                "exit_code": exit_code,
                "output_preview": output_text,
            })

        return {
            "stdout": "".join(stdout_parts),
            "stderr": "",
            "exit_code": exit_code,
            "duration_ms": duration,
        }

    def _can_use_controlled_sudo(self, server_obj: Any) -> bool:
        if normalize_sudo_policy(self.sudo_policy) != SUDO_POLICY_APPROVED:
            return False
        mode = normalize_sudo_auth_mode(getattr(server_obj, "sudo_auth_mode", "none"))
        return mode != SUDO_AUTH_MODE_NONE

    async def _execute_controlled_sudo(
        self,
        session: _ServerSession,
        server_obj: Any,
        command: str,
        *,
        reason: str,
        original_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sudo_command = wrap_command_for_controlled_sudo(command)
        result = await self._execute_with_sudo_password(session, server_obj, sudo_command)
        notes = [reason]
        if original_result is not None:
            notes.append(f"original_exit_code={original_result.get('exit_code', -1)}")
        result["stdout"] = "\n".join(notes) + "\n" + (result.get("stdout") or "")
        result["auto_sudo"] = True
        result["auto_sudo_reason"] = reason
        return result

    async def _execute_with_sudo_password(self, session: _ServerSession, server_obj: Any, command: str) -> dict[str, Any]:
        t0 = time.monotonic()
        sudo_password = await sync_to_async(get_server_sudo_secret, thread_sensitive=True)(server_obj)
        prepared = prepare_sudo_command(
            command,
            SUDO_POLICY_APPROVED,
            sudo_auth_mode=getattr(server_obj, "sudo_auth_mode", "none"),
            sudo_password=sudo_password,
        )
        run_kwargs: dict[str, Any] = {"check": False}
        if prepared.input_text is not None:
            run_kwargs["input"] = prepared.input_text
        result = await asyncio.wait_for(
            session.conn.run(prepared.command, **run_kwargs),
            timeout=self.command_timeout,
        )
        duration = int((time.monotonic() - t0) * 1000)
        stdout = result.stdout or ""
        if prepared.notes:
            stdout = "\n".join(prepared.notes) + "\n" + stdout

        if self.event_callback:
            await self.event_callback("agent_console", {
                "server_id": session.server_id,
                "server_name": session.server_name,
                "event": "command_done",
                "command": prepared.command,
                "exit_code": result.exit_status,
                "output_preview": stdout[:500],
            })

        return {
            "stdout": stdout,
            "stderr": result.stderr or "",
            "exit_code": result.exit_status,
            "duration_ms": duration,
        }

    async def _wait_for_marker(self, session: _ServerSession, marker: str) -> tuple[int, list[str]]:
        """Poll the output buffer until the marker appears."""
        collected = []
        while True:
            await asyncio.sleep(0.1)
            current = "".join(session.output_buffer)
            idx = current.find(marker)
            if idx != -1:
                before_marker = current[:idx]
                after_marker = current[idx + len(marker):]
                exit_code = 0
                match = re.search(r":(\d+):", after_marker[:20])
                if match:
                    exit_code = int(match.group(1))
                collected.append(before_marker)
                return exit_code, collected
            collected = [current]

    # ------------------------------------------------------------------
    # Output reading
    # ------------------------------------------------------------------

    def read_output(self, server_id: int) -> str:
        session = self.connections.get(server_id)
        if session is None:
            return ""
        return "".join(session.output_buffer)

    async def _read_loop(self, session: _ServerSession) -> None:
        """Continuously read from PTY stdout into the rolling buffer."""
        try:
            while True:
                data = await session.proc.stdout.read(4096)
                if not data:
                    break
                for ch in data:
                    session.output_buffer.append(ch)
                if self.event_callback:
                    await self.event_callback("agent_console", {
                        "server_id": session.server_id,
                        "server_name": session.server_name,
                        "event": "output",
                        "data": data[:500],
                    })
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("Reader for {} stopped: {}", session.server_name, exc)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    async def send_signal(self, server_id: int, signal: str) -> None:
        session = self.connections.get(server_id)
        if session is None or session.proc is None:
            return
        if signal == "ctrl_c":
            session.proc.stdin.write("\x03")
        elif signal == "ctrl_d":
            session.proc.stdin.write("\x04")
        elif signal == "ctrl_z":
            session.proc.stdin.write("\x1a")

    # ------------------------------------------------------------------
    # Pattern waiting
    # ------------------------------------------------------------------

    async def wait_for_pattern(self, server_id: int, pattern: str, timeout: int = 30) -> str:
        """Block until a regex pattern appears in the output buffer."""
        deadline = time.monotonic() + timeout
        compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        while time.monotonic() < deadline:
            buf = self.read_output(server_id)
            match = compiled.search(buf)
            if match:
                return match.group(0)
            await asyncio.sleep(0.3)
        raise asyncio.TimeoutError(f"Pattern '{pattern}' not found in {timeout}s")

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    def resolve_server(self, name_or_id: str) -> int | None:
        """Resolve server name or id to a connected server_id."""
        key = str(name_or_id).lower().strip()
        sid = self._name_to_id.get(key)
        if sid is not None and sid in self.connections:
            return sid
        try:
            sid_int = int(name_or_id)
            if sid_int in self.connections:
                return sid_int
        except (ValueError, TypeError):
            pass
        for s in self.connections.values():
            if s.server_name.lower() == key:
                return s.server_id
        return None

    def find_server_object(self, name_or_id: str):
        """Find server model object from allowed servers."""
        key = str(name_or_id).lower().strip()
        sid = self._name_to_id.get(key)
        if sid and sid in self.allowed_servers:
            return self.allowed_servers[sid]
        try:
            sid_int = int(name_or_id)
            return self.allowed_servers.get(sid_int)
        except (ValueError, TypeError):
            pass
        for s in self.allowed_servers.values():
            if s.name.lower() == key:
                return s
        return None

    def get_forbidden_patterns(self, server_id: int) -> list[str]:
        session = self.connections.get(server_id)
        if session:
            return session._forbidden_patterns
        return []

    def get_connected_info(self) -> list[dict]:
        return [
            {
                "server_id": s.server_id,
                "server_name": s.server_name,
                "connected_for_s": int(time.monotonic() - s.connected_at),
            }
            for s in self.connections.values()
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_forbidden(server) -> list[str]:
        """Collect forbidden patterns from global rules and server group."""
        patterns = []
        try:
            from servers.models import GlobalServerRules
            rules = GlobalServerRules.objects.filter(user=server.user).first()
            if rules and rules.forbidden_commands:
                patterns.extend(rules.forbidden_commands)
        except Exception:
            pass
        try:
            if server.group and server.group.forbidden_commands:
                patterns.extend(server.group.forbidden_commands)
        except Exception:
            pass
        return patterns
