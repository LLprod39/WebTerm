from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from servers.models import AgentRun, AgentRunArtifact, AgentRunEvent, ServerAgent
from tests.servers_api_smoke_harness import create_server, grant_feature


def _owner_client(username: str = "report-v2-owner") -> tuple[User, Client]:
    user = User.objects.create_user(username=username, password="x")
    grant_feature(user, "agents")
    client = Client()
    client.force_login(user)
    return user, client


def _run(user: User, *, status: str = AgentRun.STATUS_COMPLETED, report: str = "# Report") -> AgentRun:
    server = create_server(user, name=f"{user.username}-node")
    agent = ServerAgent.objects.create(
        user=user,
        name="Report v2 agent",
        mode=ServerAgent.MODE_FULL,
        goal="Inspect the selected server and explain the evidence",
    )
    agent.servers.set([server])
    return AgentRun.objects.create(
        agent=agent,
        server=server,
        user=user,
        status=status,
        final_report=report,
        completed_at=timezone.now() if status in {AgentRun.STATUS_COMPLETED, AgentRun.STATUS_FAILED} else None,
    )


@pytest.mark.django_db
def test_report_v2_2156_separates_failed_lifecycle_from_partial_user_outcome():
    user, client = _owner_client("report-v2-2156")
    report = """# Частичная проверка логов Docker-контейнеров

На сервере обнаружен 21 контейнер, но логи проверены только у двух контейнеров из 21.

## Ключевые находки
- Два проверенных контейнера не вернули записей за последние 24 часа.

## Проблемы и риски
- Логи 19 контейнеров не проверены, поэтому ошибки могли остаться необнаруженными.

## Рекомендации
- Проверить оставшиеся 19 контейнеров. - Изучить завершение контейнера с кодом 137. - Проверить logging driver.

**Статус:** Частичный успех
---
Outcome: failed — LLM call failed
"""
    run = _run(user, status=AgentRun.STATUS_FAILED, report=report)
    run.id = 2156
    run.ai_analysis = "LLM call failed"
    run.duration_ms = 214_000
    run.execution_outcome = {
        "outcome": "failed",
        "status": "failed",
        "reason": "LLM call failed",
        "exit_reason": "llm_error",
        "tool_call_count": 6,
        "report_generation": {"status": "failed", "error": "LLM call failed"},
    }
    run.iterations_log = [{"iteration": index, "action": "ssh_execute"} for index in range(1, 8)]
    run.tool_calls = [{"tool": "ssh_execute", "result": "no output"} for _ in range(6)]
    run.total_iterations = 7
    run.save(force_insert=True)
    run.agent.report_delivery = {"telegram": {"enabled": True, "chat_id": ""}}
    run.agent.save(update_fields=["report_delivery"])
    for index in range(45):
        AgentRunEvent.objects.create(
            run=run,
            event_type="agent_task_failed" if index in {20, 40} else "agent_action",
            message=f"signal {index + 1}",
            payload={"severity": "critical"} if index in {20, 40} else {},
        )
    AgentRunEvent.objects.create(
        run=run,
        event_type="agent_report_delivery_skipped",
        message="Telegram bot token or chat id is not configured.",
        payload={"reason": "telegram_not_configured", "channel": "telegram"},
    )

    response = client.get("/servers/api/agents/runs/2156/report/v2/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["lifecycle"]["status"] == "failed"
    assert payload["outcome"]["status"] == "partial"
    assert payload["outcome"]["exit_reason"] == "llm_error"
    assert payload["outcome"]["details"]["technical_outcome"] == "failed"
    assert payload["report_generation"]["status"] == "ready_with_fallback"
    assert payload["report_generation"]["generated_at"]
    assert payload["delivery"]["status"] == "blocked"
    assert payload["delivery"]["configured"] is False
    assert payload["delivery"]["can_retry"] is False
    assert payload["delivery"]["blocked_reason"] == "telegram_not_configured"
    assert payload["evidence_state"]["coverage"]["checked"] == 2
    assert payload["evidence_state"]["coverage"]["total"] == 21
    assert len(payload["actions"]) == 3
    assert [phase["id"] for phase in payload["phases"]] == ["goal", "action", "observation", "conclusion"]
    assert {item["id"] for item in payload["indicators"]} >= {"outcome", "report_delivery"}
    assert payload["counts"]["events_total"] == 46
    assert payload["counts"]["tool_calls"] == 6
    assert payload["counts"]["operations_unknown"] == 6
    assert next(item for item in payload["indicators"] if item["id"] == "operations")["value"] == "6"
    assert payload["report_revision"].startswith("r2-")
    assert payload["event_high_watermark"]["sequence_no"] == 46
    assert "events" not in payload and "activity" not in payload and "markdown" not in payload
    assert payload["data"] is None
    assert len(response.content) < 25_000
    assert b"7/7" not in response.content


@pytest.mark.django_db
def test_legacy_adapter_is_read_only_and_understands_numbered_sections():
    user, client = _owner_client("report-v2-legacy")
    run = _run(
        user,
        report="""## 1. Резюме
Сервер проверен; сохранённый документ не содержит kernel outcome.

## 2. Обнаружения
- Все четыре read-only команды завершились с кодом 0.

## 5. Рекомендации
- Проверить результат при следующем плановом запуске.
""",
    )
    run.commands_output = [{"cmd": f"check-{index}", "exit_code": 0, "stdout": "ok"} for index in range(4)]
    run.report_payload = {"legacy_marker": "preserve"}
    run.save(update_fields=["commands_output", "report_payload"])

    response = client.get(f"/servers/api/agents/runs/{run.id}/report/v2/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["outcome"]["status"] == "inconclusive"
    assert payload["outcome"]["reason_source"] == "legacy_inference"
    assert [item["title"] for item in payload["findings"]] == [
        "Все четыре read-only команды завершились с кодом 0."
    ]
    assert [item["title"] for item in payload["actions"]] == [
        "Проверить результат при следующем плановом запуске."
    ]
    assert payload["counts"]["operations_succeeded"] == 4
    run.refresh_from_db()
    assert run.execution_outcome == {}
    assert run.report_payload == {"legacy_marker": "preserve"}


@pytest.mark.django_db
def test_events_cursor_reads_beyond_legacy_500_cap_without_overlap():
    user, client = _owner_client("report-v2-cursor")
    run = _run(user, status=AgentRun.STATUS_RUNNING, report="")
    for index in range(503):
        AgentRunEvent.objects.create(
            run=run,
            event_type="agent_task_failed" if index == 502 else "agent_action",
            message=f"event {index + 1}",
        )

    newest = client.get(f"/servers/api/agents/runs/{run.id}/events/?cursor=504&limit=3").json()
    older = client.get(
        f"/servers/api/agents/runs/{run.id}/events/?cursor={newest['page']['next_cursor']}&limit=3"
    ).json()

    assert [item["sequence_no"] for item in newest["items"]] == [501, 502, 503]
    assert [item["sequence_no"] for item in older["items"]] == [498, 499, 500]
    assert not ({item["id"] for item in newest["items"]} & {item["id"] for item in older["items"]})
    assert newest["events"] == newest["items"]
    assert newest["event_high_watermark"]["sequence_no"] == 503
    assert newest["event_high_watermark"]["total"] == 503
    critical = client.get(
        f"/servers/api/agents/runs/{run.id}/events/v2/?cursor=504&severity=critical&limit=10"
    ).json()
    assert critical["total"] == 1
    assert critical["items"][0]["sequence_no"] == 503


@pytest.mark.django_db
def test_report_v2_validates_structured_evidence_and_redacts_lazy_surfaces():
    user, client = _owner_client("report-v2-redaction")
    run = _run(
        user,
        report=(
            "# Result\npassword=hunter2-secret\n"
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456\n"
            "## Ключевые находки\n- Saved evidence exists."
        ),
    )
    event = AgentRunEvent.objects.create(
        run=run,
        event_type="agent_observation",
        message="token=private-value-123456",
        payload={"authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456"},
    )
    run.commands_output = [
        {
            "cmd": "curl -H 'Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456' https://example.test",
            "stdout": "password=hunter2-secret",
        }
    ]
    run.tool_calls = [
        {
            "tool": "ssh_execute",
            "result_preview": "api_key=super-secret-api-key-value",
            "error": "Bearer abcdefghijklmnopqrstuvwxyz123456",
            "status": "succeeded",
            "success": True,
            "exit_code": 0,
            "args": {"password": "must-never-leak", "command": "echo ok"},
        }
    ]
    run.report_payload = {
        "model_report": {
            "indicators": [
                {
                    "id": "domain-health",
                    "role": "primary",
                    "label": "Domain health",
                    "value": "degraded",
                    "value_kind": "status",
                    "tone": "warning",
                    "priority": 3,
                    "evidence_refs": [{"ref": f"event:{event.id}"}, {"ref": "event:999999"}],
                }
            ],
            "findings": [
                {
                    "id": "model-finding",
                    "title": "Validated model finding",
                    "severity": "high",
                    "confidence": "high",
                    "scope": "selected server",
                    "evidence_refs": [{"ref": f"event:{event.id}"}, {"ref": "event:999999"}],
                }
            ],
            "actions": [
                {
                    "id": "model-action",
                    "title": "Review the validated event",
                    "safety": "read_only",
                    "evidence_refs": [{"ref": f"event:{event.id}"}],
                    "cta": {"type": "open_evidence", "ref": f"event:{event.id}", "href": "javascript:alert(1)"},
                }
            ],
        }
    }
    run.save(update_fields=["commands_output", "tool_calls", "report_payload"])
    AgentRunArtifact.objects.create(
        run=run,
        user=user,
        artifact_key="secret-log",
        name="secret.log",
        artifact_type="LOG",
        content_type="text/plain",
        content="password=artifact-secret",
    )

    report_response = client.get(f"/servers/api/agents/runs/{run.id}/report/v2/")
    document_response = client.get(f"/servers/api/agents/runs/{run.id}/report/document/")
    activity_response = client.get(f"/servers/api/agents/runs/{run.id}/activity/?limit=10")
    artifacts_response = client.get(f"/servers/api/agents/runs/{run.id}/artifacts/")

    assert report_response.status_code == document_response.status_code == activity_response.status_code == 200
    report_payload = report_response.json()
    serialized = str(report_payload)
    assert "hunter2-secret" not in serialized
    assert "abcdefghijklmnopqrstuvwxyz123456" not in serialized
    assert "domain-health" in {item["id"] for item in report_payload["indicators"]}
    finding = next(item for item in report_payload["findings"] if item["id"] == "model-finding")
    assert [ref["ref"] for ref in finding["evidence_refs"]] == [f"event:{event.id}"]
    assert "tab=evidence&view=events" in finding["evidence_refs"][0]["href"]
    action = next(item for item in report_payload["actions"] if item["id"] == "model-action")
    assert action["cta"]["href"] == finding["evidence_refs"][0]["href"]
    assert b"hunter2-secret" not in document_response.content
    assert b"abcdefghijklmnopqrstuvwxyz123456" not in document_response.content
    assert document_response["ETag"]
    activity_payload = activity_response.json()
    command = next(item for item in activity_payload["items"] if item["kind"] == "command")
    tool = next(item for item in activity_payload["items"] if item["kind"] == "tool")
    assert command["status"] == "unknown" and command["exit_code"] is None
    assert tool["status"] == "succeeded" and tool["exit_code"] == 0
    assert "must-never-leak" not in str(activity_payload)
    assert artifacts_response.json()["items"][0]["download_url"].endswith(f"/{run.artifacts.first().id}/download/")
    assert "content" not in artifacts_response.json()["items"][0]

    other, other_client = _owner_client("report-v2-redaction-other")
    assert other.pk != user.pk
    for path in (
        f"/servers/api/agents/runs/{run.id}/report/v2/",
        f"/servers/api/agents/runs/{run.id}/report/document/",
        f"/servers/api/agents/runs/{run.id}/activity/",
        f"/servers/api/agents/runs/{run.id}/artifacts/",
        f"/servers/api/agents/runs/{run.id}/events/v2/",
    ):
        assert other_client.get(path).status_code == 404


@pytest.mark.django_db
def test_delivery_retry_returns_409_or_compact_202_with_attempt_id(monkeypatch):
    user, client = _owner_client("report-v2-delivery")
    run = _run(user)
    run.agent.report_delivery = {"telegram": {"enabled": True, "chat_id": "123456789"}}
    run.agent.save(update_fields=["report_delivery"])
    task_delay = Mock()
    monkeypatch.setattr("servers.views.server_agent_runs.deliver_agent_report_task.delay", task_delay)
    monkeypatch.setattr(
        "servers.agents.agent_run_report_v2.load_notification_config",
        lambda: {"telegram_bot_token": "", "telegram_chat_id": ""},
    )

    blocked = client.post(f"/servers/api/agents/runs/{run.id}/report/deliver/")
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "telegram_not_configured"
    task_delay.assert_not_called()

    monkeypatch.setattr(
        "servers.agents.agent_run_report_v2.load_notification_config",
        lambda: {"telegram_bot_token": "bot-secret", "telegram_chat_id": ""},
    )
    accepted = client.post(f"/servers/api/agents/runs/{run.id}/report/deliver/")
    assert accepted.status_code == 202
    payload = accepted.json()
    assert set(payload) == {"success", "code", "data", "accepted", "attempt_id", "delivery"}
    assert payload["code"] == "delivery_accepted" and payload["data"] is None
    assert payload["accepted"] is True
    assert payload["delivery"]["status"] == "in_progress"
    assert payload["delivery"]["can_retry"] is False
    assert payload["delivery"]["blocked_reason"] == "delivery_in_progress"
    task_delay.assert_called_once_with(run.id, payload["attempt_id"])
    second = client.post(f"/servers/api/agents/runs/{run.id}/report/deliver/")
    assert second.status_code == 409
    assert second.json()["code"] == "delivery_in_progress"


@pytest.mark.django_db
def test_run_scoped_stale_cleanup_exposes_canonical_result(monkeypatch):
    user, client = _owner_client("report-v2-cleanup")
    run = _run(user, status=AgentRun.STATUS_RUNNING, report="")
    AgentRun.objects.filter(pk=run.pk).update(started_at=timezone.now() - timedelta(hours=2))
    run.refresh_from_db()
    monkeypatch.setattr("servers.agents.agent_cleanup_service._agent_run_stale_seconds_setting", lambda: 60)

    response = client.post(f"/servers/api/agents/runs/{run.id}/cleanup-stale/")

    assert response.status_code == 200
    assert response.json()["run_id"] == run.id
    assert response.json()["cleaned"] is True
    assert "canceled_dispatches" in response.json()
    run.refresh_from_db()
    assert run.status == AgentRun.STATUS_FAILED
    assert run.execution_outcome["exit_reason"] == "stale_cleanup"
    assert client.post(f"/servers/api/agents/runs/{run.id}/cleanup-stale/").status_code == 409
