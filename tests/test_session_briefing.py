from __future__ import annotations

from servers.services.terminal_ai.session_briefing import (
    append_briefing_entry,
    build_briefing_entry,
    narrate_command,
    render_session_briefing,
)
from servers.services.terminal_ai.session_context import build_nova_context_bundle


def test_cd_narration_and_secret_redaction():
    text = narrate_command(command="cd /tmp", cwd="/home/op", exit_code=0, source="session")
    assert "перешёл в каталог `/tmp`" in text
    assert "Оператор" in text

    redacted = narrate_command(
        command="export TOKEN=super-secret-value",
        cwd="/",
        exit_code=0,
        source="nova",
    )
    assert "super-secret-value" not in redacted
    assert "***" in redacted
    assert "Nova" in redacted


def test_nonzero_exit_includes_output_hint():
    text = narrate_command(
        command="systemctl restart nginx",
        cwd="/",
        exit_code=1,
        source="ai",
        output_tail="Unit not found",
    )
    assert "ошибкой" in text
    assert "Unit not found" in text


def test_render_splits_human_and_nova():
    entries = [
        build_briefing_entry(command="cd /tmp", cwd="/home", exit_code=0, source="session"),
        build_briefing_entry(command="ls", cwd="/tmp", exit_code=0, source="nova"),
    ]
    rendered = render_session_briefing(entries)
    assert "Что уже происходило в этой сессии" in rendered
    assert "Действия оператора" in rendered
    assert "Действия Nova" in rendered
    assert "перешёл" in rendered
    assert "просмотрел содержимое" in rendered


def test_append_bounds_entries():
    entries = []
    for index in range(20):
        entries = append_briefing_entry(
            entries,
            build_briefing_entry(command=f"echo {index}", cwd="/", exit_code=0, source="session"),
        )
    assert len(entries) == 12
    assert entries[0]["command"] == "echo 8"


def test_context_bundle_prefers_briefing_over_raw_commands():
    bundle = build_nova_context_bundle(
        snapshot={"cwd": "/tmp", "user": "op", "hostname": "box"},
        live_activity=[{"command": "ls", "cwd": "/tmp", "exit_code": 0, "source": "session"}],
        persisted_activity=[],
        include_session_context=True,
        include_recent_activity=True,
        briefing_entries=[
            build_briefing_entry(command="ls", cwd="/tmp", exit_code=0, source="session"),
        ],
        occupancy_note="Строка ввода общего терминала пустая — Fast может печатать команды.",
    )
    assert "Что уже происходило" in bundle.recent_activity_context
    assert "cwd=/tmp | exit=0" not in bundle.recent_activity_context
    assert "Fast может печатать" in bundle.recent_activity_context
    assert bundle.ui_payload["recent_activity"][0]["summary"]
