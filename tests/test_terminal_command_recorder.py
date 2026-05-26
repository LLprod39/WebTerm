from __future__ import annotations

from servers.models import ServerCommandHistory
from servers.services import terminal_command_recorder as recorder


def test_append_live_terminal_activity_bounds_and_sanitizes_fields() -> None:
    entries = [{"command": f"old-{i}", "cwd": "/", "exit_code": 0, "source": "history"} for i in range(3)]
    updated = recorder.append_live_terminal_activity(
        entries,
        command="x" * 2100,
        cwd="/tmp/" + ("y" * 600),
        exit_code=1,
        source="live_session_with_long_suffix",
        max_entries=3,
    )

    assert [item["command"] for item in updated[:2]] == ["old-1", "old-2"]
    assert updated[-1]["command"] == "x" * 2000
    assert len(updated[-1]["cwd"]) == 500
    assert updated[-1]["exit_code"] == 1
    assert updated[-1]["source"] == "live_session_with_long_suffix"


def test_append_live_terminal_activity_ignores_empty_command() -> None:
    original = [{"command": "ls", "cwd": "/", "exit_code": 0, "source": "history"}]
    assert recorder.append_live_terminal_activity(original, command="", cwd="/", exit_code=0, source="x") == original


def test_persist_manual_terminal_command_result_uses_canonical_history_service(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(recorder, "save_command_history_entry", lambda **kwargs: calls.append(kwargs))

    recorder.persist_manual_terminal_command_result(
        user_id=1,
        server_id=2,
        session_id="term-1",
        command="uptime",
        output="ok",
        exit_code=0,
        cwd="/srv",
    )

    assert calls == [
        {
            "server_id": 2,
            "user_id": 1,
            "session_id": "term-1",
            "cwd": "/srv",
            "command": "uptime",
            "output": "ok",
            "exit_code": 0,
        }
    ]


def test_persist_agent_command_history_redacts_and_marks_actor(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(recorder, "save_command_history_entry", lambda **kwargs: calls.append(kwargs))

    recorder.persist_agent_command_history(
        user_id=1,
        server_id=2,
        command="deploy",
        output_snippet="Authorization: Bearer sk-secret-token",
        exit_code=0,
    )

    assert calls[0]["actor_kind"] == ServerCommandHistory.ACTOR_AGENT
    assert calls[0]["source_kind"] == ServerCommandHistory.SOURCE_AGENT
    assert calls[0]["command"] == "deploy"
    assert "sk-secret-token" not in calls[0]["output"]
