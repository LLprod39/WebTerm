import pytest
from django.contrib.auth.models import User

from servers.adapters.memory_store import DjangoServerMemoryStore
from servers.models import Server, ServerKnowledge, ServerMemoryEpisode, ServerMemorySnapshot


@pytest.mark.django_db(transaction=True)
def test_snapshot_versions_capture_rewrite_reason_and_history():
    owner = User.objects.create_user(username="ops-memory-history-user", password="x")
    server = Server.objects.create(user=owner, name="history-node", host="10.0.0.67", port=22, username="root")
    store = DjangoServerMemoryStore()

    first_snapshot, _ = store._upsert_snapshot_sync(
        server_id=server.id,
        memory_key="risks",
        title="Canonical Risks",
        content="- CPU saturation detected",
        source_kind="dream",
        confidence=0.72,
        metadata={"trust_level": "system_measured", "verification_status": "measured"},
    )
    second_snapshot, created = store._upsert_snapshot_sync(
        server_id=server.id,
        memory_key="risks",
        title="Canonical Risks",
        content="- CPU saturation detected\n- Disk pressure detected",
        source_kind="dream",
        confidence=0.84,
        metadata={"trust_level": "system_measured", "verification_status": "measured"},
    )

    assert created is True
    assert second_snapshot.version == first_snapshot.version + 1

    overview = store._get_memory_overview_sync(server.id)
    current = next(item for item in overview["canonical"] if item["memory_key"] == "risks")

    assert current["rewrite_reason"] == "Risk state changed"
    assert current["prior_version"] == 1
    assert any(history_item["rewrite_reason"] == "Risk state changed" for history_item in current["history"])


@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_promotes_command_patterns_to_habits_and_runbook():
    owner = User.objects.create_user(username="ops-memory-pattern-user", password="x")
    server = Server.objects.create(user=owner, name="pattern-node", host="10.0.0.32", port=22, username="root")
    store = DjangoServerMemoryStore()

    for index in range(4):
        session_id = f"ssh-pattern-{index}"
        store._ingest_event_sync(
            server.id,
            source_kind="terminal",
            actor_kind="human",
            source_ref=session_id,
            session_id=session_id,
            event_type="command_executed",
            raw_text="$ systemctl status nginx\nactive (running)",
            structured_payload={"command": "systemctl status nginx", "exit_code": 0},
            importance_hint=0.7,
            actor_user_id=owner.id,
        )
    for index in range(2):
        pipeline_session = f"pipeline-check-{index}"
        store._ingest_event_sync(
            server.id,
            source_kind="pipeline",
            actor_kind="agent",
            source_ref=pipeline_session,
            session_id=pipeline_session,
            event_type="command_executed",
            raw_text="$ docker ps --format table\nCONTAINER ID   IMAGE",
            structured_payload={"command": "docker ps --format table", "exit_code": 0},
            importance_hint=0.68,
            actor_user_id=owner.id,
        )

    result = store._run_dream_cycle_sync(server.id, job_kind="nearline")

    assert result["skipped"] is False
    habits = ServerMemorySnapshot.objects.get(server=server, memory_key="human_habits", is_active=True)
    runbook = ServerMemorySnapshot.objects.get(server=server, memory_key="runbook", is_active=True)
    pattern_candidates = ServerMemorySnapshot.objects.filter(
        server=server, memory_key__startswith="pattern_candidate:", is_active=True
    )
    automation_candidates = ServerMemorySnapshot.objects.filter(
        server=server,
        memory_key__startswith="automation_candidate:",
        is_active=True,
    )
    skill_drafts = ServerMemorySnapshot.objects.filter(
        server=server, memory_key__startswith="skill_draft:", is_active=True
    )
    assert "systemctl status nginx" in habits.content
    assert "docker ps --format table" not in runbook.content
    assert any("docker ps --format table" in item.content for item in pattern_candidates)
    assert "4 запусков в 4 сессиях" in habits.content
    assert pattern_candidates.exists()
    assert automation_candidates.exists()
    assert skill_drafts.exists()

    overview = store._get_memory_overview_sync(server.id)
    assert overview["patterns"]
    assert overview["automation_candidates"]
    assert overview["skill_drafts"]
    card = store._get_server_card_sync(server.id)
    prompt_text = card.as_prompt_block()
    assert "Learned Pattern:" not in prompt_text
    assert "Automation Candidate:" not in prompt_text
    assert "Skill Draft:" not in prompt_text
    assert "[human_observed][measured]" in prompt_text or "[system_measured][measured]" in prompt_text


@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_extracts_recent_docker_changes_without_false_habits():
    owner = User.objects.create_user(username="ops-memory-docker-once-user", password="x")
    server = Server.objects.create(user=owner, name="docker-once-node", host="10.0.0.72", port=22, username="root")
    store = DjangoServerMemoryStore()

    session_id = "docker-once-session"
    store._ingest_event_sync(
        server.id,
        source_kind="terminal",
        actor_kind="human",
        source_ref=session_id,
        session_id=session_id,
        event_type="command_executed",
        raw_text="$ docker run -d --name nginx-web -p 80:80 --restart unless-stopped nginx:alpine\n6f00abc123",
        structured_payload={
            "command": "docker run -d --name nginx-web -p 80:80 --restart unless-stopped nginx:alpine",
            "exit_code": 0,
        },
        importance_hint=0.84,
        actor_user_id=owner.id,
    )
    store._ingest_event_sync(
        server.id,
        source_kind="terminal",
        actor_kind="human",
        source_ref=session_id,
        session_id=session_id,
        event_type="command_executed",
        raw_text=(
            "$ docker ps\n"
            "CONTAINER ID   IMAGE          COMMAND                  CREATED          STATUS         PORTS                  NAMES\n"
            '6f00abc123     nginx:alpine   "/docker-entrypoint.…"   9 seconds ago    Up 2 seconds   0.0.0.0:80->80/tcp     nginx-web'
        ),
        structured_payload={"command": "docker ps", "exit_code": 0},
        importance_hint=0.72,
        actor_user_id=owner.id,
    )

    result = store._run_dream_cycle_sync(server.id, job_kind="nearline")

    assert result["skipped"] is False
    recent_changes = ServerMemorySnapshot.objects.get(server=server, memory_key="recent_changes", is_active=True)
    access = ServerMemorySnapshot.objects.get(server=server, memory_key="access", is_active=True)
    habits = ServerMemorySnapshot.objects.get(server=server, memory_key="human_habits", is_active=True)

    assert "Запущен контейнер nginx-web из nginx:alpine" in recent_changes.content
    assert "80:80" in recent_changes.content
    assert "nginx-web доступен через 80:80" in access.content
    assert "docker ps подтверждает опубликованные порты: 80->80/tcp" in access.content
    assert "docker ps" not in habits.content
    assert "Повторяющиеся ручные привычки пока не выделены." in habits.content


@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_skips_transport_only_terminal_sessions():
    owner = User.objects.create_user(username="ops-memory-transport-noise-user", password="x")
    server = Server.objects.create(user=owner, name="transport-node", host="10.0.0.82", port=22, username="root")
    store = DjangoServerMemoryStore()

    session_id = "ssh-open-close-only"
    for event_type, raw_text in (
        ("session_opened", "SSH terminal session opened"),
        ("session_closed", "SSH terminal session closed"),
    ):
        store._ingest_event_sync(
            server.id,
            source_kind="terminal",
            actor_kind="human",
            source_ref=session_id,
            session_id=session_id,
            event_type=event_type,
            raw_text=raw_text,
            structured_payload={"connection_id": session_id, "user_id": owner.id},
            importance_hint=0.2,
            actor_user_id=owner.id,
        )

    result = store._run_dream_cycle_sync(server.id, job_kind="nearline")

    assert result["skipped"] is False
    assert not ServerMemoryEpisode.objects.filter(
        server=server,
        episode_kind="terminal_session",
        is_active=True,
    ).exists()
    access = ServerMemorySnapshot.objects.get(server=server, memory_key="access", is_active=True)
    assert "session_opened" not in access.content
    assert "SSH terminal session opened" not in access.content
    prompt_text = store._get_server_card_sync(server.id).as_prompt_block()
    assert "session_opened" not in prompt_text
    assert "SSH terminal session opened" not in prompt_text


@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_routes_ai_profile_note_to_profile_section():
    owner = User.objects.create_user(username="ops-memory-profile-note-user", password="x")
    server = Server.objects.create(user=owner, name="profile-node", host="10.0.0.92", port=22, username="root")
    store = DjangoServerMemoryStore()
    knowledge = ServerKnowledge.objects.create(
        server=server,
        category="config",
        title="Профиль сервера (авто)",
        content=(
            "Обновлено: 2026-04-09 18:54\n"
            "Кратко: Сервер WSL2 с Docker-контейнерами.\n"
            "Факты:\n"
            "- Docker контейнеры: nginx-web (порт 80), redis (порт 6379)\n"
            "- Host: 172.25.173.251:22 user=lunix"
        ),
        source="ai_auto",
        confidence=0.91,
        created_by=owner,
    )

    store._sync_manual_knowledge_snapshot_sync(knowledge.id)

    profile = ServerMemorySnapshot.objects.get(server=server, memory_key="profile", is_active=True)
    runbook = ServerMemorySnapshot.objects.get(server=server, memory_key="runbook", is_active=True)

    assert "Docker контейнеры" in profile.content
    assert "Docker контейнеры" not in runbook.content


@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_does_not_promote_destructive_docker_rm_patterns():
    owner = User.objects.create_user(username="ops-memory-docker-rm-user", password="x")
    server = Server.objects.create(user=owner, name="docker-rm-node", host="10.0.0.93", port=22, username="root")
    store = DjangoServerMemoryStore()

    for index in range(3):
        session_id = f"docker-rm-session-{index}"
        store._ingest_event_sync(
            server.id,
            source_kind="terminal",
            actor_kind="human",
            source_ref=session_id,
            session_id=session_id,
            event_type="command_executed",
            raw_text="$ docker rm -f nginx-web\nnginx-web",
            structured_payload={"command": "docker rm -f nginx-web", "exit_code": 0},
            importance_hint=0.74,
            actor_user_id=owner.id,
        )

    result = store._run_dream_cycle_sync(server.id, job_kind="nearline")

    assert result["skipped"] is False
    habits = ServerMemorySnapshot.objects.get(server=server, memory_key="human_habits", is_active=True)
    runbook = ServerMemorySnapshot.objects.get(server=server, memory_key="runbook", is_active=True)
    assert "docker rm -f nginx-web" not in habits.content
    assert "docker rm -f nginx-web" not in runbook.content
    assert not ServerMemorySnapshot.objects.filter(
        server=server,
        is_active=True,
        memory_key__startswith="automation_candidate:",
    ).exists()
    assert not ServerMemorySnapshot.objects.filter(
        server=server,
        is_active=True,
        memory_key__startswith="skill_draft:",
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_unknown_pattern_success_requires_review_and_does_not_become_recipe():
    owner = User.objects.create_user(username="ops-memory-unknown-pattern-user", password="x")
    server = Server.objects.create(user=owner, name="unknown-pattern-node", host="10.0.0.74", port=22, username="root")
    store = DjangoServerMemoryStore()

    for index in range(3):
        session_id = f"unknown-pattern-{index}"
        store._ingest_event_sync(
            server.id,
            source_kind="terminal",
            actor_kind="human",
            source_ref=session_id,
            session_id=session_id,
            event_type="command_executed",
            raw_text="$ custom-check\noutput without exit code",
            structured_payload={"command": "custom-check"},
            importance_hint=0.55,
            actor_user_id=owner.id,
        )

    result = store._run_dream_cycle_sync(server.id, job_kind="nearline")

    assert result["skipped"] is False
    pattern = ServerMemorySnapshot.objects.get(
        server=server,
        memory_key__startswith="pattern_candidate:",
        is_active=True,
    )
    assert pattern.layer == ServerMemorySnapshot.LAYER_CANDIDATE
    assert pattern.metadata["success_rate"] is None
    assert pattern.metadata["requires_manual_review"] is True
    assert pattern.confidence <= 0.55
    assert not ServerMemorySnapshot.objects.filter(
        server=server,
        memory_key__startswith="automation_candidate:",
        is_active=True,
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_operational_recipes_exclude_unreviewed_candidates():
    owner = User.objects.create_user(username="ops-memory-candidate-recipe-user", password="x")
    server = Server.objects.create(user=owner, name="candidate-recipe-node", host="10.0.0.75", port=22, username="root")
    ServerMemorySnapshot.objects.create(
        server=server,
        memory_key="automation_candidate:unsafe",
        layer=ServerMemorySnapshot.LAYER_CANDIDATE,
        title="Automation Candidate: restart service",
        content="- systemctl restart nginx\n- systemctl is-active nginx",
        source_kind="dream",
        version_group_id="candidate-unsafe",
        version=1,
        is_active=True,
        metadata={
            "trust_level": "llm_distilled",
            "verification_status": "needs_revalidation",
            "candidate_requires_review": True,
        },
    )
    store = DjangoServerMemoryStore()

    prompt = store._build_operational_recipes_prompt_sync(
        "restart nginx service",
        server_ids=[server.id],
        limit=4,
    )

    assert "Automation Candidate" not in prompt
    assert "systemctl restart nginx" not in prompt


@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_does_not_treat_setup_steps_as_habits():
    owner = User.objects.create_user(username="ops-memory-setup-habit-user", password="x")
    server = Server.objects.create(user=owner, name="setup-node", host="10.0.0.94", port=22, username="root")
    store = DjangoServerMemoryStore()

    for index in range(4):
        session_id = f"setup-session-{index}"
        store._ingest_event_sync(
            server.id,
            source_kind="terminal",
            actor_kind="human",
            source_ref=session_id,
            session_id=session_id,
            event_type="command_executed",
            raw_text="$ mkdir -p ~/nginx-html",
            structured_payload={"command": "mkdir -p ~/nginx-html", "exit_code": 0},
            importance_hint=0.42,
            actor_user_id=owner.id,
        )

    result = store._run_dream_cycle_sync(server.id, job_kind="nearline")

    assert result["skipped"] is False
    habits = ServerMemorySnapshot.objects.get(server=server, memory_key="human_habits", is_active=True)
    assert "mkdir -p ~/nginx-html" not in habits.content
    assert "Повторяющиеся ручные привычки пока не выделены." in habits.content


@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_does_not_put_ssh_service_checks_into_access():
    owner = User.objects.create_user(username="ops-memory-ssh-status-user", password="x")
    server = Server.objects.create(user=owner, name="ssh-status-node", host="10.0.0.95", port=22, username="lunix")
    store = DjangoServerMemoryStore()

    session_id = "ssh-service-check"
    store._ingest_event_sync(
        server.id,
        source_kind="terminal",
        actor_kind="human",
        source_ref=session_id,
        session_id=session_id,
        event_type="command_executed",
        raw_text="$ systemctl status ssh --no-pager\nactive (running)",
        structured_payload={"command": "systemctl status ssh --no-pager", "exit_code": 0},
        importance_hint=0.55,
        actor_user_id=owner.id,
    )

    result = store._run_dream_cycle_sync(server.id, job_kind="nearline")

    assert result["skipped"] is False
    access = ServerMemorySnapshot.objects.get(server=server, memory_key="access", is_active=True)
    assert "Host: 10.0.0.95:22 user=lunix" in access.content
    assert "systemctl status ssh --no-pager" not in access.content
    assert "Command used" not in access.content


@pytest.mark.django_db(transaction=True)
def test_django_server_memory_store_learns_verified_command_sequences():
    owner = User.objects.create_user(username="ops-memory-sequence-user", password="x")
    server = Server.objects.create(user=owner, name="sequence-node", host="10.0.0.52", port=22, username="root")
    store = DjangoServerMemoryStore()

    for session_id in ("workflow-a", "workflow-b"):
        store._ingest_event_sync(
            server.id,
            source_kind="terminal",
            actor_kind="human",
            source_ref=session_id,
            session_id=session_id,
            event_type="command_executed",
            raw_text="$ systemctl restart nginx\nJob for nginx.service completed successfully.",
            structured_payload={"command": "systemctl restart nginx", "exit_code": 0, "cwd": "/etc/nginx"},
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

    result = store._run_dream_cycle_sync(server.id, job_kind="nearline")

    assert result["skipped"] is False
    automation = ServerMemorySnapshot.objects.filter(
        server=server,
        memory_key__startswith="automation_candidate:",
        is_active=True,
    ).order_by("-updated_at")
    skill_drafts = ServerMemorySnapshot.objects.filter(
        server=server,
        memory_key__startswith="skill_draft:",
        is_active=True,
    ).order_by("-updated_at")
    assert automation.exists()
    assert skill_drafts.exists()

    automation_snapshot = next(item for item in automation if item.metadata.get("pattern_kind") == "sequence")
    skill_snapshot = next(item for item in skill_drafts if item.metadata.get("pattern_kind") == "sequence")
    assert automation_snapshot.metadata["intent"] == "service"
    assert automation_snapshot.metadata["intent_label"] == "nginx restart with health verification"
    assert automation_snapshot.metadata["commands"] == ["systemctl restart nginx", "systemctl is-active nginx"]
    assert automation_snapshot.metadata["has_verification_step"] is True
    assert automation_snapshot.metadata["common_cwds"] == ["/etc/nginx"]
    assert "Intent: nginx restart with health verification" in automation_snapshot.content
    assert "Шаг 1" in automation_snapshot.content
    assert "systemctl is-active nginx" in automation_snapshot.content
    assert "active" in skill_snapshot.content
    assert "Skill Draft: nginx restart with health verification" in skill_snapshot.content
