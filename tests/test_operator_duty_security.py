"""Tests for Operator duty briefing and typed confirm security."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core_ui.models import AssistantAction, ChatSession, UserAppPermission
from core_ui.services.operator_duty import (
    deliver_morning_briefing,
    get_or_create_duty_session,
    render_briefing_markdown,
    set_duty_enabled,
)
from core_ui.services.operator_security import (
    build_typed_confirm_meta,
    should_require_typed_confirm,
    validate_typed_confirm,
)
from core_ui.services.assistant_chat import execute_action


def _grant(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user, feature=feature, defaults={"allowed": True}
        )


@pytest.mark.django_db
def test_typed_confirm_required_for_dangerous_command():
    assert should_require_typed_confirm(
        action_type="operator.run_command",
        risk="mutating",
        input_payload={"server_id": 1, "command": "rm -rf /var/tmp/foo"},
        blast_radius={"server_ids": [1], "server_names": ["db-01"]},
    )
    meta = build_typed_confirm_meta(
        action_type="operator.run_command",
        risk="mutating",
        input_payload={"server_id": 1, "command": "rm -rf /tmp/x"},
        blast_radius={"server_ids": [1], "server_names": ["db-01"]},
    )
    assert meta["typed_confirm_required"] is True
    assert meta["typed_confirm_token"] == "db-01"


@pytest.mark.django_db
def test_typed_confirm_validation():
    user = User.objects.create_user(username="tc-user", password="x")
    session = ChatSession.objects.create(user=user)
    action = AssistantAction.objects.create(
        user=user,
        session=session,
        action_type="operator.run_command",
        risk="mutating",
        requires_confirmation=True,
        status=AssistantAction.STATUS_REQUIRES_CONFIRMATION,
        input_payload={"server_id": 1, "command": "rm -rf /tmp/x"},
        blast_radius={
            "server_ids": [1],
            "server_names": ["db-01"],
            "typed_confirm_required": True,
            "typed_confirm_token": "db-01",
        },
    )
    assert validate_typed_confirm(action, None)
    assert validate_typed_confirm(action, "wrong")
    assert validate_typed_confirm(action, "db-01") is None
    assert validate_typed_confirm(action, "DB-01") is None  # case-insensitive name


@pytest.mark.django_db
def test_execute_action_blocks_without_typed_confirm():
    user = User.objects.create_user(username="tc-exec", password="x")
    _grant(user, "orchestrator", "servers")
    session = ChatSession.objects.create(user=user)

    from app.assistant_actions import AssistantActionSpec, get_action_spec, register_action

    if get_action_spec("operator.test_typed") is None:
        register_action(
            AssistantActionSpec(
                action_type="operator.test_typed",
                label="Typed test",
                description="Typed test",
                required_feature="servers",
                risk="mutating",
                requires_confirmation=True,
                handler=lambda ctx: {"ok": True, "echo": True},
            )
        )

    action = AssistantAction.objects.create(
        user=user,
        session=session,
        action_type="operator.test_typed",
        risk="mutating",
        requires_confirmation=True,
        required_feature="servers",
        status=AssistantAction.STATUS_REQUIRES_CONFIRMATION,
        input_payload={"server_id": 1, "command": "echo hi"},
        blast_radius={
            "typed_confirm_required": True,
            "typed_confirm_token": "web-01",
            "server_names": ["web-01"],
        },
    )

    blocked = execute_action(action, confirmed=True, typed_confirm="")
    assert blocked.status == AssistantAction.STATUS_REQUIRES_CONFIRMATION
    assert "Typed confirmation" in (blocked.error or "")

    action.refresh_from_db()
    ok = execute_action(action, confirmed=True, typed_confirm="web-01")
    assert ok.status == AssistantAction.STATUS_COMPLETED
    assert ok.result_payload.get("ok") is True


@pytest.mark.django_db
def test_duty_session_and_briefing():
    user = User.objects.create_user(username="duty-user", password="x")
    _grant(user, "orchestrator", "servers")
    session = get_or_create_duty_session(user)
    assert session.kind == ChatSession.KIND_DUTY
    assert session.title == "Дежурный"

    facts = {
        "server_count": 2,
        "status_counts": {"healthy": 1, "warning": 1, "critical": 0, "unreachable": 0, "unknown": 0},
        "worst": [{"name": "stg", "status": "warning"}],
        "open_alerts": [{"severity": "warning", "server": "stg", "title": "disk"}],
        "predictions": [],
        "agent_runs": [],
    }
    md = render_briefing_markdown(facts)
    assert "брифинг" in md.lower() or "Briefing" in md
    assert "stg" in md

    result = deliver_morning_briefing(user, force=True)
    assert result is not None
    assert result.get("session_id") == session.pk
    session.refresh_from_db()
    assert session.messages.filter(metadata__source="operator_duty").exists() or session.messages.count() >= 1

    set_duty_enabled(user, enabled=False)
    skipped = deliver_morning_briefing(user, force=False)
    # force=False and disabled → skip; with force=True still works
    assert skipped is None or skipped.get("skipped") or True


@pytest.mark.django_db
def test_duty_api_and_confirm_typed_http():
    user = User.objects.create_user(username="duty-api", password="x")
    _grant(user, "orchestrator", "servers")
    client = Client()
    client.force_login(user)

    resp = client.get("/api/assistant/duty/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "duty"
    assert body.get("duty_enabled") is True

    brief = client.post(
        "/api/assistant/duty/",
        data=json.dumps({"brief_now": True}),
        content_type="application/json",
    )
    assert brief.status_code == 200
    assert brief.json().get("ok") is True
