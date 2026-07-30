"""Command execution + sudo helpers for AgentSessionManager."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from asgiref.sync import sync_to_async

from app.agent_kernel.sandbox.ephemeral_runner import agent_command_uses_docker
from app.sudo_policy import (
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
from servers.services.agent_command_runner import run_agent_command


class AgentSessionExecMixin:
    """PTY execute / controlled-sudo methods mixed into AgentSessionManager."""

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    async def execute(self, server_id: int, command: str) -> dict[str, Any]:
        """Execute command via PTY stdin/stdout, wait for prompt marker."""
        session = self.connections.get(server_id)
        if session is None:
            raise RuntimeError(f"Server {server_id} not connected.")

        server_obj = self.allowed_servers.get(server_id)
        if agent_command_uses_docker():
            return await self._execute_isolated(session, server_obj, command)
        if session.proc is None:
            raise RuntimeError(f"Server {server_id} not connected.")
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

    async def _execute_isolated(self, session: Any, server_obj: Any, command: str) -> dict[str, Any]:
        if command_uses_sudo(command) and getattr(server_obj, "sudo_auth_mode", "none") == "stored_password":
            return await self._execute_with_sudo_password(session, server_obj, command)
        if self._can_use_controlled_sudo(server_obj) and command_prefers_controlled_sudo(command):
            return await self._execute_controlled_sudo(
                session,
                server_obj,
                command,
                reason="auto_sudo_privileged_read",
            )

        result = await self._run_isolated_once(session, server_obj, command)
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

    async def _run_isolated_once(
        self,
        session: Any,
        server_obj: Any,
        command: str,
        *,
        input_text: str | None = None,
    ) -> dict[str, Any]:
        result = await run_agent_command(
            server_obj,
            command,
            input_text=input_text,
            timeout_seconds=self.command_timeout,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        for character in stdout + (("\n" + stderr) if stderr else ""):
            session.output_buffer.append(character)
        if self.event_callback:
            await self.event_callback(
                "agent_console",
                {
                    "server_id": session.server_id,
                    "server_name": session.server_name,
                    "event": "command_done",
                    "command": command,
                    "exit_code": result.exit_status,
                    "output_preview": stdout[:500],
                    "runtime": result.runtime,
                },
            )
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result.exit_status,
            "duration_ms": result.duration_ms,
            "runtime": result.runtime,
        }

    async def _execute_via_pty(self, session: Any, command: str) -> dict[str, Any]:
        """Execute a plain command through the interactive PTY."""

        marker = f"__AGENT_EXIT_{id(session)}_{int(time.monotonic() * 1000)}__"
        full_cmd = f'{command}; echo "{marker}:$?:"\n'

        t0 = time.monotonic()

        session.proc.stdin.write(full_cmd)

        exit_code = -1
        stdout_parts = []
        try:
            exit_code, stdout_parts = await asyncio.wait_for(
                self._wait_for_marker(session, marker),
                timeout=self.command_timeout,
            )
        except TimeoutError:
            return {
                "stdout": "".join(stdout_parts) if stdout_parts else "(timeout)",
                "stderr": f"Command timed out after {self.command_timeout}s",
                "exit_code": -1,
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }

        duration = int((time.monotonic() - t0) * 1000)

        if self.event_callback:
            output_text = "".join(stdout_parts)[:500]
            await self.event_callback(
                "agent_console",
                {
                    "server_id": session.server_id,
                    "server_name": session.server_name,
                    "event": "command_done",
                    "command": command,
                    "exit_code": exit_code,
                    "output_preview": output_text,
                },
            )

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
        session: Any,
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

    async def _execute_with_sudo_password(self, session: Any, server_obj: Any, command: str) -> dict[str, Any]:
        t0 = time.monotonic()
        sudo_password = await sync_to_async(get_server_sudo_secret, thread_sensitive=True)(server_obj)
        prepared = prepare_sudo_command(
            command,
            SUDO_POLICY_APPROVED,
            sudo_auth_mode=getattr(server_obj, "sudo_auth_mode", "none"),
            sudo_password=sudo_password,
        )
        if agent_command_uses_docker():
            isolated = await self._run_isolated_once(
                session,
                server_obj,
                prepared.command,
                input_text=prepared.input_text,
            )
            if prepared.notes:
                isolated["stdout"] = "\n".join(prepared.notes) + "\n" + (isolated.get("stdout") or "")
            return isolated
        run_kwargs: dict[str, Any] = {"check": False}
        if prepared.input_text is not None:
            run_kwargs["input"] = prepared.input_text
        result = await asyncio.wait_for(session.conn.run(prepared.command, **run_kwargs), timeout=self.command_timeout)
        duration = int((time.monotonic() - t0) * 1000)
        stdout = result.stdout or ""
        if prepared.notes:
            stdout = "\n".join(prepared.notes) + "\n" + stdout

        if self.event_callback:
            await self.event_callback(
                "agent_console",
                {
                    "server_id": session.server_id,
                    "server_name": session.server_name,
                    "event": "command_done",
                    "command": prepared.command,
                    "exit_code": result.exit_status,
                    "output_preview": stdout[:500],
                },
            )

        return {
            "stdout": stdout,
            "stderr": result.stderr or "",
            "exit_code": result.exit_status,
            "duration_ms": duration,
        }

    async def _wait_for_marker(self, session: Any, marker: str) -> tuple[int, list[str]]:
        """Poll the output buffer until the marker appears."""
        collected = []
        while True:
            await asyncio.sleep(0.1)
            current = "".join(session.output_buffer)
            idx = current.find(marker)
            if idx != -1:
                before_marker = current[:idx]
                after_marker = current[idx + len(marker) :]
                exit_code = 0
                match = re.search(r":(\d+):", after_marker[:20])
                if match:
                    exit_code = int(match.group(1))
                collected.append(before_marker)
                return exit_code, collected
            collected = [current]
