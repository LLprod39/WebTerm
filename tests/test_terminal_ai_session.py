"""Tests for servers.services.terminal_ai.session (F2-1)."""
from __future__ import annotations

from servers.services.terminal_ai.session import TerminalAiSession


class TestDefaults:
    def test_fresh_session_is_empty(self):
        s = TerminalAiSession()
        assert s.plan == []
        assert s.plan_index == 0
        assert s.next_id == 1
        assert s.step_extra_count == 0
        assert s.user_message == ""
        assert s.chat_mode == "agent"
        assert s.execution_mode == "step"
        assert s.run_id == ""
        assert s.marker_token == ""
        assert s.last_done_items == []
        assert s.last_report == ""
        assert s.stop_requested is False


class TestResetForNewRequest:
    def test_reset_clears_everything_and_installs_context(self):
        s = TerminalAiSession()
        # Dirty the session
        s.plan = [{"id": 1, "cmd": "ls"}]
        s.plan_index = 1
        s.next_id = 42
        s.step_extra_count = 3
        s.last_done_items = [{"id": 1}]
        s.last_report = "old"
        s.stop_requested = True

        s.reset_for_new_request(
            user_message="новая задача",
            chat_mode="ask",
            execution_mode="fast",
            run_id="run-abc",
            marker_token="mark-xyz",
        )

        assert s.plan == []
        assert s.plan_index == 0
        assert s.next_id == 1
        assert s.step_extra_count == 0
        assert s.last_done_items == []
        assert s.last_report == ""
        assert s.stop_requested is False
        assert s.user_message == "новая задача"
        assert s.chat_mode == "ask"
        assert s.execution_mode == "fast"
        assert s.run_id == "run-abc"
        assert s.marker_token == "mark-xyz"


class TestMutationHelpers:
    def test_allocate_id_is_monotonic(self):
        s = TerminalAiSession()
        assert s.allocate_id() == 1
        assert s.allocate_id() == 2
        assert s.allocate_id() == 3
        assert s.next_id == 4

    def test_append_plan_item(self):
        s = TerminalAiSession()
        s.append_plan_item({"id": 1, "cmd": "a"})
        s.append_plan_item({"id": 2, "cmd": "b"})
        assert [x["cmd"] for x in s.plan] == ["a", "b"]

    def test_insert_after_cursor_injects_before_current(self):
        s = TerminalAiSession()
        s.plan = [{"id": 1, "cmd": "a"}, {"id": 2, "cmd": "b"}, {"id": 3, "cmd": "c"}]
        s.plan_index = 1  # cursor on "b"
        s.insert_after_cursor({"id": 10, "cmd": "adaptive"})
        assert [x["cmd"] for x in s.plan] == ["a", "adaptive", "b", "c"]

    def test_insert_after_cursor_clamps_out_of_range(self):
        s = TerminalAiSession()
        s.plan = [{"cmd": "x"}]
        s.plan_index = 99  # out-of-range cursor
        s.insert_after_cursor({"cmd": "y"})
        # Should clamp, not raise
        assert {"cmd": "y"} in s.plan

    def test_remaining_is_read_only_snapshot(self):
        s = TerminalAiSession()
        s.plan = [{"id": 1}, {"id": 2}, {"id": 3}]
        s.plan_index = 1
        remaining = s.remaining()
        assert [x["id"] for x in remaining] == [2, 3]
        # Mutating the snapshot must not change the session
        remaining.append({"id": 99})
        assert len(s.plan) == 3

    def test_is_empty_and_is_finished(self):
        s = TerminalAiSession()
        assert s.is_empty() is True
        assert s.is_finished() is True  # no items, trivially done

        s.plan = [{"id": 1}, {"id": 2}]
        s.plan_index = 0
        assert s.is_empty() is False
        assert s.is_finished() is False

        s.plan_index = 2
        assert s.is_finished() is True

    def test_record_done_accumulates(self):
        s = TerminalAiSession()
        s.record_done({"id": 1, "exit_code": 0})
        s.record_done({"id": 2, "exit_code": 127})
        assert len(s.last_done_items) == 2
        assert [x["exit_code"] for x in s.last_done_items] == [0, 127]


class TestClear:
    def test_clear_wipes_queue_but_keeps_identifiers(self):
        s = TerminalAiSession()
        s.reset_for_new_request(
            user_message="u",
            chat_mode="agent",
            execution_mode="step",
            run_id="r",
            marker_token="m",
        )
        s.plan = [{"id": 1}]
        s.plan_index = 1
        s.step_extra_count = 2
        s.stop_requested = True

        s.clear()

        assert s.plan == []
        assert s.plan_index == 0
        assert s.step_extra_count == 0
        assert s.stop_requested is False
        # Identifiers are preserved so trailing ``ai_*`` events still
        # carry the right run_id.
        assert s.run_id == "r"
        assert s.marker_token == "m"
        assert s.user_message == "u"


class TestRegressionScenario:
    """Simulate the canonical happy-path lifecycle of a single turn."""

    def test_full_turn_lifecycle(self):
        s = TerminalAiSession()

        # 1) Request starts
        s.reset_for_new_request(
            user_message="deploy",
            chat_mode="agent",
            execution_mode="step",
            run_id="R1",
            marker_token="M1",
        )

        # 2) Planner drops in 3 items
        for cmd in ("git pull", "make build", "systemctl restart app"):
            s.append_plan_item({"id": s.allocate_id(), "cmd": cmd})

        assert s.next_id == 4
        assert len(s.plan) == 3
        assert s.remaining() == s.plan

        # 3) Run first item → mark done, advance
        s.record_done({**s.plan[0], "exit_code": 0, "output": "ok"})
        s.plan_index = 1

        # 4) Step-mode injects adaptive "check logs" before remaining items
        s.insert_after_cursor({"id": s.allocate_id(), "cmd": "tail logs"})
        assert s.plan[s.plan_index]["cmd"] == "tail logs"
        s.step_extra_count += 1

        # 5) User hits /stop
        s.stop_requested = True

        # 6) Orchestrator reacts → clear
        s.clear()
        assert s.is_empty()
        assert s.stop_requested is False
        # But the last_done_items stays so the report step can still run
        assert len(s.last_done_items) == 1
