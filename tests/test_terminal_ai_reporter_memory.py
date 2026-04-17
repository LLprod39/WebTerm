"""Tests for servers.services.terminal_ai.reporter + memory (F2-3)."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from servers.models import Server, ServerKnowledge
from servers.services.terminal_ai.memory import (
    _dedup_clean_list,
    sanitize_memory_line,
    save_server_profile_sync,
    select_memory_candidate_commands,
    should_extract_memory,
)
from servers.services.terminal_ai.reporter import (
    build_fallback_report,
    compute_report_status,
)

# ---------------------------------------------------------------------------
# reporter.py — pure helpers
# ---------------------------------------------------------------------------


class TestComputeReportStatus:
    def test_empty_list_is_warning(self):
        # No data → warning is safest default
        assert compute_report_status([]) == "warning"

    def test_all_ok_returns_ok(self):
        assert (
            compute_report_status([{"exit_code": 0}, {"exit_code": 0}, {"exit_code": 0}])
            == "ok"
        )

    def test_only_interrupts_is_warning(self):
        # exit=130 = captured streaming; alone it is not "ok"
        assert compute_report_status([{"exit_code": 130}]) == "warning"

    def test_mix_ok_and_interrupted_returns_ok(self):
        assert compute_report_status([{"exit_code": 0}, {"exit_code": 130}]) == "ok"

    def test_majority_failed_returns_error(self):
        assert (
            compute_report_status(
                [
                    {"exit_code": 0},
                    {"exit_code": 1},
                    {"exit_code": 2},
                    {"exit_code": 127},
                ]
            )
            == "error"
        )

    def test_single_failure_with_ok_returns_warning(self):
        assert (
            compute_report_status(
                [{"exit_code": 0}, {"exit_code": 0}, {"exit_code": 0}, {"exit_code": 127}]
            )
            == "warning"
        )


class TestBuildFallbackReport:
    def test_all_ok_report(self):
        report = build_fallback_report([{"exit_code": 0}, {"exit_code": 0}])
        assert "успешно" in report.lower() or "код выхода 0" in report

    def test_with_failures_includes_codes(self):
        report = build_fallback_report([{"exit_code": 0}, {"exit_code": 127}])
        assert "127" in report

    def test_empty_list_still_produces_text(self):
        report = build_fallback_report([])
        assert report  # non-empty fallback string


# ---------------------------------------------------------------------------
# memory.py — pure helpers
# ---------------------------------------------------------------------------


class TestSanitizeMemoryLine:
    def test_strips_newlines(self):
        assert sanitize_memory_line("line1\nline2\r\nline3") == "line1 line2  line3"

    def test_truncates_to_400(self):
        long = "x" * 600
        assert len(sanitize_memory_line(long)) == 400

    def test_strips_surrounding_whitespace(self):
        assert sanitize_memory_line("   hello world   ") == "hello world"

    def test_empty_input(self):
        assert sanitize_memory_line("") == ""
        assert sanitize_memory_line(None) == ""  # type: ignore[arg-type]


class TestDedupCleanList:
    def test_case_insensitive_dedup(self):
        result = _dedup_clean_list(["Nginx 1.24", "NGINX 1.24", "port 443"], limit=10)
        assert result == ["Nginx 1.24", "port 443"]

    def test_limit_respected(self):
        items = [f"fact-{i}" for i in range(20)]
        result = _dedup_clean_list(items, limit=5)
        assert len(result) == 5

    def test_empty_and_whitespace_filtered(self):
        assert _dedup_clean_list(["", "   ", "real"], limit=10) == ["real"]


class TestSelectMemoryCandidateCommands:
    def test_trivial_commands_filtered(self):
        rows = [
            {"cmd": "ls", "output": "", "exit_code": 0},
            {"cmd": "pwd", "output": "/root", "exit_code": 0},
        ]
        # Heuristic should drop these as trivial.
        assert select_memory_candidate_commands(rows) == []

    def test_substantial_command_kept(self):
        rows = [
            {
                "cmd": "docker ps --format '{{.Names}}'",
                "output": "nginx\npostgres\nredis\n",
                "exit_code": 0,
            }
        ]
        result = select_memory_candidate_commands(rows)
        assert len(result) == 1
        assert "docker ps" in result[0]["cmd"]


# ---------------------------------------------------------------------------
# memory.py — sync Django ORM writer (F2-3)
# ---------------------------------------------------------------------------


def _make_server(user: User) -> Server:
    return Server.objects.create(
        user=user,
        name="mem-srv",
        host="10.0.0.99",
        username="root",
        auth_method="password",
    )


@pytest.mark.django_db
def test_save_server_profile_sync_writes_profile_and_issues():
    user = User.objects.create_user(username="mem-writer", password="x")
    server = _make_server(user)

    result = save_server_profile_sync(
        user_id=user.id,
        server_id=server.id,
        summary="nginx 1.24 running on port 80/443",
        facts=["nginx 1.24", "port 443 open", "ubuntu 22.04"],
        issues=["disk usage 85%"],
    )

    assert result["saved"] == 2
    assert "Профиль сервера (авто)" in result["titles"]
    assert "Текущие риски (авто)" in result["titles"]

    profile = ServerKnowledge.objects.filter(server=server, title="Профиль сервера (авто)").first()
    assert profile is not None
    assert "nginx 1.24" in profile.content
    assert profile.confidence == 0.88

    risks = ServerKnowledge.objects.filter(server=server, title="Текущие риски (авто)").first()
    assert risks is not None
    assert "disk usage 85%" in risks.content


@pytest.mark.django_db
def test_save_server_profile_sync_skips_when_no_durable_signals():
    """should_persist_ai_memory guard: no facts + no issues → no write."""
    user = User.objects.create_user(username="mem-empty", password="x")
    server = _make_server(user)

    result = save_server_profile_sync(
        user_id=user.id,
        server_id=server.id,
        summary="ephemeral chat summary",
        facts=[],
        issues=[],
    )

    assert result["saved"] == 0
    assert ServerKnowledge.objects.filter(server=server).count() == 0


@pytest.mark.django_db
def test_save_server_profile_sync_handles_missing_server():
    user = User.objects.create_user(username="mem-missing", password="x")
    result = save_server_profile_sync(
        user_id=user.id,
        server_id=999_999,
        summary="x",
        facts=["a"],
        issues=[],
    )
    # F2-7: layered memory bridge is part of the return shape.
    assert result == {"saved": 0, "titles": [], "layered": {"facts": 0, "incidents": 0}}


@pytest.mark.django_db
def test_save_server_profile_sync_bridge_to_layered_memory(monkeypatch):
    """F2-7: after writing ServerKnowledge, facts/issues also go through the
    layered memory store. We stub DjangoServerMemoryStore so we don't hit
    the full ingestion pipeline in this unit test."""
    user = User.objects.create_user(username="mem-bridge", password="x")
    server = _make_server(user)

    upsert_calls: list[tuple[int, dict]] = []
    incident_calls: list[tuple[int, dict]] = []

    class StubStore:
        def _upsert_server_fact_sync(self, server_id, fact, **kwargs):  # noqa: ANN001
            upsert_calls.append((server_id, dict(fact)))
            return "event-fact"

        def _record_incident_sync(self, server_id, incident, **kwargs):  # noqa: ANN001
            incident_calls.append((server_id, dict(incident)))
            return "event-incident"

    import servers.services.terminal_ai.memory as mod

    monkeypatch.setattr(
        "servers.adapters.memory_store.DjangoServerMemoryStore",
        StubStore,
    )

    result = mod.save_server_profile_sync(
        user_id=user.id,
        server_id=server.id,
        summary="nginx profile",
        facts=["nginx 1.24", "python 3.11"],
        issues=["disk 85%"],
    )

    assert result["saved"] == 2
    assert result["layered"] == {"facts": 2, "incidents": 1}

    # Facts ingested with category "profile"
    assert len(upsert_calls) == 2
    assert all(c[0] == server.id for c in upsert_calls)
    fact_contents = [c[1]["content"] for c in upsert_calls]
    assert "nginx 1.24" in fact_contents
    assert "python 3.11" in fact_contents
    assert all(c[1]["category"] == "profile" for c in upsert_calls)

    # Issues ingested with category "issues"
    assert len(incident_calls) == 1
    assert incident_calls[0][0] == server.id
    assert incident_calls[0][1]["content"] == "disk 85%"
    assert incident_calls[0][1]["category"] == "issues"


@pytest.mark.django_db
def test_save_server_profile_sync_layered_bridge_can_be_disabled(monkeypatch):
    """F2-7: ``bridge_to_layered_memory=False`` skips agent_kernel ingestion."""
    user = User.objects.create_user(username="mem-nobridge", password="x")
    server = _make_server(user)

    called = {"count": 0}

    class StubStore:
        def _upsert_server_fact_sync(self, *args, **kwargs):  # noqa: ANN001, ANN003
            called["count"] += 1
            return ""

        def _record_incident_sync(self, *args, **kwargs):  # noqa: ANN001, ANN003
            called["count"] += 1
            return ""

    monkeypatch.setattr(
        "servers.adapters.memory_store.DjangoServerMemoryStore",
        StubStore,
    )

    import servers.services.terminal_ai.memory as mod

    result = mod.save_server_profile_sync(
        user_id=user.id,
        server_id=server.id,
        summary="x",
        facts=["nginx"],
        issues=[],
        bridge_to_layered_memory=False,
    )

    assert result["saved"] == 1
    assert result["layered"] == {"facts": 0, "incidents": 0}
    assert called["count"] == 0  # bridge not invoked


@pytest.mark.django_db
def test_save_server_profile_sync_only_facts_writes_profile_only():
    user = User.objects.create_user(username="mem-facts", password="x")
    server = _make_server(user)

    result = save_server_profile_sync(
        user_id=user.id,
        server_id=server.id,
        summary="x",
        facts=["python 3.11"],
        issues=[],
    )

    assert result["saved"] == 1
    assert result["titles"] == ["Профиль сервера (авто)"]
    assert ServerKnowledge.objects.filter(server=server).count() == 1


# ---------------------------------------------------------------------------
# should_extract_memory — A2 cost-saver heuristic
# ---------------------------------------------------------------------------


class TestShouldExtractMemory:
    def test_empty_list_skips(self):
        assert should_extract_memory([]) is False
        assert should_extract_memory(None) is False

    def test_single_command_skips(self):
        assert should_extract_memory([{"cmd": "apt install nginx", "exit_code": 0}]) is False

    def test_all_noise_zero_exit_skips(self):
        items = [
            {"cmd": "ls -la", "exit_code": 0},
            {"cmd": "pwd", "exit_code": 0},
            {"cmd": "whoami", "exit_code": 0},
        ]
        assert should_extract_memory(items) is False

    def test_non_zero_exit_triggers_extract(self):
        items = [
            {"cmd": "ls", "exit_code": 0},
            {"cmd": "systemctl status nginx", "exit_code": 3},
        ]
        assert should_extract_memory(items) is True

    def test_durable_command_triggers_extract(self):
        items = [
            {"cmd": "ls", "exit_code": 0},
            {"cmd": "apt install -y htop", "exit_code": 0},
        ]
        assert should_extract_memory(items) is True

    def test_sudo_prefix_recognized(self):
        items = [
            {"cmd": "ls", "exit_code": 0},
            {"cmd": "sudo systemctl restart nginx", "exit_code": 0},
        ]
        assert should_extract_memory(items) is True

    def test_mixed_non_noise_non_durable_keeps_extract(self):
        # Command we don't classify either way — safer to keep extraction.
        items = [
            {"cmd": "curl https://api.example", "exit_code": 0},
            {"cmd": "jq .version response.json", "exit_code": 0},
        ]
        assert should_extract_memory(items) is True

    def test_ctrl_c_exit_130_does_not_count_as_failure(self):
        # User interrupted the command — not a real failure worth learning.
        items = [
            {"cmd": "ls", "exit_code": 0},
            {"cmd": "tail -f /var/log/syslog", "exit_code": 130},
        ]
        # All noise + interrupt → still skip.
        assert should_extract_memory(items) is False
