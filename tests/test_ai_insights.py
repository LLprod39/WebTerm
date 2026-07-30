"""Tests for the LLM analysis layer (servers.monitoring.ai_insights) with a mocked LLM."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from servers.models import Server, ServerAiInsight, ServerAlert, ServerMetricSample
from servers.monitoring import ai_insights
from servers.monitoring.ai_insights import (
    build_server_context,
    parse_verdict,
    run_ai_insights_for_servers,
    run_server_insight,
)

FAKE_ANALYSIS = (
    "## Вердикт\nСервер деградирует.\nУровень риска: Высокий\n"
    "## Наблюдения\n- диск растёт\n## Что сделать\n- почистить логи"
)


@pytest.fixture
def fake_llm(monkeypatch):
    calls: list[dict] = []

    def _fake(prompt: str, *, system_prompt: str) -> tuple[str, str]:
        calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return FAKE_ANALYSIS, "test-model"

    monkeypatch.setattr(ai_insights, "_call_llm", _fake)
    return calls


def _make_server(username: str, host: str = "10.0.9.1") -> Server:
    owner = User.objects.create_user(username=username, password="x")
    return Server.objects.create(
        user=owner, name=f"srv-{username}", host=host, username="root", server_type="ssh", is_active=True
    )


def test_parse_verdict_levels():
    assert parse_verdict("Уровень риска: Критический") == "critical"
    assert parse_verdict("...\nУровень риска: ВЫСОКИЙ\n...") == "high"
    assert parse_verdict("уровень риска — средний") == "medium"
    assert parse_verdict("Уровень риска: Низкий") == "low"
    assert parse_verdict("никакого формата") == "unknown"


@pytest.mark.django_db
def test_build_server_context_contains_metrics_and_is_stable():
    server = _make_server("ai-ctx")
    ServerMetricSample.objects.create(
        server=server,
        cpu_percent=55.0,
        memory_percent=70.0,
        memory_total_mb=8000,
        memory_available_mb=2400,
        disk_mounts=[{"mount": "/", "percent": 81.0, "used_gb": 81.0, "total_gb": 100.0}],
        journal_err_10m=3,
    )
    now = timezone.now()
    context1, fp1 = build_server_context(server, now=now)
    context2, fp2 = build_server_context(server, now=now)

    assert "srv-ai-ctx" in context1
    assert "81.0%" in context1
    assert fp1 == fp2  # coarse fingerprint is deterministic

    ServerAlert.objects.create(server=server, alert_type="disk", severity="warning", title="Disk 81%")
    _, fp3 = build_server_context(server, now=now)
    assert fp3 != fp1  # a new alert changes the signature


@pytest.mark.django_db
def test_run_server_insight_reuses_unchanged_context(fake_llm):
    server = _make_server("ai-reuse")
    ServerMetricSample.objects.create(server=server, cpu_percent=10.0, memory_percent=20.0)

    first = run_server_insight(server)
    assert first is not None
    assert first.verdict == ServerAiInsight.VERDICT_HIGH
    assert first.content == FAKE_ANALYSIS
    assert first.model_used == "test-model"
    assert len(fake_llm) == 1

    second = run_server_insight(server)
    assert second is not None
    assert second.id == first.id  # reused, no new LLM call
    assert len(fake_llm) == 1

    third = run_server_insight(server, force=True)
    assert third is not None
    assert third.id != first.id
    assert len(fake_llm) == 2


@pytest.mark.django_db
def test_fleet_pass_dedupes_endpoints_and_builds_digest(fake_llm):
    owner_a = User.objects.create_user(username="ai-fleet-a", password="x")
    owner_b = User.objects.create_user(username="ai-fleet-b", password="x")
    Server.objects.create(
        user=owner_a, name="fleet-a", host="10.0.9.5", username="root", server_type="ssh", is_active=True
    )
    Server.objects.create(
        user=owner_b, name="fleet-b", host="10.0.9.5", username="ubuntu", server_type="ssh", is_active=True
    )

    summary = run_ai_insights_for_servers()
    # One endpoint analysis + one fleet digest = two LLM calls total.
    assert summary["analyzed"] == 1
    assert len(fake_llm) == 2
    assert ServerAiInsight.objects.filter(kind=ServerAiInsight.KIND_SERVER).count() == 1
    assert ServerAiInsight.objects.filter(kind=ServerAiInsight.KIND_FLEET).count() == 1
    assert "fleet-a" in fake_llm[1]["prompt"]


@pytest.mark.django_db
def test_admin_insights_payload_includes_ai_block(client, fake_llm):
    cache.clear()
    server = _make_server("ai-payload")
    run_server_insight(server, force=True)

    staff = User.objects.create_user(username="ai-staff", password="x", is_staff=True)
    client.force_login(staff)
    payload = client.get(reverse("servers:admin_insights") + "?refresh=1").json()

    assert payload["ai"]["enabled"] is True
    endpoint_key = payload["servers"][0]["endpoint_key"]
    insight = payload["ai"]["by_endpoint"][endpoint_key]
    assert insight["verdict"] == "high"
    assert "Вердикт" in insight["content"]


@pytest.mark.django_db
def test_ai_run_endpoint_requires_staff_and_queues(client, monkeypatch):
    cache.clear()
    _make_server("ai-run")

    plain = User.objects.create_user(username="ai-plain", password="x")
    client.force_login(plain)
    assert client.post(reverse("servers:admin_insights_ai_run")).status_code == 403

    ran: dict = {}

    def _fake_run(server_ids=None, *, force=False, max_runs=None):
        ran["server_ids"] = server_ids
        ran["force"] = force
        return {"enabled": 1, "analyzed": 1, "reused": 0, "errors": 0}

    class _InlineThread:
        def __init__(self, *, target, daemon=None, name=None):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr("servers.views.server_insights.run_ai_insights_for_servers", _fake_run)
    monkeypatch.setattr("servers.views.server_insights.threading.Thread", _InlineThread)

    staff = User.objects.create_user(username="ai-run-staff", password="x", is_staff=True)
    client.force_login(staff)
    response = client.post(
        reverse("servers:admin_insights_ai_run"),
        data='{"force": true}',
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["queued"] is True
    assert ran == {"server_ids": None, "force": True}
    # Lock is released by the worker so the next run can start.
    assert cache.get("servers_admin_ai_insights_running") is None
