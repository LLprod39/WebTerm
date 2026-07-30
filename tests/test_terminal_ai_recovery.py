from __future__ import annotations

import asyncio

import pytest

from servers.consumers.ssh_terminal import SSHTerminalConsumer
from servers.services.terminal_ai.plan_insertions import TerminalAiPlanReservation
from servers.services.terminal_ai.recovery import (
    RetryCandidate,
    handle_fast_error_recovery,
    handle_step_post_command,
    insert_retry_candidate,
    recovery_abort_message,
    recovery_action,
    recovery_question,
    retry_candidate_from_decision,
    should_attempt_error_recovery,
)
from servers.services.terminal_ai.run_controller import TerminalAiRunController
from servers.services.terminal_ai.session import TerminalAiSession
from servers.services.terminal_ai.state import TerminalAiState


def test_should_attempt_error_recovery_only_for_fast_mode_failures_under_retry_limit():
    item = {"cmd": "apt install missing"}

    assert should_attempt_error_recovery(exit_code=1, item=item, step_mode=False, retries=1) is True
    assert should_attempt_error_recovery(exit_code=0, item=item, step_mode=False, retries=0) is False
    assert should_attempt_error_recovery(exit_code=130, item=item, step_mode=False, retries=0) is False
    assert should_attempt_error_recovery(exit_code=None, item=item, step_mode=False, retries=0) is False
    assert should_attempt_error_recovery(exit_code=1, item=item, step_mode=True, retries=0) is False
    assert should_attempt_error_recovery(exit_code=1, item={"_no_recovery": True}, step_mode=False, retries=0) is False
    assert should_attempt_error_recovery(exit_code=1, item=item, step_mode=False, retries=2) is False


def test_recovery_action_normalizes_missing_or_mixed_case_values():
    assert recovery_action({"action": " RETRY "}) == "retry"
    assert recovery_action({"action": ""}) == "skip"
    assert recovery_action({}, default="continue") == "continue"


def test_retry_candidate_from_decision_projects_valid_changed_command():
    candidate = retry_candidate_from_decision(
        {"cmd": "apt-get update", "why": "refresh package index"},
        original_command="apt update",
        retries=0,
        default_why="Retry after error",
    )

    assert candidate is not None
    assert candidate.command == "apt-get update"
    assert candidate.why == "refresh package index"


def test_retry_candidate_from_decision_rejects_empty_same_or_over_limit_commands():
    assert (
        retry_candidate_from_decision(
            {"cmd": ""},
            original_command="apt update",
            retries=0,
            default_why="Retry",
        )
        is None
    )
    assert (
        retry_candidate_from_decision(
            {"cmd": "apt update"},
            original_command="apt update",
            retries=0,
            default_why="Retry",
        )
        is None
    )
    assert (
        retry_candidate_from_decision(
            {"cmd": "apt-get update"},
            original_command="apt update",
            retries=2,
            default_why="Retry",
        )
        is None
    )


def test_recovery_text_helpers_use_defaults_for_empty_decisions():
    assert recovery_question({}, default="Как продолжить?") == "Как продолжить?"
    assert recovery_abort_message({}, default="Выполнение прервано") == "Выполнение прервано"


def test_reserved_retry_plan_item_marks_no_recovery_flag():
    consumer = object.__new__(SSHTerminalConsumer)
    consumer._ai_state = TerminalAiState.create(
        run_controller_factory=TerminalAiRunController,
        session_factory=TerminalAiSession,
        settings=SSHTerminalConsumer._default_ai_settings(),
    )
    consumer._ai_state.session.chat_mode = "agent"

    item = consumer._build_reserved_plan_item(
        TerminalAiPlanReservation(item_id=3, forbidden_patterns=[]),
        cmd="apt-get update",
        why="retry",
        no_recovery=True,
    )

    assert item["_no_recovery"] is True


@pytest.mark.asyncio
async def test_insert_retry_candidate_uses_owner_hooks():
    class Owner:
        def __init__(self):
            self.inserted = None
            self.events: list[dict] = []

        async def _reserve_ai_retry_item(self, retries: int):
            assert retries == 1
            return type("Reservation", (), {"item_id": 9})()

        def _build_reserved_plan_item(self, reservation, *, cmd: str, why: str, no_recovery: bool):
            assert reservation.item_id == 9
            assert no_recovery is True
            return {
                "id": reservation.item_id,
                "cmd": cmd,
                "why": why,
                "requires_confirm": True,
                "reason": "dangerous",
                "streaming": False,
            }

        async def _insert_ai_plan_item(self, item: dict, *, at_cursor: bool):
            self.inserted = (item, at_cursor)

        async def _send_ai_event(self, event: dict):
            self.events.append(event)

    owner = Owner()

    await insert_retry_candidate(
        owner,
        RetryCandidate(command="apt-get update", why="refresh index"),
        original_command="apt update",
        retries=1,
        at_cursor=True,
        event_why="",
    )

    assert owner.inserted == (
        {
            "id": 9,
            "cmd": "apt-get update",
            "why": "refresh index",
            "requires_confirm": True,
            "reason": "dangerous",
            "streaming": False,
        },
        True,
    )
    assert owner.events == [
        {
            "type": "ai_recovery",
            "original_cmd": "apt update",
            "new_cmd": "apt-get update",
            "new_id": 9,
            "why": "",
            "requires_confirm": True,
            "reason": "dangerous",
            "streaming": False,
        }
    ]


@pytest.mark.asyncio
async def test_handle_fast_error_recovery_retries_changed_command():
    owner = _FastRecoveryOwner([{"action": "retry", "cmd": "apt-get update", "why": "refresh"}])

    action = await handle_fast_error_recovery(
        owner,
        item={"cmd": "apt update"},
        item_id=1,
        command="apt update",
        exit_code=1,
        output="failed",
        step_mode=False,
    )

    assert action == "retry"
    assert owner.handle_error_calls == [
        {
            "cmd": "apt update",
            "exit_code": 1,
            "output": "failed",
            "remaining_cmds": ["next"],
            "user_reply": None,
        }
    ]
    assert owner.inserted[0][0]["cmd"] == "apt-get update"
    assert [event["type"] for event in owner.events] == ["ai_status", "ai_recovery"]


@pytest.mark.asyncio
async def test_handle_fast_error_recovery_ask_then_abort_emits_question_and_error():
    owner = _FastRecoveryOwner(
        [
            {"action": "ask", "question": "Continue?"},
            {"action": "abort", "why": "stop now"},
        ],
        user_reply="stop",
    )

    action = await handle_fast_error_recovery(
        owner,
        item={"cmd": "apt update"},
        item_id=1,
        command="apt update",
        exit_code=1,
        output="failed",
        step_mode=False,
    )

    assert action == "abort"
    assert owner.history == [("user", "[Ответ агенту]: stop")]
    assert [event["type"] for event in owner.events] == ["ai_status", "ai_question", "ai_error"]
    assert owner.events[-1]["message"] == "stop now"


@pytest.mark.asyncio
async def test_handle_fast_error_recovery_noops_when_recovery_is_not_allowed():
    owner = _FastRecoveryOwner([{"action": "retry", "cmd": "fixed"}])

    action = await handle_fast_error_recovery(
        owner,
        item={"_no_recovery": True},
        item_id=1,
        command="apt update",
        exit_code=1,
        output="failed",
        step_mode=False,
    )

    assert action is None
    assert owner.events == []
    assert owner.handle_error_calls == []


@pytest.mark.asyncio
async def test_handle_step_post_command_retries_at_cursor():
    owner = _FastRecoveryOwner([{"action": "retry", "cmd": "apt-get update", "why": "refresh"}])

    should_stop = await handle_step_post_command(
        owner,
        item_id=1,
        command="apt update",
        exit_code=1,
        output="failed",
    )

    assert should_stop is False
    assert owner.step_decision_calls[0]["remaining_cmds"] == ["apt update", "next"]
    assert owner.inserted[0][1] is True
    assert owner.events[-1]["type"] == "ai_recovery"
    assert owner.events[-1]["why"] == "refresh"


@pytest.mark.asyncio
async def test_handle_step_post_command_adds_next_adaptive_command():
    owner = _FastRecoveryOwner(
        [{"action": "next", "next_cmd": "uptime", "why": "check load", "assistant_text": "Adding check"}]
    )

    should_stop = await handle_step_post_command(
        owner,
        item_id=1,
        command="apt update",
        exit_code=0,
        output="ok",
    )

    assert should_stop is False
    assert owner.inserted[0][0]["cmd"] == "uptime"
    assert owner.inserted[0][1] is True
    assert owner.events[-1]["type"] == "ai_response"
    assert owner.events[-1]["commands"][0]["cmd"] == "uptime"


@pytest.mark.asyncio
async def test_handle_step_post_command_done_skips_remaining_commands():
    owner = _FastRecoveryOwner([{"action": "done", "assistant_text": "Готово"}])
    owner._ai_state.session.plan[0]["status"] = "done"
    owner._ai_state.session.plan_index = 1

    should_stop = await handle_step_post_command(
        owner,
        item_id=1,
        command="apt update",
        exit_code=0,
        output="ok",
    )

    assert should_stop is True
    assert owner.history == [("assistant", "Готово")]
    assert [event["type"] for event in owner.events] == ["ai_response", "ai_command_status"]
    assert owner.events[-1]["id"] == 2
    assert owner.events[-1]["reason"] == "goal_achieved"


@pytest.mark.asyncio
async def test_handle_step_post_command_abort_stops_queue():
    owner = _FastRecoveryOwner([{"action": "abort", "assistant_text": "Stop"}])

    should_stop = await handle_step_post_command(
        owner,
        item_id=1,
        command="apt update",
        exit_code=1,
        output="failed",
    )

    assert should_stop is True
    assert owner.events == [{"type": "ai_error", "message": "Stop"}]


class _FakeAiRun:
    def __init__(self, reply: str):
        self.reply = reply
        self.lock = asyncio.Lock()

    async def ask_user(self, *, event: dict, send_event, **_kwargs):
        await send_event(event)
        return self.reply


class _FastRecoveryOwner:
    _TerminalAiSessionCls = TerminalAiSession

    def __init__(self, decisions: list[dict], *, user_reply: str = "ok"):
        self.decisions = list(decisions)
        self.handle_error_calls: list[dict] = []
        self.events: list[dict] = []
        self.history: list[tuple[str, str]] = []
        self.inserted: list[tuple[dict, bool]] = []
        self.step_decision_calls: list[dict] = []
        self._ai_state = TerminalAiState(
            run=_FakeAiRun(user_reply),
            session=TerminalAiSession(
                plan=[{"id": 1, "cmd": "apt update"}, {"id": 2, "cmd": "next"}],
                next_id=5,
                execution_mode="fast",
            ),
            settings={},
        )

    async def _send_ai_event(self, event: dict):
        self.events.append(event)

    async def _ai_handle_error(
        self,
        cmd: str,
        exit_code: int,
        output: str,
        remaining_cmds: list[str],
        user_reply: str | None = None,
    ) -> dict:
        self.handle_error_calls.append(
            {
                "cmd": cmd,
                "exit_code": exit_code,
                "output": output,
                "remaining_cmds": remaining_cmds,
                "user_reply": user_reply,
            }
        )
        return self.decisions.pop(0)

    async def _ai_step_decide_next(
        self,
        *,
        user_goal: str,
        last_cmd: str,
        exit_code: int,
        output: str,
        remaining_cmds: list[str],
        user_reply: str | None = None,
    ) -> dict:
        self.step_decision_calls.append(
            {
                "user_goal": user_goal,
                "last_cmd": last_cmd,
                "exit_code": exit_code,
                "output": output,
                "remaining_cmds": remaining_cmds,
                "user_reply": user_reply,
            }
        )
        return self.decisions.pop(0)

    async def _reserve_ai_retry_item(self, retries: int):
        item_id = 20 + retries
        self._ai_state.error_retries[item_id] = retries + 1
        return TerminalAiPlanReservation(item_id=item_id, forbidden_patterns=[])

    async def _reserve_ai_adaptive_item(self, extra_limit: int):
        assert extra_limit == 20
        self._ai_state.session.step_extra_count += 1
        return TerminalAiPlanReservation(
            item_id=40 + self._ai_state.session.step_extra_count,
            forbidden_patterns=[],
        )

    def _build_reserved_plan_item(self, reservation, *, cmd: str, why: str, no_recovery: bool = False):
        return {
            "id": reservation.item_id,
            "cmd": cmd,
            "why": why,
            "_no_recovery": no_recovery,
            "requires_confirm": False,
            "reason": "",
            "streaming": False,
        }

    async def _insert_ai_plan_item(self, item: dict, *, at_cursor: bool):
        self.inserted.append((item, at_cursor))

    def _add_to_history(self, role: str, text: str):
        self.history.append((role, text))
