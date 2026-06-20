from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from servers.services.terminal_ai.queue_completion import handle_queue_completion
from servers.services.terminal_ai.reporter import compute_report_status
from servers.services.terminal_ai.session import TerminalAiSession


@pytest.mark.asyncio
async def test_handle_queue_completion_generates_report_history_and_memory_task():
    owner = _CompletionOwner()

    await handle_queue_completion(owner)

    assert [event["type"] for event in owner.events] == ["ai_status", "ai_report"]
    assert owner.events[0]["status"] == "generating_report"
    assert owner.events[1]["report"] == "report body"
    assert owner._ai_last_report == "report body"
    assert owner.history[0][0] == "assistant"
    assert "apt install nginx" in owner.history[0][1]
    assert owner.history[1] == ("assistant", "[Отчёт]\nreport body")
    assert owner.spawned_memory is not None
    assert owner.spawned_memory["user_message"] == "install nginx"
    assert [row["cmd"] for row in owner.spawned_memory["commands_with_output"]] == [
        "apt install nginx",
        "systemctl restart nginx",
    ]


@pytest.mark.asyncio
async def test_handle_queue_completion_noops_without_user_message():
    owner = _CompletionOwner()
    owner._ai_user_message = ""

    await handle_queue_completion(owner)

    assert owner.events == []
    assert owner.history == []
    assert owner.spawned_memory is None


@pytest.mark.asyncio
async def test_handle_queue_completion_respects_disabled_auto_report_and_memory():
    owner = _CompletionOwner(auto_report=False)
    owner._ai_settings["memory_enabled"] = False

    await handle_queue_completion(owner)

    assert owner.events == []
    assert owner.history == []
    assert owner._ai_last_report == ""
    assert owner.spawned_memory is None


class _CompletionOwner:
    _TerminalAiSessionCls = TerminalAiSession

    def __init__(self, *, auto_report: bool = True):
        self.auto_report = auto_report
        self.events: list[dict] = []
        self.history: list[tuple[str, str]] = []
        self.spawned_memory: dict | None = None
        self._ai_lock = asyncio.Lock()
        self._ai_user_message = "install nginx"
        self._ai_execution_mode = "step"
        self._ai_settings = {"memory_enabled": True, "dry_run": False}
        self._ai_plan = [
            {
                "id": 1,
                "cmd": "apt install nginx",
                "status": "done",
                "exit_code": 0,
                "output_snippet": "installed",
            },
            {
                "id": 2,
                "cmd": "systemctl restart nginx",
                "status": "done",
                "exit_code": 0,
                "output_snippet": "restarted",
            },
        ]
        self._ai_plan_index = len(self._ai_plan)
        self._ai_next_id = 3
        self._ai_step_extra_count = 0
        self._ai_forbidden_patterns: list[str] = []
        self._ai_chat_mode = "agent"
        self._ai_run_id = ""
        self._ai_marker_token = ""
        self._ai_last_done_items: list[dict] = []
        self._ai_last_report = "old"
        self._ai_stop_requested = False
        self._ai_session = TerminalAiSession()
        self._user_id = 10
        self.server = SimpleNamespace(id=20)
        self._ai_audit_context = {"run": "r1"}

    def _is_auto_report_enabled(self, _settings: dict, _execution_mode: str) -> bool:
        return self.auto_report

    async def _generate_ai_report_text(self, user_message: str, done_items: list[dict]) -> str:
        assert user_message == self._ai_user_message
        assert len(done_items) == 2
        return "report body"

    def _compute_report_status(self, done_items: list[dict]) -> str:
        return compute_report_status(done_items)

    async def _send_ai_event(self, event: dict) -> None:
        self.events.append(event)

    def _add_to_history(self, role: str, text: str) -> None:
        self.history.append((role, text))

    def _spawn_memory_extraction_task(self, **kwargs) -> None:
        self.spawned_memory = kwargs
