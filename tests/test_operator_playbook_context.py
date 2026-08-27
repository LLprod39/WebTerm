from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.utils import timezone

from app.assistant_actions import AssistantActionContext, AssistantActionError
from core_ui.models import ChatSession, OperatorTurnDispatch
from core_ui.services.operator_dispatch import execute_operator_dispatch
from core_ui.services.operator_loop_helpers import _enrich_playbook_resolve_arguments
from core_ui.services.operator_loop_prompt import build_operator_system_prompt
from servers.models import Playbook, PlaybookRun
from servers.operator.tools_playbooks import list_playbooks, playbook_runs, resolve_playbook


def _playbook(user, name: str, *, description: str = "") -> Playbook:
    return Playbook.objects.create(
        user=user,
        name=name,
        description=description,
        kind=Playbook.KIND_ANSIBLE,
        category=Playbook.CATEGORY_SECURITY,
        source_yaml="- hosts: all\n  tasks:\n    - name: Harden SSH\n      ansible.builtin.lineinfile:\n        path: /etc/ssh/sshd_config\n",
        tasks=[{"id": "ssh", "description": "Harden SSH", "command": "lineinfile sshd_config"}],
    )


@pytest.mark.django_db
def test_resolve_playbook_reads_selected_accessible_playbook_without_copying_yaml():
    user = User.objects.create_user(username="playbook-owner", password="x")
    playbook = _playbook(user, "Base Linux server configuration and hardening", description="Secure a Linux baseline")

    result = resolve_playbook(AssistantActionContext(user=user, input_payload={"playbook_id": playbook.id}))

    assert result["found"] is True
    assert result["playbook"]["id"] == playbook.id
    assert result["playbook"]["description"] == "Secure a Linux baseline"
    assert "Harden SSH" in result["playbook"]["source_yaml"]
    assert "Do not ask for its ID or YAML" in result["reply_hint"]


@pytest.mark.django_db
def test_resolve_playbook_does_not_disclose_another_users_object():
    owner = User.objects.create_user(username="private-playbook-owner", password="x")
    viewer = User.objects.create_user(username="private-playbook-viewer", password="x")
    playbook = _playbook(owner, "Private hardening")

    with pytest.raises(AssistantActionError, match="not found or not accessible") as exc:
        resolve_playbook(AssistantActionContext(user=viewer, input_payload={"playbook_id": playbook.id}))

    assert exc.value.status == 404


@pytest.mark.django_db
def test_resolve_playbook_requires_choice_for_ambiguous_accessible_name():
    user = User.objects.create_user(username="ambiguous-playbook-owner", password="x")
    first = _playbook(user, "Linux hardening production")
    second = _playbook(user, "Linux hardening staging")

    result = resolve_playbook(AssistantActionContext(user=user, input_payload={"q": "Linux hardening"}))

    assert result["found"] is False
    assert result["ambiguous"] is True
    assert {row["id"] for row in result["matches"]} == {first.id, second.id}
    assert all("source_yaml" not in row for row in result["matches"])


@pytest.mark.django_db
def test_chat_lists_accessible_playbooks_without_manual_composer_selection():
    user = User.objects.create_user(username="playbook-catalog-owner", password="x")
    other = User.objects.create_user(username="playbook-catalog-other", password="x")
    visible = _playbook(user, "Linux hardening")
    _playbook(other, "Private database maintenance")

    result = list_playbooks(AssistantActionContext(user=user, input_payload={}))

    assert result["count"] == 1
    assert result["playbooks"][0]["id"] == visible.id
    assert "source_yaml" not in result["playbooks"][0]


@pytest.mark.django_db
def test_chat_reads_owned_playbook_run_report_and_bounded_log_tail():
    user = User.objects.create_user(username="playbook-run-owner", password="x")
    other = User.objects.create_user(username="playbook-run-other", password="x")
    playbook = _playbook(user, "Linux hardening")
    private_playbook = _playbook(other, "Private maintenance")
    run = PlaybookRun.objects.create(
        user=user,
        playbook=playbook,
        status=PlaybookRun.STATUS_COMPLETED,
        playbook_snapshot={"name": playbook.name},
        target_server_ids=[7],
        summary={"ok": 4, "failed": 0},
        host_results=[{"server_id": 7, "status": "ok"}],
        live_log="begin\nTASK [harden ssh]\nok\nPLAY RECAP\n",
    )
    private_run = PlaybookRun.objects.create(
        user=other,
        playbook=private_playbook,
        status=PlaybookRun.STATUS_FAILED,
        live_log="private log",
    )

    listed = playbook_runs(AssistantActionContext(user=user, input_payload={}))
    detail = playbook_runs(AssistantActionContext(user=user, input_payload={"run_id": run.id, "log_tail_chars": 18}))

    assert listed["count"] == 1
    assert listed["runs"][0]["id"] == run.id
    assert "live_log_tail" not in listed["runs"][0]
    assert detail["run"]["summary"] == {"ok": 4, "failed": 0}
    assert detail["run"]["live_log_tail"].endswith("ok\nPLAY RECAP\n")

    with pytest.raises(AssistantActionError, match="not found") as exc:
        playbook_runs(AssistantActionContext(user=user, input_payload={"run_id": private_run.id}))
    assert exc.value.status == 404


@pytest.mark.django_db
def test_operator_prompt_exposes_pinned_playbook_id_without_yaml_request():
    user = User.objects.create_user(username="pinned-playbook-owner", password="x")
    playbook = _playbook(user, "Base Linux server configuration and hardening")
    session = ChatSession.objects.create(
        user=user,
        title="Playbook context",
        pinned_context={"playbook": {"id": playbook.id, "name": playbook.name, "kind": playbook.kind}},
    )

    prompt = build_operator_system_prompt(session)

    assert f"playbook_id {playbook.id}" in prompt
    assert playbook.name in prompt
    assert "never ask for ID/YAML" in prompt

    assert _enrich_playbook_resolve_arguments(session, {}) == {"playbook_id": playbook.id}
    assert _enrich_playbook_resolve_arguments(session, {"q": "other"}) == {"q": "other"}


@pytest.mark.django_db(transaction=True)
def test_dispatch_emits_terminal_ack_after_durable_completion(monkeypatch):
    user = User.objects.create_user(username="durable-playbook-turn", password="x")
    session = ChatSession.objects.create(user=user, title="Durable completion")
    dispatch = OperatorTurnDispatch.objects.create(
        session=session,
        kind=OperatorTurnDispatch.KIND_MESSAGE,
        payload={"message": "What does it do?"},
        status=OperatorTurnDispatch.STATUS_CLAIMED,
        claimed_by="test-worker",
        attempt_count=1,
        lease_expires_at=timezone.now() + timedelta(minutes=3),
    )
    events = []

    async def no_op(_dispatch):
        return None

    async def capture(chat_id, event):
        events.append((chat_id, event))

    monkeypatch.setattr("core_ui.services.operator_turn_runtime.run_claimed_operator_dispatch", no_op)
    monkeypatch.setattr("core_ui.services.operator_turn_runtime.broadcast_operator_event", capture)

    status = async_to_sync(execute_operator_dispatch)(dispatch.id, worker_name="test-worker")

    assert status == OperatorTurnDispatch.STATUS_COMPLETED
    assert events == [
        (
            session.id,
            {
                "type": "turn_complete",
                "status": "done",
                "turn_id": None,
                "assistant_message_id": None,
                "dispatch_id": dispatch.id,
                "durable_completion": True,
            },
        )
    ]
