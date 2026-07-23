import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from servers.models import (
    ServerKnowledge,
    ServerMemoryEpisode,
    ServerMemoryEvent,
    ServerMemoryRevalidation,
    ServerMemorySnapshot,
)
from tests.servers_api_smoke_harness import (
    create_server as _create_server,
)
from tests.servers_api_smoke_harness import (
    grant_feature as _grant_feature,
)
from tests.servers_api_smoke_harness import (
    json_payload as _json,
)


@pytest.mark.django_db
def test_server_memory_purge_user_clears_ai_memory_everywhere():
    from servers.adapters.memory_store import DjangoServerMemoryStore

    owner = User.objects.create_user(username="purge-owner", password="x")
    owner.is_staff = True
    owner.save(update_fields=["is_staff"])
    _grant_feature(owner, "servers")
    client = Client()
    client.force_login(owner)

    server = _create_server(owner, name="forget-me", server_type="ssh", port=22)
    store = DjangoServerMemoryStore()

    manual_knowledge = ServerKnowledge.objects.create(
        server=server,
        category="config",
        title="Manual note",
        content="Keep this manual note",
        source="manual",
        is_active=True,
        created_by=owner,
    )
    store._sync_manual_knowledge_snapshot_sync(manual_knowledge.id)

    ai_knowledge = ServerKnowledge.objects.create(
        server=server,
        category="issues",
        title="AI note",
        content="Delete this AI note",
        source="ai_auto",
        is_active=True,
        created_by=owner,
    )
    store._sync_manual_knowledge_snapshot_sync(ai_knowledge.id)

    canonical_snapshot = ServerMemorySnapshot.objects.filter(
        server=server, memory_key="profile", is_active=True
    ).first()
    if canonical_snapshot is None:
        canonical_snapshot = ServerMemorySnapshot.objects.create(
            server=server,
            created_by=owner,
            memory_key="profile",
            layer=ServerMemorySnapshot.LAYER_CANONICAL,
            title="Canonical profile",
            content="Ephemeral AI memory",
            source_kind="dream",
            source_ref="dream:test",
            version_group_id="purge-profile",
            version=1,
            is_active=True,
            metadata={"trust_level": "system_measured", "verification_status": "measured"},
        )
    ServerMemoryRevalidation.objects.create(
        server=server,
        source_snapshot=canonical_snapshot,
        memory_key="profile",
        title="Review profile",
        reason="stale",
    )
    ServerMemoryEpisode.objects.create(
        server=server,
        episode_kind=ServerMemoryEpisode.KIND_AGENT,
        source_kind="agent_run",
        source_ref="run:123",
        session_id="run:123",
        title="AI episode",
        summary="Summarized AI history",
        event_count=2,
        is_active=True,
    )
    ServerMemoryEvent.objects.create(
        server=server,
        actor_user=owner,
        source_kind=ServerMemoryEvent.SOURCE_AGENT_RUN,
        actor_kind=ServerMemoryEvent.ACTOR_AGENT,
        source_ref="run:123",
        session_id="run:123",
        event_type="run_completed",
        raw_text_redacted="temporary AI payload",
    )

    purge_response = client.post(f"/servers/api/{server.id}/memory/purge/")
    assert purge_response.status_code == 200
    payload = purge_response.json()
    assert payload["success"] is True
    assert payload["deleted"]["snapshots"] >= 2
    assert payload["deleted"]["episodes"] >= 1
    assert payload["deleted"]["events"] >= 1
    assert payload["deleted"]["revalidations"] >= 1
    assert payload["deleted"]["knowledge"] >= 1

    assert ServerKnowledge.objects.filter(pk=manual_knowledge.id, server=server).exists() is True
    assert (
        ServerMemorySnapshot.objects.filter(server=server, memory_key=f"manual_note:{manual_knowledge.id}").exists()
        is True
    )
    assert ServerKnowledge.objects.filter(pk=ai_knowledge.id, server=server).exists() is False
    assert ServerMemorySnapshot.objects.filter(server=server, memory_key="profile").exists() is False
    assert (
        ServerMemorySnapshot.objects.filter(server=server, memory_key=f"knowledge_note:{ai_knowledge.id}").exists()
        is False
    )
    assert ServerMemoryEpisode.objects.filter(server=server).exists() is False
    assert ServerMemoryEvent.objects.filter(server=server).exists() is False
    assert ServerMemoryRevalidation.objects.filter(server=server).exists() is False

    overview = client.get(f"/servers/api/{server.id}/memory/overview/")
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["success"] is True
    assert overview_payload["stats"]["episodes"] == 0
    assert overview_payload["stats"]["archive"] == 0


@pytest.mark.django_db
def test_server_memory_snapshot_actions_promote_archive_and_skill_scaffold(tmp_path):
    from studio.models import StudioSkillAccess
    from studio.skill_registry import get_skill

    owner = User.objects.create_user(username="memory-owner", password="x")
    owner.is_staff = True
    owner.save(update_fields=["is_staff"])
    _grant_feature(owner, "servers", "studio_skills")
    client = Client()
    client.force_login(owner)
    server = _create_server(owner, name="memory-srv", server_type="ssh", port=22)

    pattern_snapshot = ServerMemorySnapshot.objects.create(
        server=server,
        created_by=owner,
        memory_key="pattern_candidate:demo1234",
        layer=ServerMemorySnapshot.LAYER_CANDIDATE,
        title="Learned Pattern: diagnostics :: uptime && free -h",
        content="- Команда: uptime && free -h\n- Intent: diagnostics\n- Повторяемость: 4 запусков\n- Успех: 4/4 (100%)",
        source_kind="dream",
        source_ref="episode:1",
        version_group_id="pattern-demo1234",
        version=1,
        is_active=True,
        importance_score=0.64,
        stability_score=0.72,
        confidence=0.91,
        metadata={
            "intent": "diagnostics",
            "display_command": "uptime && free -h",
            "occurrences": 4,
            "successful_runs": 4,
            "measured_runs": 4,
            "success_rate": 1.0,
            "actor_kinds": ["human"],
            "source_kinds": ["terminal"],
        },
    )
    automation_snapshot = ServerMemorySnapshot.objects.create(
        server=server,
        created_by=owner,
        memory_key="automation_candidate:demo5678",
        layer=ServerMemorySnapshot.LAYER_CANDIDATE,
        title="Automation Candidate: service :: systemctl restart nginx",
        content="- Базовая команда: systemctl restart nginx\n- Intent: service\n- Шаг 2: проверить `systemctl is-active nginx`.",
        source_kind="dream",
        source_ref="episode:2",
        version_group_id="automation-demo5678",
        version=1,
        is_active=True,
        importance_score=0.72,
        stability_score=0.8,
        confidence=0.94,
        metadata={
            "intent": "service",
            "display_command": "systemctl restart nginx",
            "occurrences": 5,
            "successful_runs": 5,
            "measured_runs": 5,
            "success_rate": 1.0,
            "actor_kinds": ["human"],
            "source_kinds": ["terminal"],
        },
    )
    skill_snapshot = ServerMemorySnapshot.objects.create(
        server=server,
        created_by=owner,
        memory_key="skill_draft:demo9012",
        layer=ServerMemorySnapshot.LAYER_CANDIDATE,
        title="Skill Draft: service :: systemctl restart nginx -> systemctl is-active nginx",
        content=(
            "# Skill Draft: service\n"
            "- Trigger: задачи, где нужен workflow `systemctl restart nginx -> systemctl is-active nginx`.\n"
            "- Reuse signal: 4 повторений, успех 100%.\n"
            "- Workflow:\n"
            "  - Step 1: systemctl restart nginx\n"
            "  - Step 2: systemctl is-active nginx\n"
            "- Verification: последний шаг workflow уже выступает как verification; нужно проверить его exit code и сигнал результата.\n"
            "- Success signals: active (running) | nginx.service active\n"
        ),
        source_kind="dream",
        source_ref="episode:3",
        version_group_id="skill-demo9012",
        version=1,
        is_active=True,
        importance_score=0.76,
        stability_score=0.84,
        confidence=0.96,
        metadata={
            "intent": "service",
            "display_command": "systemctl restart nginx -> systemctl is-active nginx",
            "pattern_kind": "sequence",
            "commands": ["systemctl restart nginx", "systemctl is-active nginx"],
            "occurrences": 4,
            "successful_runs": 4,
            "measured_runs": 4,
            "success_rate": 1.0,
            "has_verification_step": True,
            "verification_rate": 1.0,
            "sample_outputs": ["active (running)", "nginx.service active"],
            "common_cwds": ["/etc/nginx", "/srv/app"],
            "actor_kinds": ["human"],
            "source_kinds": ["terminal"],
        },
    )

    promote_note = client.post(
        f"/servers/api/{server.id}/memory/snapshots/{pattern_snapshot.id}/promote-note/",
        data=_json({}),
        content_type="application/json",
    )
    assert promote_note.status_code == 200
    promote_note_payload = promote_note.json()
    assert promote_note_payload["success"] is True
    assert promote_note_payload["knowledge_id"] > 0
    assert "manual" in promote_note_payload["overview"]
    assert "worker_states" in promote_note_payload["overview"]
    pattern_snapshot.refresh_from_db()
    assert pattern_snapshot.is_active is False
    assert pattern_snapshot.layer == ServerMemorySnapshot.LAYER_ARCHIVE

    archive_response = client.post(
        f"/servers/api/{server.id}/memory/snapshots/{automation_snapshot.id}/archive/",
        data=_json({}),
        content_type="application/json",
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["success"] is True
    assert "worker_states" in archive_response.json()["overview"]
    automation_snapshot.refresh_from_db()
    assert automation_snapshot.is_active is False
    assert automation_snapshot.layer == ServerMemorySnapshot.LAYER_ARCHIVE

    with override_settings(STUDIO_SKILLS_DIRS=[str(tmp_path)]):
        promote_skill = client.post(
            f"/servers/api/{server.id}/memory/snapshots/{skill_snapshot.id}/promote-skill/",
            data=_json({}),
            content_type="application/json",
        )
        assert promote_skill.status_code == 200
        promote_skill_payload = promote_skill.json()
        assert promote_skill_payload["success"] is True
        skill_slug = promote_skill_payload["skill"]["slug"]
        skill = get_skill(skill_slug)
        assert skill.slug == skill_slug
        assert "Derived Draft" in skill.content
        assert "Derived Workflow" in skill.content
        assert "Success Signals" in skill.content
        assert promote_skill_payload["knowledge_id"] > 0
        assert "worker_states" in promote_skill_payload["overview"]
        assert ServerKnowledge.objects.filter(
            server=server, id=promote_skill_payload["knowledge_id"], is_active=True
        ).exists()
        assert StudioSkillAccess.objects.filter(slug=skill_slug, owner=owner).exists()

    skill_snapshot.refresh_from_db()
    assert skill_snapshot.is_active is False
    assert skill_snapshot.layer == ServerMemorySnapshot.LAYER_ARCHIVE
