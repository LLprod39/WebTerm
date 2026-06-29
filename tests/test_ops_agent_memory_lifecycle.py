
import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from servers.adapters.memory_store import DjangoServerMemoryStore
from servers.models import (
    BackgroundWorkerState,
    Server,
    ServerKnowledge,
    ServerMemoryEpisode,
    ServerMemoryEvent,
    ServerMemoryPolicy,
    ServerMemorySnapshot,
)


@pytest.mark.django_db(transaction=True)
def test_memory_overview_exposes_worker_states_and_richer_history():
    owner = User.objects.create_user(username="ops-memory-overview-user", password="x")
    server = Server.objects.create(user=owner, name="overview-node", host="10.0.0.71", port=22, username="root")
    store = DjangoServerMemoryStore()

    first_snapshot, _ = store._upsert_snapshot_sync(
        server_id=server.id,
        memory_key="profile",
        title="Canonical Profile",
        content="- Ubuntu 24.04\n- nginx present",
        source_kind="dream",
        source_ref="episode:123",
        confidence=0.86,
        created_by_id=owner.id,
        metadata={"trust_level": "system_measured", "verification_status": "measured"},
    )
    store._upsert_snapshot_sync(
        server_id=server.id,
        memory_key="profile",
        title="Canonical Profile",
        content="- Ubuntu 24.04\n- nginx and docker present",
        source_kind="dream",
        source_ref="episode:456",
        confidence=0.9,
        created_by_id=owner.id,
        metadata={
            "rewrite_reason": "Profile expanded after nightly dream",
            "trust_level": "system_measured",
            "verification_status": "measured",
        },
    )
    BackgroundWorkerState.objects.update_or_create(
        worker_kind=BackgroundWorkerState.KIND_AGENT_EXECUTION,
        worker_key="default",
        defaults={"status": BackgroundWorkerState.STATUS_RUNNING},
    )

    overview = store._get_memory_overview_sync(server.id)
    current = next(item for item in overview["canonical"] if item["memory_key"] == "profile")

    assert "worker_states" in overview
    assert overview["worker_states"]["agent_execution"]["status"] == "running"
    assert overview["worker_states"]["scheduled_agents"]["status"] == "missing"
    assert current["source_ref"] == "episode:456"
    assert current["created_by_username"] == owner.username
    assert current["history"]
    assert any(history_item["content_preview"] for history_item in current["history"])
    assert any(history_item["source_ref"] for history_item in current["history"])
    assert first_snapshot.version_group_id == current["version_group_id"]


@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_skips_scheduled_dreams_when_policy_disabled():
    owner = User.objects.create_user(username="ops-memory-policy-user", password="x")
    server = Server.objects.create(user=owner, name="policy-node", host="10.0.0.64", port=22, username="root")
    ServerMemoryPolicy.objects.create(user=owner, is_enabled=False)

    store = DjangoServerMemoryStore()
    result = store._run_dream_cycle_sync(server.id, job_kind="hybrid", respect_schedule=True)

    assert result["skipped"] is True
    assert result["reason"] == "disabled_by_policy"


@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_manual_force_run_ignores_disabled_policy():
    owner = User.objects.create_user(username="ops-memory-force-policy-user", password="x")
    server = Server.objects.create(user=owner, name="force-policy-node", host="10.0.0.65", port=22, username="root")
    store = DjangoServerMemoryStore()
    store._ingest_event_sync(
        server.id,
        source_kind="terminal",
        actor_kind="human",
        source_ref="force-session",
        session_id="force-session",
        event_type="command_executed",
        raw_text="$ uname -a\nLinux force-policy-node",
        structured_payload={"command": "uname -a", "exit_code": 0},
        importance_hint=0.62,
        actor_user_id=owner.id,
    )
    ServerMemoryPolicy.objects.update_or_create(user=owner, defaults={"is_enabled": False})
    result = store._run_dream_cycle_sync(server.id, job_kind="nearline", force=True)

    assert result["skipped"] is False
    assert ServerMemoryEpisode.objects.filter(server=server, is_active=True).exists()


@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_skips_event_ingest_when_ai_memory_disabled():
    owner = User.objects.create_user(username="ops-memory-disabled-user", password="x")
    server = Server.objects.create(user=owner, name="disabled-node", host="10.0.0.66", port=22, username="root")
    ServerMemoryPolicy.objects.create(user=owner, is_enabled=False)

    store = DjangoServerMemoryStore()
    event_id = store._ingest_event_sync(
        server.id,
        source_kind="terminal",
        actor_kind="human",
        source_ref="disabled-session",
        session_id="disabled-session",
        event_type="command_executed",
        raw_text="$ clear",
        structured_payload={"command": "clear", "exit_code": 0},
        importance_hint=0.2,
        actor_user_id=owner.id,
    )

    assert event_id == ""
    assert not ServerMemoryEvent.objects.filter(server=server).exists()
    assert not ServerMemoryEpisode.objects.filter(server=server).exists()

@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_nightly_llm_enhances_sequence_playbooks(monkeypatch):
    owner = User.objects.create_user(username="ops-memory-llm-sequence-user", password="x")
    server = Server.objects.create(user=owner, name="llm-sequence-node", host="10.0.0.62", port=22, username="root")
    store = DjangoServerMemoryStore()

    for session_id in ("llm-workflow-a", "llm-workflow-b"):
        store._ingest_event_sync(
            server.id,
            source_kind="terminal",
            actor_kind="human",
            source_ref=session_id,
            session_id=session_id,
            event_type="command_executed",
            raw_text="$ nginx -t\nsyntax is ok",
            structured_payload={"command": "nginx -t", "exit_code": 0, "cwd": "/etc/nginx"},
            importance_hint=0.68,
            actor_user_id=owner.id,
        )
        store._ingest_event_sync(
            server.id,
            source_kind="terminal",
            actor_kind="human",
            source_ref=session_id,
            session_id=session_id,
            event_type="command_executed",
            raw_text="$ systemctl reload nginx\nreload requested",
            structured_payload={"command": "systemctl reload nginx", "exit_code": 0, "cwd": "/etc/nginx"},
            importance_hint=0.82,
            actor_user_id=owner.id,
        )
        store._ingest_event_sync(
            server.id,
            source_kind="terminal",
            actor_kind="human",
            source_ref=session_id,
            session_id=session_id,
            event_type="command_executed",
            raw_text="$ systemctl is-active nginx\nactive",
            structured_payload={"command": "systemctl is-active nginx", "exit_code": 0, "cwd": "/etc/nginx"},
            importance_hint=0.72,
            actor_user_id=owner.id,
        )

    async def fake_stream_chat(self, prompt: str, model: str = "auto", purpose: str = "chat", specific_model=None):
        if "Workflow candidates" in prompt:
            yield (
                '[{"normalized_command":"nginx -t => systemctl reload nginx","when_to_use":"перед безопасным reload после правки конфига",'
                '"automation_hint":"сначала проверить синтаксис, потом reload и потом status","skill_summary":"безопасный nginx reload workflow",'
                '"verification":"проверить is-active nginx и отсутствие ошибок в journalctl","success_signals":["syntax is ok","active"]}]'
            )
            return
        yield '{"profile":"- nginx установлен","access":"- Host: demo","risks":"- риски не изменились","runbook":"- использовать проверенный workflow reload","recent_changes":"- reload workflow подтвержден","human_habits":"- оператор предпочитает nginx -t перед reload"}'

    monkeypatch.setattr("app.core.llm.LLMProvider.stream_chat", fake_stream_chat, raising=False)

    result = store._run_dream_cycle_sync(server.id, job_kind="nightly")

    assert result["skipped"] is False
    automation_snapshots = [
        item
        for item in ServerMemorySnapshot.objects.filter(server=server, memory_key__startswith="automation_candidate:", is_active=True)
        if item.metadata.get("pattern_kind") == "sequence"
    ]
    skill_snapshots = [
        item
        for item in ServerMemorySnapshot.objects.filter(server=server, memory_key__startswith="skill_draft:", is_active=True)
        if item.metadata.get("pattern_kind") == "sequence"
    ]
    assert any(item.metadata.get("llm_enhanced") is True for item in automation_snapshots)
    assert any("безопасный nginx reload workflow" in item.content for item in skill_snapshots)


@pytest.mark.django_db(transaction=True)
def test_run_dream_cycle_respects_sleep_window_and_recent_activity():
    owner = User.objects.create_user(username="ops-memory-schedule-user", password="x")
    server = Server.objects.create(user=owner, name="schedule-node", host="10.0.0.33", port=22, username="root")
    policy = ServerMemoryPolicy.objects.create(
        user=owner,
        dream_mode=ServerMemoryPolicy.DREAM_HYBRID,
        sleep_start_hour=(timezone.localtime().hour + 1) % 24,
        sleep_end_hour=(timezone.localtime().hour + 2) % 24,
    )
    store = DjangoServerMemoryStore()

    outside_window = store._run_dream_cycle_sync(server.id, job_kind="nightly", respect_schedule=True)
    assert outside_window["skipped"] is True
    assert outside_window["reason"] == "outside_sleep_window"

    policy.sleep_start_hour = timezone.localtime().hour
    policy.sleep_end_hour = (timezone.localtime().hour + 1) % 24
    policy.save(update_fields=["sleep_start_hour", "sleep_end_hour", "updated_at"])
    store._ingest_event_sync(
        server.id,
        source_kind="terminal",
        actor_kind="human",
        source_ref="active-session",
        session_id="active-session",
        event_type="command_executed",
        raw_text="$ uptime",
        structured_payload={"command": "uptime", "exit_code": 0},
        importance_hint=0.4,
        actor_user_id=owner.id,
    )
    active_window = store._run_dream_cycle_sync(server.id, job_kind="nightly", respect_schedule=True)
    assert active_window["skipped"] is True
    assert active_window["reason"] == "server_recently_active"


@pytest.mark.django_db(transaction=True)
def test_run_memory_dreams_command_updates_worker_state():
    owner = User.objects.create_user(username="dream-worker-user", password="x")
    Server.objects.create(user=owner, name="dream-worker-node", host="10.0.0.90", port=22, username="root")

    call_command("run_memory_dreams", once=True, limit=1, worker_key="pytest-dreams")

    state = BackgroundWorkerState.objects.get(
        worker_kind=BackgroundWorkerState.KIND_MEMORY_DREAMS,
        worker_key="pytest-dreams",
    )
    assert state.status == BackgroundWorkerState.STATUS_IDLE
    assert state.last_started_at is not None
    assert state.last_stopped_at is not None
    assert state.last_summary["servers"] >= 1


@pytest.mark.django_db(transaction=True)
def test_manual_knowledge_sync_creates_versioned_snapshots():
    owner = User.objects.create_user(username="ops-memory-manual-user", password="x")
    server = Server.objects.create(user=owner, name="manual-node", host="10.0.0.41", port=22, username="root")
    note = ServerKnowledge.objects.create(
        server=server,
        category="config",
        title="Main app upstream",
        content="proxy_pass http://127.0.0.1:8000;",
        source="manual",
        confidence=1.0,
        created_by=owner,
    )
    store = DjangoServerMemoryStore()
    first_snapshot_id = store._sync_manual_knowledge_snapshot_sync(note.id)
    note.content = "proxy_pass http://127.0.0.1:9000;"
    note.save(update_fields=["content", "updated_at"])
    second_snapshot_id = store._sync_manual_knowledge_snapshot_sync(note.id)

    assert first_snapshot_id != second_snapshot_id
    snapshots = list(ServerMemorySnapshot.objects.filter(server=server, memory_key=f"manual_note:{note.id}").order_by("version"))
    assert len(snapshots) == 2
    assert snapshots[0].is_active is False
    assert snapshots[1].is_active is True
