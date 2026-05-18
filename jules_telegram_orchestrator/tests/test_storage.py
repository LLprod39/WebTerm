from pathlib import Path

from jules_tg_orchestrator.storage import Storage


def test_storage_tracks_project_task_and_events(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "bot.sqlite3")
    try:
        task_id = storage.create_task(
            chat_id=123,
            title="Fix memory tests",
            description="Add focused coverage for memory policy updates",
            project_root="C:\\WebTrerm",
            source="sources/github-owner-repo",
            branch="main",
            status="READY",
        )
        storage.add_task_event(task_id, kind="delegated", message="Delegated to Jules")
        storage.update_task(task_id, status="DELEGATED", branch="codex/task-1")
        run_id = storage.create_agent_run(task_id=task_id, agent_kind="gemini_cli")
        storage.update_agent_run(run_id, status="COMPLETED", summary="Done", output="Full output")
        storage.set_state("codex_chief_session_id", "thread-1")
        chief_run_id = storage.create_chief_run(
            chat_id=123,
            user_id=456,
            message="Проверь статус",
            status_message_id=789,
            thread_id="thread-1",
        )
        storage.update_chief_run(chief_run_id, status="COMPLETED", response="Готово", thread_id="thread-1")
        plan_id = storage.create_pending_plan(
            chat_id=123,
            user_id=456,
            message="Сделай задачу",
            plan_text="План",
        )
        storage.update_pending_plan(plan_id, status="APPROVED", chief_run_id=chief_run_id)

        task = storage.get_task(task_id)
        events = storage.list_task_events(task_id)
        runs = storage.list_task_agent_runs(task_id)
        chief_runs = storage.list_chief_runs()
        plans = storage.list_pending_plans()

        assert task is not None
        assert task["status"] == "DELEGATED"
        assert task["branch"] == "codex/task-1"
        assert [event["kind"] for event in events] == ["delegated", "created"]
        assert runs[0]["agent_kind"] == "gemini_cli"
        assert runs[0]["status"] == "COMPLETED"
        assert storage.get_state("codex_chief_session_id") == "thread-1"
        assert chief_runs[0]["status"] == "COMPLETED"
        assert chief_runs[0]["response"] == "Готово"
        assert plans[0]["status"] == "APPROVED"
        assert plans[0]["chief_run_id"] == chief_run_id
    finally:
        storage.close()
