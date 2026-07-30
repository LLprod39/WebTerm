"""
Multi-server SSH session manager for full ReAct agents.

Manages concurrent SSH connections with PTY processes, output buffering,
signal sending, and pattern-based waiting.

F-08a.10: command execution / sudo live in ``agent_sessions_exec``
(``AgentSessionExecMixin``). This module keeps connection lifecycle, skills,
materials, I/O helpers and re-exports ``AgentSessionManager``.
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
from loguru import logger

from app.agent_kernel.sandbox.ephemeral_runner import agent_command_uses_docker
from app.sudo_policy import normalize_sudo_policy
from servers.agents.agent_sessions_exec import AgentSessionExecMixin
from servers.monitoring.monitor import _build_connect_kwargs

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


class AgentSessionManager(AgentSessionExecMixin):
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
        available_materials: list[dict[str, Any]] | None = None,
        sudo_policy: str = "disabled",
        execution_approval_granted: bool = False,
    ):
        self.allowed_servers: dict[int, Any] = {s.id: s for s in allowed_servers}
        self.max_connections = max_connections
        self.command_timeout = command_timeout
        self.event_callback = event_callback
        self.user_reply_future: asyncio.Future | None = None
        self.available_skills = [dict(skill) for skill in (available_skills or [])]
        self.sudo_policy = normalize_sudo_policy(sudo_policy)
        self.execution_approval_granted = bool(execution_approval_granted)

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

        from servers.agents.agent_inputs import normalize_input_artifacts

        self.available_materials = normalize_input_artifacts(available_materials or [])

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

        if agent_command_uses_docker():
            session.connected_at = time.monotonic()
            self.connections[server.id] = session
            self._name_to_id[server.name.lower()] = server.id
            if self.event_callback:
                await self.event_callback(
                    "agent_console",
                    {
                        "server_id": server.id,
                        "server_name": server.name,
                        "event": "connected",
                        "runtime": "ephemeral_container",
                    },
                )
            logger.info("Agent isolated session ready: {} ({})", server.name, server.host)
            return

        kwargs = await _build_connect_kwargs(server)
        host = kwargs.get("host") or getattr(server, "host", "") or "?"
        port = kwargs.get("port") or int(getattr(server, "port", 22) or 22)
        try:
            session.conn = await asyncssh.connect(**kwargs)
        except Exception as exc:  # noqa: BLE001 — surface a readable connection error
            detail = str(exc).strip()
            if not detail:
                detail = (
                    "истёк таймаут SSH-рукопожатия (порт открыт, но SSH не ответил)"
                    if isinstance(exc, (asyncio.TimeoutError, TimeoutError))
                    else type(exc).__name__
                )
            raise RuntimeError(f"SSH connection failed to {server.name} ({host}:{port}): {detail}") from exc
        session.proc = await session.conn.create_process(
            term_type="xterm-256color",
            term_size=(120, 40),
        )
        session.connected_at = time.monotonic()
        session._reader_task = asyncio.create_task(self._read_loop(session))

        self.connections[server.id] = session
        self._name_to_id[server.name.lower()] = server.id

        if self.event_callback:
            await self.event_callback(
                "agent_console",
                {
                    "server_id": server.id,
                    "server_name": server.name,
                    "event": "connected",
                },
            )

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
    # Materials (operator documents / task lists / scripts)
    # ------------------------------------------------------------------

    def list_materials(self) -> list[dict[str, Any]]:
        from servers.agents.agent_inputs import materials_catalog

        return materials_catalog(self.available_materials)

    def get_material(self, material_ref: str) -> dict[str, Any] | None:
        from servers.agents.agent_inputs import get_material_by_ref

        return get_material_by_ref(self.available_materials, material_ref)

    def update_material_task(
        self,
        material_ref: str,
        task_index: int,
        *,
        status: str,
        evidence: str = "",
    ) -> dict[str, Any] | None:
        material = self.get_material(material_ref)
        if material is None or material.get("kind") != "task_list":
            return None
        tasks = list(material.get("tasks") or [])
        if task_index < 0 or task_index >= len(tasks):
            return None
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"pending", "in_progress", "done", "skipped", "blocked"}:
            return None
        task = dict(tasks[task_index])
        task["status"] = normalized_status
        task["done"] = normalized_status == "done"
        if evidence:
            task["evidence"] = str(evidence).strip()[:800]
        tasks[task_index] = task
        material["tasks"] = tasks
        from servers.agents.agent_inputs import _tasks_to_markdown

        material["content"] = _tasks_to_markdown(tasks)
        # Keep list in sync by id
        for index, item in enumerate(self.available_materials):
            if item.get("id") == material.get("id"):
                self.available_materials[index] = material
                break
        return material

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
                    await self.event_callback(
                        "agent_console",
                        {
                            "server_id": session.server_id,
                            "server_name": session.server_name,
                            "event": "output",
                            "data": data[:500],
                        },
                    )
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
        raise TimeoutError(f"Pattern '{pattern}' not found in {timeout}s")

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
        except Exception as exc:
            logger.debug("global forbidden-command rules unavailable: {}", exc)
        try:
            if server.group and server.group.forbidden_commands:
                patterns.extend(server.group.forbidden_commands)
        except Exception as exc:
            logger.debug("group forbidden-command rules unavailable: {}", exc)
        return patterns
