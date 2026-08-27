import hashlib
import json

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from core_ui.models.projects import ProjectMembership
from core_ui.projects import create_project
from servers.models import (
    Playbook,
    PlaybookDraft,
    PlaybookRevision,
    PlaybookRun,
    Server,
    ServerMemoryAsset,
    ServerMemoryGenerationLog,
    ServerMemoryPromotion,
    ServerMemorySnapshot,
    ServerShare,
)
from servers.services.memory_asset_access import create_memory_asset
from servers.services.memory_asset_promotion import MemoryPromotionError, promote_memory_asset
from servers.services.playbooks.revisions import initialize_created_playbook, update_draft


def _project(owner, name):
    return create_project(owner=owner, name=name, activate=True)


def _server(owner, project, name="promotion-node"):
    return Server.objects.create(
        user=owner,
        project=project,
        name=name,
        host="10.90.0.1",
        port=22,
        username="root",
    )


def _generation_log(server):
    return ServerMemoryGenerationLog.objects.create(
        server=server,
        generation_kind=ServerMemoryGenerationLog.KIND_DISTILLATION,
        status=ServerMemoryGenerationLog.STATUS_SUCCEEDED,
        model_alias="opssummary",
        prompt_template_key="memory-promotion-test",
        prompt_template_version="1",
        prompt_sha256="a" * 64,
        output_sha256="b" * 64,
    )


def _asset(
    server,
    owner,
    *,
    title="Promotion asset",
    payload=None,
    lifecycle=ServerMemoryAsset.LIFECYCLE_APPROVED,
    generation_log=None,
):
    if payload is None:
        payload = {
            "content_format": PlaybookRevision.FORMAT_RUNBOOK_JSON,
            "tasks": [{"id": "restart", "command": "systemctl restart nginx"}],
            "secret_references": {"db_password": "managed://playbook-binding/7/db_password"},
        }
    layer = (
        ServerMemorySnapshot.LAYER_CANONICAL
        if lifecycle == ServerMemoryAsset.LIFECYCLE_APPROVED
        else ServerMemorySnapshot.LAYER_CANDIDATE
    )
    snapshot = ServerMemorySnapshot.objects.create(
        server=server,
        memory_key=f"promotion:{title.casefold().replace(' ', '-')}",
        layer=layer,
        title=title,
        content=payload if isinstance(payload, str) else json.dumps(payload),
        source_kind="llm" if generation_log else "manual",
        version_group_id=f"promotion-{title.casefold().replace(' ', '-')}",
        generation_log=generation_log,
    )
    return create_memory_asset(
        server=server,
        stable_key=title.casefold().replace(" ", "-"),
        title=title,
        current_snapshot=snapshot,
        created_by=owner,
        approved_by=owner if lifecycle == ServerMemoryAsset.LIFECYCLE_APPROVED else None,
        generation_log=generation_log,
        asset_kind=ServerMemoryAsset.KIND_RUNBOOK,
        lifecycle=lifecycle,
    )


def _playbook(owner, project, name="Promotion Target"):
    playbook = Playbook.objects.create(
        user=owner,
        project=project,
        name=name,
        kind=Playbook.KIND_RUNBOOK,
        tasks=[{"id": "baseline", "command": "systemctl status nginx"}],
    )
    initialize_created_playbook(playbook, actor=owner, origin_type=PlaybookRevision.ORIGIN_MANUAL)
    playbook.refresh_from_db()
    return playbook


def _stable_runtime_fingerprint(monkeypatch):
    monkeypatch.setattr(
        "servers.services.playbooks.validation.runtime_fingerprint",
        lambda: {
            "method": "test",
            "available": True,
            "runtime_digest": "test-runtime",
            "config_hash": "test-config",
            "analyzer_version": "test",
        },
    )


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_PROMOTION_ENABLED=True)
def test_playbook_promotion_is_idempotent_validated_unpublished_and_provenanced(monkeypatch, settings):
    _stable_runtime_fingerprint(monkeypatch)
    owner = User.objects.create_user(username="promotion-owner", password="x", is_staff=True)
    project = _project(owner, "Promotion Project")
    server = _server(owner, project)
    generation_log = _generation_log(server)
    asset = _asset(server, owner, generation_log=generation_log)
    ServerMemorySnapshot.objects.filter(pk=asset.current_snapshot_id).update(content_hash="")
    asset.current_snapshot.refresh_from_db()
    playbook = _playbook(owner, project)
    baseline_published_id = playbook.published_revision_id
    baseline_revision_count = playbook.content_revisions.count()

    promotion = promote_memory_asset(
        asset=asset,
        actor=owner,
        destination_kind=ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION,
        playbook=playbook,
    )
    duplicate = promote_memory_asset(
        asset=asset,
        actor=owner,
        destination_kind=ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION,
        playbook=playbook,
    )

    playbook.refresh_from_db()
    assert duplicate.id == promotion.id
    assert ServerMemoryPromotion.objects.count() == 1
    assert playbook.content_revisions.count() == baseline_revision_count + 1
    assert promotion.status == ServerMemoryPromotion.STATUS_VALIDATED
    assert promotion.source_asset_id == asset.id
    assert promotion.source_snapshot_id == asset.current_snapshot_id
    assert promotion.generation_log_id == generation_log.id
    assert promotion.requested_by_id == owner.id
    assert promotion.playbook_id == playbook.id
    assert promotion.playbook_revision.playbook_id == playbook.id
    assert promotion.validation_result["source"]["snapshot_id"] == asset.current_snapshot_id
    assert (
        promotion.validation_result["source"]["snapshot_content_hash"]
        == hashlib.sha256(asset.current_snapshot.content.encode("utf-8")).hexdigest()
    )
    assert promotion.validation_result["destination"]["revision_id"] == promotion.playbook_revision_id
    assert promotion.validation_result["destination"]["published"] is False
    assert promotion.validation_result["binding_required"] is True
    assert promotion.validation_result["managed_secret_reference_names"] == ["db_password"]
    assert promotion.validation_result["validation"]["status"] == "ready"
    assert "runtime_fingerprint" not in promotion.validation_result["validation"]
    assert len(json.dumps(promotion.validation_result).encode()) <= 16_000
    assert playbook.published_revision_id == baseline_published_id
    assert not PlaybookRun.objects.filter(playbook=playbook).exists()

    settings.SERVER_MEMORY_PROMOTION_ENABLED = False
    with pytest.raises(MemoryPromotionError, match="disabled"):
        promote_memory_asset(
            asset=asset,
            actor=owner,
            destination_kind=ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION,
            playbook=playbook,
        )
    assert ServerMemoryPromotion.objects.filter(pk=promotion.id).exists()


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_PROMOTION_ENABLED=True)
def test_llm_candidate_cannot_promote():
    owner = User.objects.create_user(username="promotion-candidate-owner", password="x", is_staff=True)
    project = _project(owner, "Candidate Promotion")
    server = _server(owner, project)
    asset = _asset(
        server,
        owner,
        title="LLM candidate",
        lifecycle=ServerMemoryAsset.LIFECYCLE_CANDIDATE,
        generation_log=_generation_log(server),
    )
    playbook = _playbook(owner, project)

    with pytest.raises(MemoryPromotionError) as exc_info:
        promote_memory_asset(
            asset=asset,
            actor=owner,
            destination_kind=ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION,
            playbook=playbook,
        )

    assert exc_info.value.code == "source_not_approved"
    assert not ServerMemoryPromotion.objects.exists()


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_PROMOTION_ENABLED=True)
def test_shared_or_non_owner_actor_and_foreign_playbook_are_denied():
    owner = User.objects.create_user(username="promotion-boundary-owner", password="x", is_staff=True)
    shared_staff = User.objects.create_user(username="promotion-shared-staff", password="x", is_staff=True)
    foreign_owner = User.objects.create_user(username="promotion-playbook-owner", password="x", is_staff=True)
    project = _project(owner, "Boundary Promotion")
    ProjectMembership.objects.create(
        project=project,
        user=shared_staff,
        role=ProjectMembership.ROLE_OPERATOR,
        is_active=True,
    )
    ProjectMembership.objects.create(
        project=project,
        user=foreign_owner,
        role=ProjectMembership.ROLE_OPERATOR,
        is_active=True,
    )
    server = _server(owner, project)
    ServerShare.objects.create(server=server, user=shared_staff, shared_by=owner, share_context=True)
    asset = _asset(server, owner)
    owner_playbook = _playbook(owner, project)

    with pytest.raises(MemoryPromotionError) as exc_info:
        promote_memory_asset(
            asset=asset,
            actor=shared_staff,
            destination_kind=ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION,
            playbook=owner_playbook,
        )
    assert exc_info.value.code == "promotion_forbidden"

    foreign_playbook = _playbook(foreign_owner, project, name="Foreign Target")
    with pytest.raises(MemoryPromotionError) as exc_info:
        promote_memory_asset(
            asset=asset,
            actor=owner,
            destination_kind=ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION,
            playbook=foreign_playbook,
        )
    assert exc_info.value.code == "playbook_forbidden"
    assert not ServerMemoryPromotion.objects.exists()


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_PROMOTION_ENABLED=True)
@pytest.mark.parametrize(
    ("title", "payload", "expected_code"),
    [
        ("Invalid payload", "not-json", "draft_payload_invalid"),
        (
            "Raw secret payload",
            {
                "content_format": PlaybookRevision.FORMAT_RUNBOOK_JSON,
                "tasks": [{"id": "bad", "command": "password=supersecret123"}],
            },
            "literal_secret_rejected",
        ),
        (
            "Raw secret reference",
            {
                "content_format": PlaybookRevision.FORMAT_RUNBOOK_JSON,
                "tasks": [{"id": "safe", "command": "echo ready"}],
                "secret_references": {"api_token": "raw-token-value"},
            },
            "secret_references_invalid",
        ),
    ],
)
def test_invalid_or_raw_secret_payload_is_rejected(title, payload, expected_code):
    owner = User.objects.create_user(username=f"promotion-invalid-{expected_code}", password="x", is_staff=True)
    project = _project(owner, f"Invalid {expected_code}")
    server = _server(owner, project)
    asset = _asset(server, owner, title=title, payload=payload)
    playbook = _playbook(owner, project)
    baseline_revision_count = playbook.content_revisions.count()

    with pytest.raises(MemoryPromotionError) as exc_info:
        promote_memory_asset(
            asset=asset,
            actor=owner,
            destination_kind=ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION,
            playbook=playbook,
        )

    assert exc_info.value.code == expected_code
    promotion = ServerMemoryPromotion.objects.get()
    assert promotion.status == ServerMemoryPromotion.STATUS_REJECTED
    assert promotion.validation_result["ok"] is False
    assert promotion.validation_result["code"] == expected_code
    assert promotion.validation_result["source"]["asset_id"] == asset.id
    assert promotion.validation_result["destination"]["playbook_id"] == playbook.id
    assert playbook.content_revisions.count() == baseline_revision_count


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_PROMOTION_ENABLED=True)
def test_snapshot_content_hash_mismatch_is_rejected_with_computed_provenance():
    owner = User.objects.create_user(username="promotion-integrity-owner", password="x", is_staff=True)
    project = _project(owner, "Promotion Integrity")
    server = _server(owner, project)
    asset = _asset(server, owner, title="Integrity source")
    ServerMemorySnapshot.objects.filter(pk=asset.current_snapshot_id).update(content_hash="f" * 64)
    asset.current_snapshot.refresh_from_db()
    playbook = _playbook(owner, project, name="Integrity Target")
    baseline_revision_count = playbook.content_revisions.count()

    with pytest.raises(MemoryPromotionError) as exc_info:
        promote_memory_asset(
            asset=asset,
            actor=owner,
            destination_kind=ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION,
            playbook=playbook,
        )

    assert exc_info.value.code == "source_integrity_mismatch"
    promotion = ServerMemoryPromotion.objects.get()
    assert promotion.status == ServerMemoryPromotion.STATUS_REJECTED
    assert promotion.validation_result["code"] == "source_integrity_mismatch"
    assert (
        promotion.validation_result["source"]["snapshot_content_hash"]
        == hashlib.sha256(asset.current_snapshot.content.encode("utf-8")).hexdigest()
    )
    assert playbook.content_revisions.count() == baseline_revision_count


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_PROMOTION_ENABLED=True)
def test_unsafe_destination_gateway_fails_closed_with_ledger_only():
    owner = User.objects.create_user(username="promotion-studio-owner", password="x", is_staff=True)
    project = _project(owner, "Studio Fail Closed")
    server = _server(owner, project)
    asset = _asset(server, owner)

    with pytest.raises(MemoryPromotionError) as exc_info:
        promote_memory_asset(
            asset=asset,
            actor=owner,
            destination_kind=ServerMemoryPromotion.DESTINATION_STUDIO_SKILL,
        )

    assert exc_info.value.code == "studio_draft_gateway_unavailable"
    promotion = ServerMemoryPromotion.objects.get()
    assert promotion.status == ServerMemoryPromotion.STATUS_FAILED
    assert promotion.skill_slug == ""
    assert promotion.playbook_revision_id is None
    assert promotion.validation_result["source"]["snapshot_id"] == asset.current_snapshot_id


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_PROMOTION_ENABLED=True)
def test_dirty_playbook_draft_is_preserved_and_promotion_fails_closed():
    owner = User.objects.create_user(username="promotion-dirty-owner", password="x", is_staff=True)
    project = _project(owner, "Dirty Draft Promotion")
    server = _server(owner, project)
    asset = _asset(server, owner, title="Dirty draft source")
    playbook = _playbook(owner, project, name="Dirty Draft Target")
    baseline_published_id = playbook.published_revision_id
    baseline_revision_count = playbook.content_revisions.count()
    draft = PlaybookDraft.objects.get(playbook=playbook)
    draft = update_draft(
        playbook,
        actor=owner,
        expected_version=draft.version,
        content_format=PlaybookRevision.FORMAT_RUNBOOK_JSON,
        tasks=[{"id": "human-edit", "command": "echo keep-this-edit"}],
    )
    dirty_hash = draft.content_hash
    dirty_version = draft.version

    with pytest.raises(MemoryPromotionError) as exc_info:
        promote_memory_asset(
            asset=asset,
            actor=owner,
            destination_kind=ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION,
            playbook=playbook,
        )

    assert exc_info.value.code == "playbook_draft_dirty"
    promotion = ServerMemoryPromotion.objects.get()
    assert promotion.status == ServerMemoryPromotion.STATUS_REJECTED
    assert promotion.validation_result["code"] == "playbook_draft_dirty"
    assert promotion.playbook_revision_id is None
    playbook.refresh_from_db()
    draft.refresh_from_db()
    assert playbook.published_revision_id == baseline_published_id
    assert playbook.content_revisions.count() == baseline_revision_count
    assert draft.content_hash == dirty_hash
    assert draft.version == dirty_version


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_PROMOTION_ENABLED=True)
def test_blocked_validation_keeps_revision_unpublished_and_marks_rejected(monkeypatch):
    _stable_runtime_fingerprint(monkeypatch)
    owner = User.objects.create_user(username="promotion-blocked-owner", password="x", is_staff=True)
    project = _project(owner, "Blocked Promotion")
    server = _server(owner, project)
    asset = _asset(server, owner, title="Blocked source")
    playbook = _playbook(owner, project, name="Blocked Target")
    baseline_published_id = playbook.published_revision_id

    class BlockedValidation:
        id = 4242
        status = "blocked"
        issues = [{"code": "target_not_ready"}]
        runtime_fingerprint_hash = "c" * 64
        target_signature = "d" * 64

    monkeypatch.setattr(
        "servers.services.memory_asset_promotion.validate_revision",
        lambda **_kwargs: BlockedValidation(),
    )

    promotion = promote_memory_asset(
        asset=asset,
        actor=owner,
        destination_kind=ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION,
        playbook=playbook,
    )

    playbook.refresh_from_db()
    assert promotion.status == ServerMemoryPromotion.STATUS_REJECTED
    assert promotion.validation_result["code"] == "validation_blocked"
    assert promotion.validation_result["validation"] == {
        "id": 4242,
        "status": "blocked",
        "issue_count": 1,
        "issue_codes": ["target_not_ready"],
        "runtime_fingerprint_hash": "c" * 64,
        "target_signature": "d" * 64,
    }
    assert promotion.playbook_revision_id is not None
    assert playbook.published_revision_id == baseline_published_id
    assert not PlaybookRun.objects.filter(playbook=playbook).exists()


@pytest.mark.django_db(transaction=True)
@override_settings(SERVER_MEMORY_PROMOTION_ENABLED=True)
def test_unexpected_validation_failure_rolls_back_draft_and_revision(monkeypatch):
    owner = User.objects.create_user(username="promotion-rollback-owner", password="x", is_staff=True)
    project = _project(owner, "Promotion Transaction Rollback")
    server = _server(owner, project)
    asset = _asset(server, owner, title="Rollback source")
    playbook = _playbook(owner, project, name="Rollback Target")
    baseline_published_id = playbook.published_revision_id
    baseline_revision_count = playbook.content_revisions.count()
    baseline_draft = PlaybookDraft.objects.get(playbook=playbook)
    baseline_draft_state = (
        baseline_draft.base_revision_id,
        baseline_draft.content_hash,
        baseline_draft.version,
    )

    def _validation_failure(**_kwargs):
        raise RuntimeError("simulated validator failure")

    monkeypatch.setattr(
        "servers.services.memory_asset_promotion.validate_revision",
        _validation_failure,
    )

    with pytest.raises(MemoryPromotionError) as exc_info:
        promote_memory_asset(
            asset=asset,
            actor=owner,
            destination_kind=ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION,
            playbook=playbook,
        )

    assert exc_info.value.code == "draft_or_validation_failed"
    promotion = ServerMemoryPromotion.objects.get()
    assert promotion.status == ServerMemoryPromotion.STATUS_FAILED
    assert promotion.playbook_revision_id is None
    playbook.refresh_from_db()
    baseline_draft.refresh_from_db()
    assert playbook.published_revision_id == baseline_published_id
    assert playbook.content_revisions.count() == baseline_revision_count
    assert (
        baseline_draft.base_revision_id,
        baseline_draft.content_hash,
        baseline_draft.version,
    ) == baseline_draft_state
