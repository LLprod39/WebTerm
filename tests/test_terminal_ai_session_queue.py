"""Queue state-machine tests for terminal-AI sessions."""

from __future__ import annotations

from servers.services.terminal_ai.session import TerminalAiSession


class TestTerminalAiQueueIdsAndInsertion:
    def test_allocate_question_id_uses_same_monotonic_sequence(self):
        s = TerminalAiSession()

        assert s.allocate_question_id("q_10") == "q_10_1"
        assert s.allocate_id() == 2
        assert s.allocate_question_id("q_step_10") == "q_step_10_3"
        assert s.next_id == 4

    def test_insert_after_current_places_item_after_cursor(self):
        s = TerminalAiSession()
        s.plan = [{"cmd": "a"}, {"cmd": "b"}, {"cmd": "c"}]
        s.plan_index = 1

        s.insert_after_current({"cmd": "retry"})

        assert [x["cmd"] for x in s.plan] == ["a", "b", "retry", "c"]

    def test_insert_at_cursor_places_item_as_next_to_run(self):
        s = TerminalAiSession()
        s.plan = [{"cmd": "a"}, {"cmd": "b"}, {"cmd": "c"}]
        s.plan_index = 1

        s.insert_at_cursor({"cmd": "adaptive"})

        assert [x["cmd"] for x in s.plan] == ["a", "adaptive", "b", "c"]

    def test_increment_step_extra_count_returns_new_value(self):
        s = TerminalAiSession()

        assert s.increment_step_extra_count() == 1
        assert s.increment_step_extra_count() == 2
        assert s.step_extra_count == 2


class TestTerminalAiQueueStepPreparation:
    def test_prepare_parallel_batch_returns_current_direct_snapshot(self):
        s = TerminalAiSession()
        s.plan = [
            {"id": 1, "cmd": "df -h", "exec_mode": "direct"},
            {"id": 2, "cmd": "free -m", "exec_mode": "direct"},
            {"id": 3, "cmd": "top", "exec_mode": "pty"},
        ]

        batch = s.prepare_parallel_batch(
            direct_exec_enabled=True,
            step_mode=False,
            has_ssh_connection=True,
        )

        assert batch.is_ready is True
        assert batch.indices == [0, 1]
        assert batch.items == s.plan[:2]

    def test_prepare_parallel_batch_disabled_without_direct_ssh_or_in_step_mode(self):
        s = TerminalAiSession()
        s.plan = [
            {"id": 1, "cmd": "df -h", "exec_mode": "direct"},
            {"id": 2, "cmd": "free -m", "exec_mode": "direct"},
        ]

        assert not s.prepare_parallel_batch(
            direct_exec_enabled=False,
            step_mode=False,
            has_ssh_connection=True,
        ).is_ready
        assert not s.prepare_parallel_batch(
            direct_exec_enabled=True,
            step_mode=True,
            has_ssh_connection=True,
        ).is_ready
        assert not s.prepare_parallel_batch(
            direct_exec_enabled=True,
            step_mode=False,
            has_ssh_connection=False,
        ).is_ready

    def test_advance_after_parallel_batch_moves_cursor_past_completed_batch(self):
        s = TerminalAiSession()
        s.plan = [{"id": 1}, {"id": 2}, {"id": 3}]

        assert s.advance_after_parallel_batch([0, 1]) is True

        assert s.plan_index == 2

    def test_advance_after_parallel_batch_ignores_negative_or_stale_indices(self):
        s = TerminalAiSession()
        s.plan = [{"id": 1}, {"id": 2}]
        s.plan_index = 1

        assert s.advance_after_parallel_batch([-1]) is False
        assert s.advance_after_parallel_batch([0]) is False

        assert s.plan_index == 1

    def test_prepare_next_step_empty_when_queue_finished(self):
        s = TerminalAiSession()

        step = s.prepare_next_step()

        assert step.action == "empty"
        assert step.item is None

    def test_prepare_next_step_advances_past_terminal_status(self):
        s = TerminalAiSession()
        s.plan = [{"id": 1, "status": "done"}, {"id": 2, "cmd": "hostname"}]

        step = s.prepare_next_step()

        assert step.action == "advance"
        assert s.plan_index == 1

    def test_prepare_next_step_skips_blocked_command(self):
        s = TerminalAiSession()
        s.plan = [{"id": 5, "cmd": "rm -rf /", "reason": "dangerous", "blocked": True}]

        step = s.prepare_next_step()

        assert step.action == "blocked_skipped"
        assert step.command_id == 5
        assert step.command == "rm -rf /"
        assert step.reason == "dangerous"
        assert s.plan[0]["status"] == "skipped"
        assert s.plan_index == 1

    def test_prepare_next_step_waits_for_confirmation_without_advancing(self):
        s = TerminalAiSession()
        s.plan = [{"id": 6, "cmd": "systemctl restart app", "requires_confirm": True, "reason": "restart"}]

        step = s.prepare_next_step()

        assert step.action == "waiting_confirm"
        assert step.command_id == 6
        assert step.reason == "restart"
        assert s.plan[0]["status"] == "pending_confirm"
        assert s.plan_index == 0

    def test_prepare_next_step_marks_current_command_running(self):
        s = TerminalAiSession()
        s.plan = [{"id": 7, "cmd": "uptime"}]

        step = s.prepare_next_step()

        assert step.action == "run"
        assert step.command_id == 7
        assert step.command == "uptime"
        assert step.item is s.plan[0]
        assert s.plan[0]["status"] == "running"
        assert s.plan_index == 0

    def test_mark_current_done_updates_matching_cursor_and_advances(self):
        s = TerminalAiSession()
        s.plan = [{"id": 8, "cmd": "uptime", "status": "running"}]

        assert s.mark_current_done(8, 0, "load average: 0.1") is True

        assert s.plan[0]["status"] == "done"
        assert s.plan[0]["exit_code"] == 0
        assert s.plan[0]["output_snippet"] == "load average: 0.1"
        assert s.plan_index == 1

    def test_mark_current_done_noops_when_cursor_changed(self):
        s = TerminalAiSession()
        s.plan = [{"id": 8, "cmd": "uptime", "status": "running"}]

        assert s.mark_current_done(99, 1, "bad") is False

        assert s.plan[0]["status"] == "running"
        assert "exit_code" not in s.plan[0]
        assert s.plan_index == 0

    def test_mark_plan_index_done_updates_exact_item_without_advancing_cursor(self):
        s = TerminalAiSession()
        s.plan = [{"id": 1, "status": "running"}, {"id": 2, "status": "running"}]

        assert s.mark_plan_index_done(1, 2, "failed") is True

        assert s.plan[0]["status"] == "running"
        assert s.plan[1]["status"] == "done"
        assert s.plan[1]["exit_code"] == 2
        assert s.plan[1]["output_snippet"] == "failed"
        assert s.plan_index == 0

    def test_mark_plan_index_done_rejects_negative_index(self):
        s = TerminalAiSession()
        s.plan = [{"id": 1, "status": "running"}]

        assert s.mark_plan_index_done(-1, 1, "bad") is False

        assert s.plan[0]["status"] == "running"
        assert "exit_code" not in s.plan[0]

    def test_skip_remaining_marks_only_non_terminal_items(self):
        s = TerminalAiSession()
        s.plan = [
            {"id": 1, "status": "done"},
            {"id": 2, "status": "pending"},
            {"id": 3, "status": "skipped"},
            {"id": 4},
        ]
        s.plan_index = 1

        skipped = s.skip_remaining()

        assert skipped == [2, 4]
        assert s.plan[1]["status"] == "skipped"
        assert s.plan[2]["status"] == "skipped"
        assert s.plan[3]["status"] == "skipped"
        assert s.plan_index == 4


class TestTerminalAiQueueProjections:
    def test_remaining_commands_after_current_preserves_command_payloads_after_cursor(self):
        s = TerminalAiSession()
        s.plan = [
            {"cmd": "current", "status": "running"},
            {"cmd": " next ", "status": "pending"},
            {"cmd": "done", "status": "done"},
            {"cmd": "later"},
        ]

        assert s.remaining_commands_after_current() == [" next ", "later"]

    def test_remaining_commands_from_cursor_normalizes_command_text(self):
        s = TerminalAiSession()
        s.plan = [
            {"cmd": " current ", "status": "running"},
            {"cmd": "skipped", "status": "skipped"},
            {"cmd": " next "},
        ]

        assert s.remaining_commands_from_cursor() == ["current", "next"]

    def test_snapshot_done_items_projects_and_caches_completed_commands(self):
        s = TerminalAiSession()
        s.plan = [
            {"cmd": " uptime ", "status": "done", "exit_code": 0, "output_snippet": " ok "},
            {"cmd": "pending", "status": "pending", "exit_code": 1, "output_snippet": "no"},
            {"cmd": "big", "status": "done", "exit_code": 2, "output_snippet": "abcdef"},
        ]

        done_items = s.snapshot_done_items(output_limit=3)

        assert done_items == [
            {"cmd": "uptime", "exit_code": 0, "output": "ok"},
            {"cmd": "big", "exit_code": 2, "output": "abc"},
        ]
        assert s.last_done_items == done_items

    def test_done_items_with_output_filters_empty_outputs(self):
        done_items = [
            {"cmd": "a", "output": "x"},
            {"cmd": "b", "output": "  "},
            {"cmd": "c"},
        ]

        assert TerminalAiSession.done_items_with_output(done_items) == [{"cmd": "a", "output": "x"}]
