import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from servers.models import Server, ServerMemorySnapshot


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _create_server(user: User, **kwargs) -> Server:
    return Server.objects.create(
        user=user,
        name=kwargs.pop("name", "srv-01"),
        host=kwargs.pop("host", "10.0.0.11"),
        username=kwargs.pop("username", "root"),
        auth_method=kwargs.pop("auth_method", "password"),
        **kwargs,
    )


@pytest.mark.django_db
def test_share_master_password_and_knowledge_endpoints(monkeypatch):
    owner = User.objects.create_user(username="owner", password="x")
    owner.is_staff = True
    owner.save(update_fields=["is_staff"])
    teammate = User.objects.create_user(username="shared-user", password="x")
    client = Client()
    client.force_login(owner)

    server = _create_server(owner, name="share-me", server_type="ssh", port=22)

    create_share = client.post(
        f"/servers/api/{server.id}/share/",
        data=_json({"user": teammate.username, "share_context": True}),
        content_type="application/json",
    )
    assert create_share.status_code == 200
    share_id = create_share.json()["share"]["id"]

    shares = client.get(f"/servers/api/{server.id}/shares/")
    assert shares.status_code == 200
    assert len(shares.json()["shares"]) == 1

    revoke = client.post(f"/servers/api/{server.id}/shares/{share_id}/revoke/")
    assert revoke.status_code == 200
    assert revoke.json()["success"] is True

    set_mp = client.post(
        "/servers/api/master-password/set/",
        data=_json({"master_password": "master-secret"}),
        content_type="application/json",
    )
    assert set_mp.status_code == 200
    assert set_mp.json()["success"] is True

    has_mp = client.get("/servers/api/master-password/check/")
    assert has_mp.status_code == 200
    assert has_mp.json()["has_master_password"] is True

    clear_mp = client.post("/servers/api/master-password/clear/")
    assert clear_mp.status_code == 200
    assert clear_mp.json()["success"] is True

    create_knowledge = client.post(
        f"/servers/api/{server.id}/knowledge/create/",
        data=_json({"title": "Nginx path", "content": "/etc/nginx/nginx.conf", "category": "config"}),
        content_type="application/json",
    )
    assert create_knowledge.status_code == 200
    knowledge_id = create_knowledge.json()["id"]

    list_knowledge = client.get(f"/servers/api/{server.id}/knowledge/")
    assert list_knowledge.status_code == 200
    assert list_knowledge.json()["success"] is True
    assert len(list_knowledge.json()["items"]) == 1

    memory_overview = client.get(f"/servers/api/{server.id}/memory/overview/")
    assert memory_overview.status_code == 200
    assert memory_overview.json()["success"] is True
    assert "daemon_state" in memory_overview.json()
    assert "worker_states" in memory_overview.json()
    assert memory_overview.json()["manual"]
    assert "patterns" in memory_overview.json()
    assert "automation_candidates" in memory_overview.json()
    assert "skill_drafts" in memory_overview.json()
    manual_snapshot = memory_overview.json()["manual"][0]
    assert "history" in manual_snapshot
    assert "action_summary" in manual_snapshot
    assert manual_snapshot["version_group_id"]
    assert "created_by_username" in manual_snapshot

    user_snapshot = ServerMemorySnapshot.objects.filter(server=server, memory_key="profile", is_active=True).first()
    if user_snapshot is None:
        user_snapshot = ServerMemorySnapshot.objects.create(
            server=server,
            created_by=owner,
            memory_key="profile",
            layer=ServerMemorySnapshot.LAYER_CANONICAL,
            title="Server profile",
            content="Ubuntu host with nginx",
            source_kind="manual",
            source_ref="test",
            version_group_id="profile-test",
            version=1,
            is_active=True,
            metadata={"rewrite_reason": "Merged duplicate profile notes"},
        )
    else:
        user_snapshot.title = "Server profile"
        user_snapshot.content = "Ubuntu host with nginx"
        user_snapshot.source_kind = "manual"
        user_snapshot.source_ref = "test"
        user_snapshot.metadata = {"rewrite_reason": "Merged duplicate profile notes"}
        user_snapshot.save(update_fields=["title", "content", "source_kind", "source_ref", "metadata", "updated_at"])

    list_snapshots = client.get(f"/servers/api/{server.id}/memory/snapshots/")
    assert list_snapshots.status_code == 200
    assert list_snapshots.json()["success"] is True
    snapshot_payload = next(item for item in list_snapshots.json()["items"] if item["id"] == user_snapshot.id)
    assert snapshot_payload["title"] == "Server profile"
    assert snapshot_payload["kind"] == "canonical"
    assert isinstance(snapshot_payload["freshness"], float)
    assert snapshot_payload["rewrite_reason"] == "Merged duplicate profile notes"

    ai_note_snapshot = ServerMemorySnapshot.objects.create(
        server=server,
        created_by=owner,
        memory_key="knowledge_note:999",
        layer=ServerMemorySnapshot.LAYER_CANONICAL,
        title="AI profile",
        content="Discovered by terminal AI",
        source_kind="manual_knowledge",
        source_ref="knowledge:999",
        version_group_id="knowledge-note-999",
        version=1,
        is_active=True,
    )
    list_snapshots = client.get(f"/servers/api/{server.id}/memory/snapshots/")
    assert list_snapshots.status_code == 200
    ai_note_payload = next(item for item in list_snapshots.json()["items"] if item["id"] == ai_note_snapshot.id)
    assert ai_note_payload["kind"] == "ai_note"

    update_snapshot = client.post(
        f"/servers/api/{server.id}/memory/snapshots/{user_snapshot.id}/update/",
        data=_json({"title": "Server profile updated", "content": "Ubuntu host with nginx and certbot"}),
        content_type="application/json",
    )
    assert update_snapshot.status_code == 200
    assert update_snapshot.json()["success"] is True
    user_snapshot.refresh_from_db()
    assert user_snapshot.title == "Server profile updated"
    assert user_snapshot.content == "Ubuntu host with nginx and certbot"

    snapshot_to_delete = ServerMemorySnapshot.objects.create(
        server=server,
        created_by=owner,
        memory_key="automation_candidate:test-delete-one",
        layer=ServerMemorySnapshot.LAYER_CANDIDATE,
        title="Delete one snapshot",
        content="Temporary AI memory",
        source_kind="dream",
        source_ref="test-delete",
        version_group_id="delete-one",
        version=1,
        is_active=True,
    )
    delete_snapshot = client.post(
        f"/servers/api/{server.id}/memory/snapshots/{snapshot_to_delete.id}/delete/",
        content_type="application/json",
    )
    assert delete_snapshot.status_code == 200
    assert delete_snapshot.json()["success"] is True
    assert ServerMemorySnapshot.objects.filter(pk=snapshot_to_delete.id).exists() is False

    snapshot_bulk_one = ServerMemorySnapshot.objects.create(
        server=server,
        created_by=owner,
        memory_key="pattern_candidate:test-bulk-one",
        layer=ServerMemorySnapshot.LAYER_CANDIDATE,
        title="Bulk delete one",
        content="Temporary AI memory one",
        source_kind="dream",
        source_ref="test-bulk",
        version_group_id="bulk-one",
        version=1,
        is_active=True,
    )
    snapshot_bulk_two = ServerMemorySnapshot.objects.create(
        server=server,
        created_by=owner,
        memory_key="pattern_candidate:test-bulk-two",
        layer=ServerMemorySnapshot.LAYER_CANDIDATE,
        title="Bulk delete two",
        content="Temporary AI memory two",
        source_kind="dream",
        source_ref="test-bulk",
        version_group_id="bulk-two",
        version=1,
        is_active=True,
    )
    bulk_delete_snapshots = client.post(
        f"/servers/api/{server.id}/memory/snapshots/bulk-delete/",
        data=_json({"snapshot_ids": [snapshot_bulk_one.id, snapshot_bulk_two.id]}),
        content_type="application/json",
    )
    assert bulk_delete_snapshots.status_code == 200
    assert bulk_delete_snapshots.json()["success"] is True
    assert bulk_delete_snapshots.json()["deleted_count"] == 2
    assert ServerMemorySnapshot.objects.filter(pk=snapshot_bulk_one.id).exists() is False
    assert ServerMemorySnapshot.objects.filter(pk=snapshot_bulk_two.id).exists() is False

    update_knowledge = client.post(
        f"/servers/api/{server.id}/knowledge/{knowledge_id}/update/",
        data=_json({"title": "Nginx main config", "is_active": False, "confidence": 0.6}),
        content_type="application/json",
    )
    assert update_knowledge.status_code == 200
    assert update_knowledge.json()["success"] is True

    run_dreams = client.post(
        f"/servers/api/{server.id}/memory/run-dreams/",
        data=_json({"job_kind": "hybrid"}),
        content_type="application/json",
    )
    assert run_dreams.status_code == 200
    assert run_dreams.json()["success"] is True
    assert run_dreams.json()["overview"]["success"] is True
    assert "patterns" in run_dreams.json()["overview"]
    assert "automation_candidates" in run_dreams.json()["overview"]
    assert "skill_drafts" in run_dreams.json()["overview"]

    update_memory_policy = client.post(
        f"/servers/api/{server.id}/memory/policy/",
        data=_json(
            {
                "dream_mode": "nightly_llm",
                "nightly_model_alias": "opssummary",
                "nearline_event_threshold": 9,
                "sleep_start_hour": 2,
                "sleep_end_hour": 6,
                "human_habits_capture_enabled": False,
            }
        ),
        content_type="application/json",
    )
    assert update_memory_policy.status_code == 200
    assert update_memory_policy.json()["success"] is True
    assert update_memory_policy.json()["overview"]["policy"]["dream_mode"] == "nightly_llm"
    assert update_memory_policy.json()["overview"]["policy"]["nearline_event_threshold"] == 9
    assert update_memory_policy.json()["overview"]["policy"]["human_habits_capture_enabled"] is False
    assert update_memory_policy.json()["overview"]["policy"]["is_enabled"] is True

    disable_memory_policy = client.post(
        f"/servers/api/{server.id}/memory/policy/",
        data=_json({"is_enabled": False}),
        content_type="application/json",
    )
    assert disable_memory_policy.status_code == 200
    assert disable_memory_policy.json()["success"] is True
    assert disable_memory_policy.json()["overview"]["policy"]["is_enabled"] is False

    forced_run_dreams = client.post(
        f"/servers/api/{server.id}/memory/run-dreams/",
        data=_json({"job_kind": "nearline"}),
        content_type="application/json",
    )
    assert forced_run_dreams.status_code == 200
    assert forced_run_dreams.json()["success"] is True
    assert forced_run_dreams.json()["result"]["skipped"] is False

    delete_knowledge = client.post(
        f"/servers/api/{server.id}/knowledge/{knowledge_id}/delete/",
        content_type="application/json",
    )
    assert delete_knowledge.status_code == 200
    assert delete_knowledge.json()["success"] is True

    server.auth_method = "password"
    server.save(update_fields=["auth_method"])
    from servers.secret_utils import store_server_auth_secret

    store_server_auth_secret(server, secret_value="plain-password")
    reveal = client.post(
        f"/servers/api/{server.id}/reveal-password/",
        data=_json({}),
        content_type="application/json",
    )
    assert reveal.status_code == 200
    assert reveal.json()["success"] is True
    assert reveal.json()["password"] == "plain-password"
