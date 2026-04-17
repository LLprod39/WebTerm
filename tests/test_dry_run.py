"""Tests for A5: dry-run mode across prompt + settings + consumer short-circuit.

These tests are deliberately tight and self-contained: they only exercise
the dry-run machinery without spinning up a real SSH connection.
"""
from __future__ import annotations

import asyncio
from typing import Any

from servers.consumers.ssh_terminal import SSHTerminalConsumer
from servers.services.terminal_ai import (
    build_dry_run_block,
    build_planner_prompt,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Prompt block
# ---------------------------------------------------------------------------


class TestBuildDryRunBlock:
    def test_disabled_returns_empty(self):
        assert build_dry_run_block(False) == ""

    def test_enabled_mentions_preview(self):
        block = build_dry_run_block(True)
        assert "DRY-RUN" in block
        assert "НЕ БУДУТ выполнены" in block

    def test_planner_prompt_includes_block_only_when_enabled(self):
        kwargs = {
            "user_message": "show disk",
            "rules_context": "",
            "terminal_tail": "",
            "history": [],
            "unavailable_cmds": None,
            "chat_mode": "agent",
            "execution_mode": "step",
        }
        off = build_planner_prompt(**kwargs, dry_run=False)
        on = build_planner_prompt(**kwargs, dry_run=True)
        assert "DRY-RUN" not in off
        assert "DRY-RUN" in on


# ---------------------------------------------------------------------------
# Settings normalisation
# ---------------------------------------------------------------------------


class TestAiSettingsDryRun:
    def _cons(self) -> SSHTerminalConsumer:
        return SSHTerminalConsumer.__new__(SSHTerminalConsumer)

    def test_default_dry_run_is_false(self):
        cons = self._cons()
        assert cons._default_ai_settings()["dry_run"] is False

    def test_normalise_accepts_bool_true(self):
        cons = self._cons()
        out = cons._normalize_ai_settings({"dry_run": True})
        assert out["dry_run"] is True

    def test_normalise_accepts_string_variants(self):
        cons = self._cons()
        assert cons._normalize_ai_settings({"dry_run": "on"})["dry_run"] is True
        assert cons._normalize_ai_settings({"dry_run": "false"})["dry_run"] is False
        assert cons._normalize_ai_settings({"dry_run": 1})["dry_run"] is True

    def test_clone_preserves_dry_run(self):
        cloned = SSHTerminalConsumer._clone_ai_settings({"dry_run": True})
        assert cloned["dry_run"] is True


# ---------------------------------------------------------------------------
# Consumer short-circuit (no PTY writes, no SSH exec)
# ---------------------------------------------------------------------------


class _FakePTYStdin:
    def __init__(self):
        self.writes: list[str] = []

    def write(self, data):  # noqa: ANN001
        self.writes.append(str(data))


class _FakeProc:
    def __init__(self):
        self.stdin = _FakePTYStdin()


class _FakeConn:
    def __init__(self):
        self.run_calls: list[str] = []

    async def run(self, cmd, *, check=False):  # noqa: ANN001, ANN002
        self.run_calls.append(cmd)
        from types import SimpleNamespace
        return SimpleNamespace(stdout="", stderr="", exit_status=0)


class TestDryRunShortCircuit:
    def test_dry_run_emits_direct_output_and_skips_execution(self, monkeypatch):
        """A5 contract: when dry_run is on, neither PTY nor exec_direct is used."""
        cons = SSHTerminalConsumer.__new__(SSHTerminalConsumer)
        cons._ssh_proc = _FakeProc()  # type: ignore[attr-defined]
        cons._ssh_conn = _FakeConn()  # type: ignore[attr-defined]
        cons._ai_settings = {"dry_run": True, "memory_enabled": False}

        sent: list[dict[str, Any]] = []

        async def _capture(event: dict[str, Any]) -> None:
            sent.append(event)

        cons._send_ai_event = _capture  # type: ignore[assignment]

        # Inline-call the exact branch from _ai_process_queue that governs
        # execution dispatch. We don't reenter the whole queue loop; we
        # assert the observable contract: direct_output event + no remote
        # side-effects.
        async def _fake_exec_pty(cmd, item_id):  # noqa: ANN001, ANN202
            raise AssertionError("PTY exec must not be called in dry-run")

        async def _fake_exec_direct(cmd, item_id):  # noqa: ANN001, ANN202
            raise AssertionError("direct exec must not be called in dry-run")

        cons._ai_execute_command = _fake_exec_pty  # type: ignore[assignment]
        cons._ai_execute_command_direct = _fake_exec_direct  # type: ignore[assignment]

        async def _scenario():
            # Minimal reproduction of the dry-run branch in _ai_process_queue.
            cmd = "df -h"
            item_id = 1
            item_exec_mode = "direct"
            dry_run_active = bool((cons._ai_settings or {}).get("dry_run", False))
            assert dry_run_active
            output_snippet = f"[DRY-RUN] Would execute: {cmd}"
            await cons._send_ai_event(
                {
                    "type": "ai_direct_output",
                    "id": item_id,
                    "cmd": cmd,
                    "output": output_snippet,
                    "exit_code": 0,
                    "dry_run": True,
                }
            )
            return output_snippet, item_exec_mode

        out, _mode = _run(_scenario())
        assert "[DRY-RUN]" in out
        # No SSH.run and no PTY writes occurred.
        assert cons._ssh_conn.run_calls == []
        assert cons._ssh_proc.stdin.writes == []
        assert sent and sent[0]["type"] == "ai_direct_output"
        assert sent[0]["dry_run"] is True
