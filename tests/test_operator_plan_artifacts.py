"""Tests for plan mode, artifacts, memory grounding, rate limit."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import Client

from app.assistant_actions import AssistantActionSpec, get_action_spec, register_action
from core_ui.models import ChatArtifact, ChatMessage, ChatSession, ChatTurnState, UserAppPermission
from core_ui.services.operator_artifacts import create_artifact, extract_artifacts_from_tool_result, list_artifacts
from core_ui.services.operator_loop import _create_pending_action
from core_ui.services.operator_memory import memory_context_block, server_ids_from_arguments
from core_ui.services.operator_rate_limit import check_turn_rate_limit


def _grant(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user, feature=feature, defaults={"allowed": True}
        )


@pytest.mark.django_db
def test_only_one_active_turn_is_allowed_per_chat():
    user = User.objects.create_user(username="turn-unique", password="x")
    session = ChatSession.objects.create(user=user, title="Unique active turn")
    ChatTurnState.objects.create(session=session, status=ChatTurnState.STATUS_RUNNING)

    with pytest.raises(IntegrityError), transaction.atomic():
        ChatTurnState.objects.create(
            session=session,
            status=ChatTurnState.STATUS_AWAITING_CONFIRM,
        )

    ChatTurnState.objects.create(session=session, status=ChatTurnState.STATUS_DONE)


@pytest.mark.django_db
def test_create_and_list_artifacts():
    user = User.objects.create_user(username="art-user", password="x")
    session = ChatSession.objects.create(user=user, title="t")
    art = create_artifact(
        session=session,
        kind="ansible",
        title="Cleanup WAL",
        content="---\n- hosts: all\n",
    )
    assert art.version == 1
    listed = list_artifacts(session)
    assert len(listed) == 1
    assert listed[0]["title"] == "Cleanup WAL"
    assert listed[0]["kind"] == "ansible"


@pytest.mark.django_db
def test_extract_artifacts_from_playbook_result():
    user = User.objects.create_user(username="art-pb", password="x")
    session = ChatSession.objects.create(user=user)
    msg = ChatMessage.objects.create(session=session, role="assistant", content="")
    arts = extract_artifacts_from_tool_result(
        session=session,
        message=msg,
        action_type="operator.create_playbook",
        result={
            "ok": True,
            "playbook": {"id": 99, "name": "Nightly", "kind": "runbook"},
            "yaml": "---\n- name: test\n",
        },
    )
    assert arts
    assert ChatArtifact.objects.filter(session=session).exists()


@pytest.mark.django_db
def test_artifacts_api():
    user = User.objects.create_user(username="art-api", password="x")
    _grant(user, "orchestrator")
    session = ChatSession.objects.create(user=user)
    client = Client()
    client.force_login(user)
    create = client.post(
        f"/api/assistant/chats/{session.pk}/artifacts/",
        data=json.dumps({"kind": "script", "title": "fix.sh", "content": "#!/bin/sh\necho ok\n"}),
        content_type="application/json",
    )
    assert create.status_code == 201
    payload = create.json()
    assert payload["title"] == "fix.sh"

    listing = client.get(f"/api/assistant/chats/{session.pk}/artifacts/")
    assert listing.status_code == 200
    assert len(listing.json()["artifacts"]) == 1

    patch = client.patch(
        f"/api/assistant/chats/{session.pk}/artifacts/",
        data=json.dumps({"id": payload["id"], "content": "#!/bin/sh\necho v2\n"}),
        content_type="application/json",
    )
    assert patch.status_code == 200
    assert patch.json()["version"] == 2


@pytest.mark.django_db
def test_propose_plan_registered():
    from servers.operator_tools import register_operator_tools

    register_operator_tools()
    assert get_action_spec("operator.propose_plan") is not None
    assert get_action_spec("operator.server_memory") is not None
    assert get_action_spec("operator.metric_series") is not None


@pytest.mark.django_db
def test_memory_server_ids_and_pending_description(monkeypatch):
    user = User.objects.create_user(username="mem-user", password="x")
    session = ChatSession.objects.create(user=user)
    msg = ChatMessage.objects.create(session=session, role="assistant", content="")

    if get_action_spec("operator.test_mem") is None:
        register_action(
            AssistantActionSpec(
                action_type="operator.test_mem",
                label="Mem",
                description="Mem action",
                required_feature="servers",
                risk="mutating",
                requires_confirmation=True,
                handler=lambda ctx: {"ok": True},
            )
        )
    _grant(user, "servers")

    monkeypatch.setattr(
        "core_ui.services.operator_memory.memory_hints_for_server",
        lambda sid, limit=5: [f"hint for {sid}"],
    )
    assert server_ids_from_arguments({"server_id": 7, "server_ids": [8]}) == [7, 8]
    block = memory_context_block([7])
    assert "7" in block or "hint" in block

    action = _create_pending_action(
        user=user,
        session=session,
        message=msg,
        action_type="operator.test_mem",
        arguments={"server_id": 7, "command": "systemctl restart nginx"},
        tool_call_id="c1",
    )
    assert "Memory" in action.description or "hint" in action.description
    assert action.blast_radius.get("memory_hints")


@pytest.mark.django_db
def test_rate_limit_triggers():
    user = User.objects.create_user(username="rate-user", password="x")
    session = ChatSession.objects.create(user=user)
    for i in range(60):
        ChatMessage.objects.create(session=session, role="user", content=f"m{i}")
    err = check_turn_rate_limit(session)
    assert err is not None
    assert "Rate limit" in err


@pytest.mark.django_db
def test_rate_limit_is_per_user_not_per_chat():
    user = User.objects.create_user(username="rate-user-global", password="x")
    first = ChatSession.objects.create(user=user)
    second = ChatSession.objects.create(user=user)
    for i in range(60):
        ChatMessage.objects.create(session=first, role="user", content=f"m{i}")
    assert check_turn_rate_limit(second) is not None
