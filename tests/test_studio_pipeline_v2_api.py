from __future__ import annotations

from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone

from studio.assistant_action_registry import register_assistant_actions
from studio.models import ApprovalRequest, Pipeline, PipelineRun
from studio.pipeline.pipeline_run_state import update_node_state
from tests.studio_pipeline_v2_harness import (
    build_run,
    disable_activity_logging,
    grant_feature,
    json_payload,
    report_node,
)


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    disable_activity_logging(monkeypatch)


@pytest.mark.django_db
def test_api_run_approve_requires_confirmation_post_and_csrf(monkeypatch):
    user = User.objects.create_user(username="approval-link-user", password="x")
    approver = User.objects.create_user(
        username="approval-link-approver",
        email="approver@example.com",
        password="x",
    )
    pipeline = Pipeline.objects.create(
        name="Approval link flow",
        owner=user,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            {
                "id": "approval_gate",
                "type": "logic/human_approval",
                "position": {"x": 180, "y": 0},
                "data": {
                    "label": "Approval Gate",
                    "tg_bot_token": "bot-123",
                    "tg_chat_id": "chat-42",
                },
            },
        ],
        edges=[{"id": "e1", "source": "manual", "target": "approval_gate", "sourceHandle": "out"}],
    )
    run = build_run(pipeline, entry_node_id="manual")
    run.node_states = {
        "approval_gate": {
            "status": "awaiting_approval",
        }
    }
    run.save(update_fields=["node_states"])
    raw_token = "tok-123"
    approval = ApprovalRequest.objects.create(
        run=run,
        node_id="approval_gate",
        token_digest=ApprovalRequest.digest_token(raw_token),
        approver=approver,
        requested_by=user,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    assert approval.token_digest != raw_token

    captured: dict[str, object] = {}

    def fake_post(url: str, json: dict, timeout: int):
        captured["url"] = url
        captured["json"] = json

        class _Resp:
            status_code = 200
            text = "ok"

        return _Resp()

    monkeypatch.setattr("studio.views.run_views.httpx.post", fake_post)
    client = Client(enforce_csrf_checks=True)
    client.force_login(approver)

    url = f"/api/studio/runs/{run.id}/approve/approvalgate/?token={raw_token}&decision=approved"
    confirmation = client.get(url)

    assert confirmation.status_code == 200
    assert b"Review pipeline decision" in confirmation.content
    assert confirmation.headers["Cache-Control"] == "no-store"
    assert confirmation.headers["Referrer-Policy"] == "no-referrer"
    assert captured == {}
    run.refresh_from_db()
    assert "approval_decision" not in run.node_states["approval_gate"]

    csrf_token = client.cookies["csrftoken"].value
    owner_client = Client(enforce_csrf_checks=True)
    owner_client.force_login(user)
    assert owner_client.get(url).status_code == 403

    unrelated = User.objects.create_user(username="approval-unrelated-user", password="x")
    unrelated_client = Client(enforce_csrf_checks=True)
    unrelated_client.force_login(unrelated)
    assert unrelated_client.get(url).status_code == 403

    rejected_without_csrf_client = Client(enforce_csrf_checks=True)
    rejected_without_csrf_client.force_login(approver)
    rejected_without_csrf = rejected_without_csrf_client.post(
        url.split("?", 1)[0],
        data={"token": raw_token, "decision": "approved"},
    )
    assert rejected_without_csrf.status_code == 403

    response = client.post(
        url.split("?", 1)[0],
        data={
            "csrfmiddlewaretoken": csrf_token,
            "token": raw_token,
            "decision": "approved",
            "response_text": "Reviewed",
        },
        HTTP_X_CSRFTOKEN=csrf_token,
    )

    assert response.status_code == 200
    run.refresh_from_db()
    assert run.node_states["approval_gate"]["approval_decision"] == "approved"
    assert run.node_states["approval_gate"]["approval_response"] == "Reviewed"
    approval.refresh_from_db()
    assert approval.status == ApprovalRequest.STATUS_APPROVED
    assert approval.decided_by == approver
    assert approval.response_text == "Reviewed"
    assert captured["url"] == "https://api.telegram.org/botbot-123/sendMessage"
    assert "Решение записано" in str(captured["json"]["text"])

    replay = client.post(
        url.split("?", 1)[0],
        data={
            "csrfmiddlewaretoken": csrf_token,
            "token": raw_token,
            "decision": "rejected",
        },
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    assert replay.status_code == 200
    approval.refresh_from_db()
    assert approval.status == ApprovalRequest.STATUS_APPROVED


@pytest.mark.django_db
def test_expired_approval_request_fails_closed():
    owner = User.objects.create_user(username="approval-expired-owner", password="x")
    approver = User.objects.create_user(username="approval-expired-approver", password="x")
    pipeline = Pipeline.objects.create(name="Expired approval", owner=owner, nodes=[], edges=[])
    run = build_run(pipeline, entry_node_id="")
    run.node_states = {"approval": {"status": "awaiting_approval"}}
    run.save(update_fields=["node_states"])
    raw_token = "expired-approval-token"
    approval = ApprovalRequest.objects.create(
        run=run,
        node_id="approval",
        token_digest=ApprovalRequest.digest_token(raw_token),
        approver=approver,
        requested_by=owner,
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    client = Client()
    client.force_login(approver)

    response = client.get(f"/api/studio/runs/{run.id}/approve/approval/?token={raw_token}")

    assert response.status_code == 403
    approval.refresh_from_db()
    assert approval.status == ApprovalRequest.STATUS_EXPIRED


def test_studio_assistant_cannot_bypass_assigned_approval(monkeypatch):
    registered_actions = []
    monkeypatch.setattr("studio.assistant_action_registry.register_action", registered_actions.append)
    monkeypatch.setattr("studio.assistant_action_registry.register_runtime_context_provider", lambda *_args: None)

    register_assistant_actions()

    action_types = {spec.action_type for spec in registered_actions}
    assert "studio.run.approve_node" not in action_types


@pytest.mark.django_db
def test_run_apis_expose_only_allowlisted_node_state_fields():
    user = User.objects.create_user(username="run-state-contract-user", password="x")
    grant_feature(user, "studio", "studio_runs")
    pipeline = Pipeline.objects.create(name="Public run state", owner=user, nodes=[], edges=[])
    run = build_run(pipeline, entry_node_id="")
    token = "APPROVAL_TOKEN_SENTINEL_9a60e9"
    approve_url = f"https://ops.example/approve/?token={token}&decision=approved"
    run.node_states = {
        "approval": {
            "status": "awaiting_approval",
            "output": f"Review: {approve_url}",
            "started_at": "2026-07-30T00:00:00+00:00",
            "approval_token": token,
            "approve_url": approve_url,
            "reject_url": approve_url.replace("approved", "rejected"),
            "telegram_chat_id": "sensitive-chat-id",
        }
    }
    run.save(update_fields=["node_states"])
    client = Client()
    client.force_login(user)

    detail = client.get(f"/api/studio/runs/{run.id}/")
    listing = client.get("/api/studio/runs/")

    assert detail.status_code == 200
    assert listing.status_code == 200
    for payload in (detail.json(), listing.json()["data"][0]):
        serialized = payload["node_states"]["approval"]
        assert set(serialized) == {"status", "output", "started_at"}
        assert serialized["status"] == "awaiting_approval"
        assert "token=[REDACTED]" in serialized["output"]
        assert token not in json_payload(payload)
        assert "sensitive-chat-id" not in json_payload(payload)


@pytest.mark.django_db(transaction=True)
def test_live_run_updates_expose_only_allowlisted_node_state_fields(monkeypatch):
    user = User.objects.create_user(username="live-run-state-contract-user", password="x")
    pipeline = Pipeline.objects.create(name="Live public run state", owner=user, nodes=[], edges=[])
    run = build_run(pipeline, entry_node_id="")
    token = "LIVE_APPROVAL_TOKEN_SENTINEL_d38ac1"
    events: list[dict] = []

    class FakeChannelLayer:
        async def group_send(self, _group: str, event: dict) -> None:
            events.append(event)

    async def no_activity_log(**_kwargs) -> None:
        return None

    monkeypatch.setattr("studio.pipeline.pipeline_run_state.get_channel_layer", lambda: FakeChannelLayer())
    monkeypatch.setattr("studio.pipeline.pipeline_run_state.log_user_activity_async", no_activity_log)

    async_to_sync(update_node_state)(
        run,
        "approval",
        {
            "status": "awaiting_approval",
            "output": f"Review https://ops.example/approve/?token={token}",
            "approval_token": token,
            "approve_url": f"https://ops.example/approve/?token={token}",
        },
    )

    assert len(events) == 1
    assert set(events[0]["state"]) == {"status", "output"}
    assert token not in json_payload(events[0])
    run.refresh_from_db()
    assert run.node_states["approval"]["approval_token"] == token


@pytest.mark.django_db
def test_manual_run_auto_selects_only_manual_trigger(monkeypatch):
    user = User.objects.create_user(username="manual-api-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.trigger_dispatch.launch_pipeline_run_async", lambda _run: None)

    pipeline = Pipeline.objects.create(
        name="Manual API flow",
        owner=user,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            report_node("report"),
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json_payload({"context": {"ticket": "INC-1"}}),
        content_type="application/json",
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["entry_node_id"] == "manual"
    assert payload["trigger_type"] == "manual"
    assert payload["trigger_id"] is not None


@pytest.mark.django_db
def test_manual_run_validate_only_does_not_create_or_launch_run(monkeypatch):
    user = User.objects.create_user(username="manual-validate-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    launch_calls: list[int] = []
    monkeypatch.setattr(
        "studio.views.pipeline_helpers._launch_pipeline_run_async",
        lambda run: launch_calls.append(run.id),
    )

    pipeline = Pipeline.objects.create(
        name="Manual validate flow",
        owner=user,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            report_node("report"),
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json_payload({"context": {"ticket": "INC-1"}, "validate_only": True}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["validation"] == {"ok": True, "errors": [], "issues": []}
    assert payload["dry_run"]["executed"] is False
    assert payload["dry_run"]["mode"] == "validate_only"
    assert payload["entry_node_id"] == "manual"
    assert payload["would_create_run"] is False
    assert launch_calls == []
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_manual_run_validate_only_reports_graph_errors_without_launch(monkeypatch):
    user = User.objects.create_user(username="manual-validate-errors-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr(
        "studio.views.pipeline_helpers._launch_pipeline_run_async",
        lambda _run: pytest.fail("validate_only must not launch"),
    )

    pipeline = Pipeline.objects.create(
        name="Legacy validate flow",
        owner=user,
        graph_version=1,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            report_node("report"),
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json_payload({"context": {}, "dry_run": True}),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["validation"]["ok"] is False
    assert any("graph_version=1" in error for error in payload["validation"]["errors"])
    assert payload["dry_run"]["executed"] is False
    assert PipelineRun.objects.filter(pipeline=pipeline).count() == 0


@pytest.mark.django_db
def test_create_pipeline_without_nodes_seeds_manual_draft():
    user = User.objects.create_user(username="draft-create-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)

    response = client.post(
        "/api/studio/pipelines/",
        data=json_payload({"name": "Draft Pipeline", "nodes": [], "edges": []}),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["graph_version"] == 2
    assert len(payload["nodes"]) == 1
    assert payload["nodes"][0]["type"] == "trigger/manual"
    assert payload["nodes"][0]["id"] == "manual_start"


@pytest.mark.django_db
def test_manual_run_requires_entry_node_when_multiple_manual_triggers(monkeypatch):
    user = User.objects.create_user(username="manual-multi-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views.pipeline_helpers._launch_pipeline_run_async", lambda _run: None)

    pipeline = Pipeline.objects.create(
        name="Multiple manual triggers",
        owner=user,
        nodes=[
            {"id": "manual_a", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual A"}},
            {"id": "manual_b", "type": "trigger/manual", "position": {"x": 0, "y": 120}, "data": {"label": "Manual B"}},
            report_node("report_a"),
            report_node("report_b"),
        ],
        edges=[
            {"id": "e1", "source": "manual_a", "target": "report_a", "sourceHandle": "out"},
            {"id": "e2", "source": "manual_b", "target": "report_b", "sourceHandle": "out"},
        ],
    )
    pipeline.sync_triggers_from_nodes()

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json_payload({"context": {}}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "entry_node_id" in response.json()["error"]

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json_payload({"context": {}, "entry_node_id": "manual_b"}),
        content_type="application/json",
    )
    assert response.status_code == 202
    assert response.json()["entry_node_id"] == "manual_b"


@pytest.mark.django_db
def test_webhook_trigger_stores_entry_node_id(monkeypatch):
    user = User.objects.create_user(username="webhook-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views.pipeline_helpers._launch_pipeline_run_async", lambda _run: None)

    pipeline = Pipeline.objects.create(
        name="Webhook flow",
        owner=user,
        nodes=[
            {
                "id": "webhook",
                "type": "trigger/webhook",
                "position": {"x": 0, "y": 0},
                "data": {"label": "Webhook", "webhook_payload_map": {"ref": "git.ref"}},
            },
            report_node("report"),
        ],
        edges=[{"id": "e1", "source": "webhook", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()
    trigger = pipeline.triggers.get(trigger_type="webhook")

    response = client.post(
        f"/api/studio/triggers/{trigger.webhook_token}/receive/",
        data=json_payload({"git": {"ref": "refs/heads/main"}}),
        content_type="application/json",
    )

    assert response.status_code == 200
    run = PipelineRun.objects.get(pk=response.json()["run_id"])
    assert run.entry_node_id == "webhook"
    assert run.context["ref"] == "refs/heads/main"


@pytest.mark.django_db
def test_old_graph_version_is_rejected_by_run_api(monkeypatch):
    user = User.objects.create_user(username="old-graph-user", password="x")
    grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)
    monkeypatch.setattr("studio.views.pipeline_helpers._launch_pipeline_run_async", lambda _run: None)

    pipeline = Pipeline.objects.create(
        name="Legacy flow",
        owner=user,
        graph_version=1,
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}},
            report_node("report"),
        ],
        edges=[{"id": "e1", "source": "manual", "target": "report", "sourceHandle": "out"}],
    )
    pipeline.sync_triggers_from_nodes()

    response = client.post(
        f"/api/studio/pipelines/{pipeline.id}/run/",
        data=json_payload({"context": {}}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "graph_version=1" in response.json()["error"]
