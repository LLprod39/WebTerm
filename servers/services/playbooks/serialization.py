"""Viewer-aware playbook workspace serialization."""

from __future__ import annotations

from servers.services.playbooks.access import capabilities_for
from servers.services.playbooks.compatibility import compatibility_for_revision


def serialize_revision(revision, *, include_content: bool = False) -> dict:
    payload = {
        "id": revision.id,
        "revision_number": revision.revision_number,
        "parent_id": revision.parent_id,
        "content_format": revision.content_format,
        "content_hash": revision.content_hash,
        "bundle_hash": revision.bundle_hash,
        "origin_type": revision.origin_type,
        "message": revision.message,
        "author_id": revision.author_id,
        "author_username": revision.author.get_username() if revision.author_id and revision.author else "",
        "created_at": revision.created_at.isoformat(),
        "compatibility": compatibility_for_revision(revision),
    }
    if include_content:
        payload["source_yaml"] = revision.source_yaml
        payload["tasks"] = revision.tasks if isinstance(revision.tasks, list) else []
    return payload


def serialize_draft(draft) -> dict:
    return {
        "id": draft.id,
        "base_revision_id": draft.base_revision_id,
        "content_format": draft.content_format,
        "source_yaml": draft.source_yaml,
        "tasks": draft.tasks if isinstance(draft.tasks, list) else [],
        "content_hash": draft.content_hash,
        "bundle_hash": draft.bundle_hash,
        "version": draft.version,
        "last_editor_id": draft.last_editor_id,
        "updated_at": draft.updated_at.isoformat(),
    }


def serialize_workspace_playbook(playbook, *, viewer, include_published_content: bool = False) -> dict:
    capabilities = capabilities_for(playbook, viewer)
    published = playbook.published_revision
    return {
        "id": playbook.id,
        "name": playbook.name,
        "description": playbook.description,
        "kind": playbook.kind,
        "category": playbook.category,
        "tags": playbook.tags if isinstance(playbook.tags, list) else [],
        "visibility": playbook.visibility,
        "owner_id": playbook.user_id,
        "is_archived": playbook.is_archived,
        "origin_revision_id": playbook.origin_revision_id,
        "published_revision": (
            serialize_revision(published, include_content=include_published_content) if published else None
        ),
        "capabilities": capabilities.to_dict(),
        "created_at": playbook.created_at.isoformat(),
        "updated_at": playbook.updated_at.isoformat(),
    }
