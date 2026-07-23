from __future__ import annotations

from servers.services.terminal_events import (
    ai_command_status,
    ai_direct_output,
    ai_error,
    ai_explanation,
    ai_install_progress,
    ai_parallel_batch,
    ai_question,
    ai_recovery,
    ai_report,
    ai_response,
    ai_status,
)


def test_ai_status_compacts_none_fields():
    assert ai_status("running", id=1, unused=None) == {
        "type": "ai_status",
        "status": "running",
        "id": 1,
    }


def test_ai_error_payload():
    assert ai_error("boom") == {"type": "ai_error", "message": "boom"}


def test_ai_response_defaults():
    assert ai_response(assistant_text="ok") == {
        "type": "ai_response",
        "mode": "answer",
        "assistant_text": "ok",
        "commands": [],
    }


def test_ai_command_status_optional_fields():
    assert ai_command_status(item_id=5, status="done", exit_code=0, streaming=False) == {
        "type": "ai_command_status",
        "id": 5,
        "status": "done",
        "exit_code": 0,
        "streaming": False,
    }


def test_ai_parallel_batch_defaults_count_to_ids_length():
    assert ai_parallel_batch(status="start", ids=[1, 2]) == {
        "type": "ai_parallel_batch",
        "status": "start",
        "ids": [1, 2],
        "count": 2,
    }


def test_remaining_event_builders_shape_payloads():
    assert ai_report(report="r", status="ok")["type"] == "ai_report"
    assert ai_explanation(item_id=1, command="df", explanation="disk")["type"] == "ai_explanation"
    assert ai_direct_output(item_id=1, command="true", output="", exit_code=0)["type"] == "ai_direct_output"
    assert (
        ai_recovery(
            original_cmd="netstat",
            new_cmd="ss",
            new_id=2,
            why="missing",
            requires_confirm=False,
            reason="",
            streaming=False,
        )["type"]
        == "ai_recovery"
    )
    assert ai_question(q_id="q1", question="continue?", command="cmd", exit_code=1)["type"] == "ai_question"
    assert ai_install_progress(command="apt install nginx", elapsed=12, output_tail="Installing") == {
        "type": "ai_install_progress",
        "cmd": "apt install nginx",
        "elapsed": 12,
        "output_tail": "Installing",
    }
