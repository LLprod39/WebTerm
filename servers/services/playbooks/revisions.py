"""Draft and immutable revision lifecycle with optimistic locking."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Max

from servers.models import Playbook, PlaybookDraft, PlaybookRevision, PlaybookValidation
from servers.services.playbooks.audit import record_playbook_event
from servers.services.playbooks.content import (
    calculate_content_hash,
    content_format_for,
    normalize_tasks,
    validate_content,
)


@dataclass(frozen=True)
class DraftConflict(Exception):
    current_version: int
    current_hash: str
    updated_at: str

    def __str__(self) -> str:
        return "Draft was changed by another editor"


def _legacy_content(playbook: Playbook) -> tuple[str, str, list[dict]]:
    source_yaml = playbook.source_yaml or ""
    content_format = content_format_for(kind=playbook.kind, source_yaml=source_yaml)
    return content_format, source_yaml, normalize_tasks(playbook.tasks)


@transaction.atomic
def ensure_playbook_workspace(
    playbook: Playbook,
    *,
    actor=None,
    origin_type: str | None = None,
) -> tuple[PlaybookRevision, PlaybookDraft]:
    locked = Playbook.objects.select_for_update().get(pk=playbook.pk)
    published_revision = locked.published_revision
    workspace_migrated = locked.origin_revision_id is None
    origin_revision = locked.origin_revision or locked.content_revisions.order_by("revision_number").first()
    if published_revision is None:
        published_revision = locked.content_revisions.order_by("-revision_number").first()
    if origin_revision is None:
        content_format, source_yaml, tasks = _legacy_content(locked)
        origin_revision = PlaybookRevision.objects.create(
            playbook=locked,
            revision_number=1,
            author=actor if getattr(actor, "is_authenticated", False) else locked.user,
            content_format=content_format,
            source_yaml=source_yaml,
            tasks=tasks,
            content_hash=calculate_content_hash(
                content_format=content_format,
                source_yaml=source_yaml,
                tasks=tasks,
            ),
            origin_type=origin_type
            or (
                PlaybookRevision.ORIGIN_TEMPLATE
                if locked.is_template_clone
                else PlaybookRevision.ORIGIN_IMPORTED
                if source_yaml
                else PlaybookRevision.ORIGIN_MANUAL
            ),
            message="Initial revision",
        )
        published_revision = origin_revision
        compatibility = locked.active_compatibility_revision
        source_hash = hashlib.sha256(source_yaml.strip().encode("utf-8")).hexdigest() if source_yaml else ""
        if (
            compatibility
            and compatibility.status == "validated"
            and compatibility.source_hash == source_hash
            and (compatibility.adapted_yaml or "").strip()
        ):
            published_revision = PlaybookRevision.objects.create(
                playbook=locked,
                revision_number=2,
                parent=origin_revision,
                author=compatibility.user,
                content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
                source_yaml=compatibility.adapted_yaml,
                tasks=tasks,
                content_hash=calculate_content_hash(
                    content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
                    source_yaml=compatibility.adapted_yaml,
                    tasks=tasks,
                ),
                origin_type=PlaybookRevision.ORIGIN_ADAPTATION,
                message="Validated compatibility adaptation",
                metadata={"legacy_compatibility_revision_id": compatibility.id},
            )
            type(compatibility).objects.filter(pk=compatibility.pk).update(
                source_revision_id=origin_revision.id,
                result_revision_id=published_revision.id,
            )
    update_fields: list[str] = []
    if locked.origin_revision_id is None:
        locked.origin_revision = origin_revision
        update_fields.append("origin_revision")
    if locked.published_revision_id is None:
        locked.published_revision = published_revision
        update_fields.append("published_revision")
    if update_fields:
        locked.save(update_fields=update_fields)

    draft, _created = PlaybookDraft.objects.get_or_create(
        playbook=locked,
        defaults={
            "base_revision": published_revision,
            "content_format": published_revision.content_format,
            "source_yaml": published_revision.source_yaml,
            "tasks": published_revision.tasks,
            "content_hash": published_revision.content_hash,
            "asset_bundle": published_revision.asset_bundle,
            "bundle_hash": published_revision.bundle_hash,
            "last_editor": actor if getattr(actor, "is_authenticated", False) else locked.user,
        },
    )
    playbook.origin_revision_id = locked.origin_revision_id
    playbook.published_revision_id = locked.published_revision_id
    if workspace_migrated:
        from servers.services.playbooks.sharing import sync_legacy_visibility_grant

        sync_legacy_visibility_grant(locked, actor=actor)
    return published_revision, draft


def initialize_created_playbook(
    playbook: Playbook,
    *,
    actor,
    origin_type: str,
) -> tuple[PlaybookRevision, PlaybookDraft]:
    revision, draft = ensure_playbook_workspace(playbook, actor=actor, origin_type=origin_type)
    from servers.services.playbooks.sharing import sync_legacy_visibility_grant

    sync_legacy_visibility_grant(playbook, actor=actor)
    record_playbook_event(
        playbook=playbook,
        actor=actor,
        event_type="playbook_created",
        metadata={"origin_type": origin_type, "origin_revision_id": revision.id},
    )
    return revision, draft


@transaction.atomic
def initialize_forked_playbook(
    playbook: Playbook,
    source_revision: PlaybookRevision,
    *,
    actor,
) -> tuple[PlaybookRevision, PlaybookDraft]:
    """Create an exact executable fork, including its verified project bundle."""

    if playbook.origin_revision_id or playbook.content_revisions.exists():
        raise ValueError("Fork workspace is already initialized")
    metadata = source_revision.metadata if isinstance(source_revision.metadata, dict) else {}
    safe_metadata = {
        key: metadata[key] for key in ("bundle_entrypoint", "required_collections", "required_roles") if key in metadata
    }
    safe_metadata["forked_from_revision_id"] = source_revision.id
    revision = PlaybookRevision.objects.create(
        playbook=playbook,
        revision_number=1,
        author=actor,
        content_format=source_revision.content_format,
        source_yaml=source_revision.source_yaml,
        tasks=source_revision.tasks,
        content_hash=source_revision.content_hash,
        asset_bundle=source_revision.asset_bundle,
        bundle_hash=source_revision.bundle_hash,
        origin_type=PlaybookRevision.ORIGIN_MANUAL,
        message=f"Forked from revision {source_revision.id}",
        metadata=safe_metadata,
    )
    Playbook.objects.filter(pk=playbook.pk).update(
        origin_revision_id=revision.id,
        published_revision_id=revision.id,
    )
    draft = PlaybookDraft.objects.create(
        playbook=playbook,
        base_revision=revision,
        content_format=revision.content_format,
        source_yaml=revision.source_yaml,
        tasks=revision.tasks,
        content_hash=revision.content_hash,
        asset_bundle=revision.asset_bundle,
        bundle_hash=revision.bundle_hash,
        last_editor=actor,
    )
    from servers.services.playbooks.sharing import sync_legacy_visibility_grant

    sync_legacy_visibility_grant(playbook, actor=actor)
    record_playbook_event(
        playbook=playbook,
        actor=actor,
        event_type="playbook_forked",
        entity_type="revision",
        entity_id=revision.id,
        metadata={"source_revision_id": source_revision.id, "bundle_hash": source_revision.bundle_hash},
    )
    playbook.refresh_from_db(fields=["origin_revision", "published_revision"])
    return revision, draft


def sync_legacy_content_save(playbook: Playbook, *, actor, message: str = "Legacy editor save") -> PlaybookRevision:
    """Dual-write an explicit legacy save into draft and immutable history."""
    current, draft = ensure_playbook_workspace(playbook, actor=actor)
    content_format, source_yaml, tasks = _legacy_content(playbook)
    next_hash = calculate_content_hash(
        content_format=content_format,
        source_yaml=source_yaml,
        tasks=tasks,
        bundle_hash=draft.bundle_hash,
    )
    if draft.content_hash != next_hash:
        draft = update_draft(
            playbook,
            actor=actor,
            expected_version=draft.version,
            content_format=content_format,
            source_yaml=source_yaml,
            tasks=tasks,
        )
    published = Playbook.objects.get(pk=playbook.pk).published_revision
    if published and published.content_hash == next_hash:
        return published
    revision = create_revision_from_draft(
        playbook,
        actor=actor,
        expected_version=draft.version,
        message=message,
    )
    publish_revision(playbook, revision, actor=actor)
    return revision


@transaction.atomic
def create_compatibility_adaptation_revision(playbook: Playbook, compatibility, *, actor) -> PlaybookRevision:
    """Freeze an accepted proposal in draft/history without publishing it."""
    source_revision, draft = ensure_playbook_workspace(playbook, actor=actor)
    adapted_yaml = compatibility.adapted_yaml or ""
    draft = update_draft(
        playbook,
        actor=actor,
        expected_version=draft.version,
        content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
        source_yaml=adapted_yaml,
        tasks=draft.tasks,
    )
    result = create_revision_from_draft(
        playbook,
        actor=actor,
        expected_version=draft.version,
        message="Apply validated compatibility adaptation",
        origin_type=PlaybookRevision.ORIGIN_ADAPTATION,
    )
    type(compatibility).objects.filter(pk=compatibility.pk).update(
        source_revision_id=source_revision.id,
        result_revision_id=result.id,
    )
    return result


@transaction.atomic
def update_draft(
    playbook: Playbook,
    *,
    actor,
    expected_version: int,
    source_yaml: str | None = None,
    tasks=None,
    content_format: str | None = None,
) -> PlaybookDraft:
    ensure_playbook_workspace(playbook, actor=actor)
    draft = PlaybookDraft.objects.select_for_update().select_related("playbook").get(playbook=playbook)
    if int(expected_version) != draft.version:
        record_playbook_event(
            playbook=playbook,
            actor=actor,
            event_type="draft_conflict",
            entity_type="draft",
            entity_id=draft.id,
            metadata={"expected_version": expected_version, "current_version": draft.version},
        )
        raise DraftConflict(draft.version, draft.content_hash, draft.updated_at.isoformat())

    next_format = content_format or draft.content_format
    next_source = draft.source_yaml if source_yaml is None else source_yaml
    next_tasks = draft.tasks if tasks is None else tasks
    next_source, next_tasks = validate_content(
        content_format=next_format,
        source_yaml=next_source,
        tasks=next_tasks,
    )
    next_hash = calculate_content_hash(
        content_format=next_format,
        source_yaml=next_source,
        tasks=next_tasks,
        bundle_hash=draft.bundle_hash,
    )
    if next_hash != draft.content_hash:
        draft.content_format = next_format
        draft.source_yaml = next_source
        draft.tasks = next_tasks
        draft.content_hash = next_hash
        draft.version += 1
        draft.last_editor = actor
        draft.save(
            update_fields=[
                "content_format",
                "source_yaml",
                "tasks",
                "content_hash",
                "version",
                "last_editor",
                "updated_at",
            ]
        )
    record_playbook_event(
        playbook=playbook,
        actor=actor,
        event_type="draft_saved",
        entity_type="draft",
        entity_id=draft.id,
        metadata={"version": draft.version, "content_hash": draft.content_hash},
    )
    return draft


@transaction.atomic
def create_revision_from_draft(
    playbook: Playbook,
    *,
    actor,
    expected_version: int | None = None,
    message: str = "",
    origin_type: str = PlaybookRevision.ORIGIN_MANUAL,
) -> PlaybookRevision:
    ensure_playbook_workspace(playbook, actor=actor)
    locked = Playbook.objects.select_for_update().get(pk=playbook.pk)
    draft = PlaybookDraft.objects.select_for_update().get(playbook=locked)
    if expected_version is not None and int(expected_version) != draft.version:
        raise DraftConflict(draft.version, draft.content_hash, draft.updated_at.isoformat())

    next_number = (locked.content_revisions.aggregate(value=Max("revision_number"))["value"] or 0) + 1
    revision = PlaybookRevision.objects.create(
        playbook=locked,
        revision_number=next_number,
        parent=draft.base_revision,
        author=actor,
        content_format=draft.content_format,
        source_yaml=draft.source_yaml,
        tasks=draft.tasks,
        content_hash=draft.content_hash,
        asset_bundle=draft.asset_bundle,
        bundle_hash=draft.bundle_hash,
        origin_type=origin_type,
        message=(message or "")[:500],
    )
    draft.base_revision = revision
    draft.save(update_fields=["base_revision", "updated_at"])
    record_playbook_event(
        playbook=locked,
        actor=actor,
        event_type="revision_created",
        entity_type="revision",
        entity_id=revision.id,
        metadata={"revision_number": revision.revision_number, "content_hash": revision.content_hash},
    )
    return revision


@transaction.atomic
def publish_revision(playbook: Playbook, revision: PlaybookRevision, *, actor) -> Playbook:
    locked = Playbook.objects.select_for_update().get(pk=playbook.pk)
    if revision.playbook_id != locked.id:
        raise ValueError("Revision does not belong to this playbook")
    if revision.origin_type == PlaybookRevision.ORIGIN_ADAPTATION:
        actor_id = getattr(actor, "id", None)
        ready_validations = revision.validations.filter(status=PlaybookValidation.STATUS_READY)
        if actor_id != locked.user_id:
            ready_validations = ready_validations.filter(requested_by_id=actor_id)
        if actor_id is None or not ready_validations.exists():
            raise ValueError("Compatibility adaptation must pass standard revision validation before publishing")
    locked.published_revision = revision
    # Dual-write legacy fields until every consumer reads immutable revisions.
    locked.source_yaml = revision.source_yaml
    locked.tasks = revision.tasks
    locked.kind = Playbook.KIND_ANSIBLE if revision.content_format == "ansible_yaml" else Playbook.KIND_RUNBOOK
    locked.save(update_fields=["published_revision", "source_yaml", "tasks", "kind", "updated_at"])
    record_playbook_event(
        playbook=locked,
        actor=actor,
        event_type="revision_published",
        entity_type="revision",
        entity_id=revision.id,
        metadata={"revision_number": revision.revision_number, "content_hash": revision.content_hash},
    )
    return locked


@transaction.atomic
def rollback_to_revision(
    playbook: Playbook, revision: PlaybookRevision, *, actor, message: str = ""
) -> PlaybookRevision:
    if revision.playbook_id != playbook.id:
        raise ValueError("Revision does not belong to this playbook")
    _current, draft = ensure_playbook_workspace(playbook, actor=actor)
    draft = PlaybookDraft.objects.select_for_update().get(pk=draft.pk)
    draft.base_revision = revision
    draft.content_format = revision.content_format
    draft.source_yaml = revision.source_yaml
    draft.tasks = revision.tasks
    draft.content_hash = revision.content_hash
    draft.asset_bundle = revision.asset_bundle
    draft.bundle_hash = revision.bundle_hash
    draft.version += 1
    draft.last_editor = actor
    draft.save()
    rollback_revision = create_revision_from_draft(
        playbook,
        actor=actor,
        expected_version=draft.version,
        message=message or f"Rollback to revision {revision.revision_number}",
        origin_type=PlaybookRevision.ORIGIN_ROLLBACK,
    )
    publish_revision(playbook, rollback_revision, actor=actor)
    record_playbook_event(
        playbook=playbook,
        actor=actor,
        event_type="revision_rolled_back",
        entity_type="revision",
        entity_id=rollback_revision.id,
        metadata={"restored_revision_id": revision.id},
    )
    return rollback_revision
