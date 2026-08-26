"""Serialization + input-normalization helpers for playbook views.

Extracted from server_playbooks.py to keep modules under the size limit.
"""

from __future__ import annotations

from typing import Any

from app.egress_redaction import redact_egress_payload
from servers.models_playbooks import Playbook, PlaybookRun
from servers.services.playbook_compatibility_analysis import (
    COMPATIBILITY_ANALYZER_VERSION,
    analyze_playbook_compatibility,
)
from servers.services.playbook_runner import normalize_tasks
from servers.services.playbooks.access import capabilities_for, playbooks_visible_to


def _playbooks_for_user(user):
    return playbooks_visible_to(user)


def _playbook_compatibility(pb: Playbook) -> dict[str, Any]:
    compatibility = pb.compatibility if isinstance(pb.compatibility, dict) else {}
    if compatibility.get("analyzer_version") != COMPATIBILITY_ANALYZER_VERSION and (pb.source_yaml or "").strip():
        return analyze_playbook_compatibility(pb.source_yaml)
    return compatibility


def _active_compatibility_payload(revision, *, is_owner: bool) -> dict[str, Any] | None:
    if revision is None:
        return None
    revision_report = revision.report if revision and isinstance(revision.report, dict) else {}
    if revision_report.get("analyzer_version") != COMPATIBILITY_ANALYZER_VERSION:
        revision_report = analyze_playbook_compatibility(
            revision.adapted_yaml,
            bindings=revision.inventory_bindings if isinstance(revision.inventory_bindings, dict) else {},
        )
    return {
        "id": revision.id,
        "status": revision.status,
        "report": revision_report,
        "semantic_guard": revision.semantic_guard if isinstance(revision.semantic_guard, dict) else {},
        "change_summary": revision.change_summary if isinstance(revision.change_summary, list) else [],
        "inventory_bindings": (
            revision.inventory_bindings if is_owner and isinstance(revision.inventory_bindings, dict) else {}
        ),
        "created_at": revision.created_at.isoformat(),
    }


def _published_source_metadata(published) -> dict[str, str]:
    metadata = published.metadata if published and isinstance(published.metadata, dict) else {}
    source = metadata.get("source") if isinstance(metadata.get("source"), dict) else {}
    allowed = {"type", "host", "project", "ref", "path", "commit_sha"}
    return {key: str(value) for key, value in source.items() if key in allowed and isinstance(value, str)}


def _has_unpublished_draft(draft, published) -> bool:
    return bool(
        draft
        and (
            published is None
            or draft.content_hash != published.content_hash
            or (draft.bundle_hash or "") != (published.bundle_hash or "")
        )
    )


def _serialized_playbook_content(pb: Playbook, published, revision, *, is_owner: bool) -> dict[str, Any]:
    tasks = published.tasks if published and isinstance(published.tasks, list) else pb.tasks
    return {
        "tasks": tasks if isinstance(tasks, list) else [],
        "source_yaml": published.source_yaml if published else pb.source_yaml or "",
        "adapted_source_yaml": revision.adapted_yaml if revision and is_owner else "",
    }


def _serialize_playbook(pb: Playbook, *, include_tasks: bool = True, viewer=None) -> dict[str, Any]:
    capabilities = capabilities_for(pb, viewer or pb.user)
    revision = pb.active_compatibility_revision
    published = pb.published_revision
    draft = getattr(pb, "draft", None)
    data: dict[str, Any] = {
        "id": pb.id,
        "name": pb.name,
        "description": pb.description,
        "kind": pb.kind,
        "category": pb.category,
        "visibility": pb.visibility,
        "tags": pb.tags if isinstance(pb.tags, list) else [],
        "fidelity": pb.fidelity if isinstance(pb.fidelity, dict) else {},
        "compatibility": _playbook_compatibility(pb),
        "active_compatibility_revision": _active_compatibility_payload(
            revision,
            is_owner=capabilities.is_owner,
        ),
        "task_count": (len(published.tasks) if published and isinstance(published.tasks, list) else pb.task_count),
        "is_template_clone": pb.is_template_clone,
        "template_slug": pb.template_slug,
        "last_run_at": pb.last_run_at.isoformat() if pb.last_run_at else None,
        "last_run_status": pb.last_run_status or "",
        "created_at": pb.created_at.isoformat() if pb.created_at else None,
        "updated_at": pb.updated_at.isoformat() if pb.updated_at else None,
        "owner_id": pb.user_id,
        "origin_revision_id": pb.origin_revision_id,
        "published_revision_id": pb.published_revision_id,
        "published_revision_number": published.revision_number if published else None,
        "published_content_hash": published.content_hash if published else "",
        "draft_version": draft.version if draft else None,
        "has_unpublished_draft": _has_unpublished_draft(draft, published),
        "source": _published_source_metadata(published),
        "capabilities": capabilities.to_dict(),
    }
    if include_tasks:
        data.update(
            _serialized_playbook_content(
                pb,
                published,
                revision,
                is_owner=capabilities.is_owner,
            )
        )
    return data


def _serialize_run(run: PlaybookRun, *, include_hosts: bool = True) -> dict[str, Any]:
    snapshot = run.playbook_snapshot if isinstance(run.playbook_snapshot, dict) else {}
    data: dict[str, Any] = {
        "id": run.id,
        "playbook_id": run.playbook_id,
        "revision_id": run.revision_id,
        "validation_id": run.validation_id,
        "binding_profile_id": run.binding_profile_id,
        "status": run.status,
        "playbook_name": snapshot.get("name") or (run.playbook.name if run.playbook_id else "Playbook"),
        "target_server_ids": run.target_server_ids or [],
        "target_group_ids": run.target_group_ids or [],
        "options": run.options if isinstance(run.options, dict) else {},
        "variable_manifest": run.variable_manifest if isinstance(run.variable_manifest, dict) else {},
        "execution_fingerprint": (run.execution_fingerprint if isinstance(run.execution_fingerprint, dict) else {}),
        "summary": run.summary if isinstance(run.summary, dict) else {},
        "progress": run.progress if isinstance(run.progress, dict) else {},
        "inventory_preview": run.inventory_preview or "",
        "error_message": run.error_message or "",
        "cancel_requested": bool(run.cancel_requested),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
    if include_hosts:
        data["host_results"] = run.host_results if isinstance(run.host_results, list) else []
        visible_snapshot = dict(snapshot)
        if run.playbook_id and run.user_id != run.playbook.user_id:
            visible_snapshot.pop("source_yaml_original", None)
        data["playbook_snapshot"] = visible_snapshot
        data["live_log"] = (run.live_log or "")[-120_000:]
    # Older rows may predate storage-time redaction.  Keep the legacy response
    # contract, but apply the same egress policy to the complete payload before
    # any caller can serialize or incrementally reconstruct a secret.
    redacted, _report, _hashes = redact_egress_payload(data)
    if not isinstance(redacted, dict):
        return {}
    # Names are identifiers, not secret values.  Preserve the documented
    # manifest contract while never returning the corresponding values.
    manifest = run.variable_manifest if isinstance(run.variable_manifest, dict) else {}
    redacted["variable_manifest"] = {
        "names": [str(item) for item in manifest.get("names", [])[:100]]
        if isinstance(manifest.get("names"), list)
        else [],
        "managed_secret_names": [str(item) for item in manifest.get("managed_secret_names", [])[:100]]
        if isinstance(manifest.get("managed_secret_names"), list)
        else [],
        "values_redacted": True,
    }
    return redacted


def _normalize_incoming_tasks(raw: Any) -> list[dict[str, Any]]:
    tasks = normalize_tasks(raw)
    # re-map keys for storage with snake_case
    return [
        {
            "id": t["id"],
            "command": t["command"],
            "description": t.get("description") or "",
            "continue_on_error": bool(t.get("continue_on_error")),
        }
        for t in tasks
        if not t.get("skipped_module") or t.get("command")
    ]
