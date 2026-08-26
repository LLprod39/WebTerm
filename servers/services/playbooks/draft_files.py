"""Editable project-file views over immutable bundle snapshots."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from django.db import transaction

from servers.models import PlaybookAssetBundle, PlaybookDraft, PlaybookRevision
from servers.services.playbook_parser import parse_ansible_playbook
from servers.services.playbooks.audit import record_playbook_event
from servers.services.playbooks.bundle_archive import (
    TEXT_EXTENSIONS,
    BundleLimits,
    BundleValidationError,
    InspectedBundle,
    build_canonical_zip,
    calculate_bundle_content_hash,
    inspect_project_bundle,
    normalize_bundle_path,
)
from servers.services.playbooks.bundle_content import blocking_secret_findings
from servers.services.playbooks.bundle_storage import BundleStorageError, get_playbook_bundle_storage
from servers.services.playbooks.content import calculate_content_hash
from servers.services.playbooks.controller_policy import analyze_project_files_controller_policy
from servers.services.playbooks.revisions import DraftConflict, ensure_playbook_workspace
from servers.services.playbooks.source_guard import PlaybookSourceSafetyError, validate_ansible_source

_EDITABLE_ROLE_SECTIONS = frozenset({"defaults", "handlers", "tasks", "vars"})


@dataclass(frozen=True)
class DraftFileSnapshot:
    path: str
    content: str
    size_bytes: int
    sha256: str
    is_entrypoint: bool
    draft_version: int | None


def draft_file_tree(draft: PlaybookDraft) -> dict[str, Any]:
    inspected, files, entrypoint = _load_draft_files(draft)
    rows = []
    for path, content in sorted(files.items()):
        suffix = PurePosixPath(path).suffix.casefold()
        is_text = suffix in TEXT_EXTENSIONS
        rows.append(
            {
                "path": path,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "is_text": is_text,
                "editable": _is_editable_yaml_path(path),
                "is_entrypoint": path == entrypoint,
            }
        )
    return {
        "entrypoint": entrypoint,
        "bundle_hash": draft.bundle_hash or (inspected.content_hash if inspected else calculate_bundle_content_hash(files)),
        "draft_version": draft.version,
        "files": rows,
    }


def revision_file_tree(revision: PlaybookRevision) -> dict[str, Any]:
    """Describe immutable published/base files without exposing a mutable draft."""

    files, entrypoint = _load_revision_files(revision)
    rows = []
    for path, content in sorted(files.items()):
        suffix = PurePosixPath(path).suffix.casefold()
        rows.append(
            {
                "path": path,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "is_text": suffix in TEXT_EXTENSIONS,
                "editable": False,
                "is_entrypoint": path == entrypoint,
            }
        )
    return {
        "entrypoint": entrypoint,
        "bundle_hash": revision.bundle_hash or calculate_bundle_content_hash(files),
        "draft_version": None,
        "files": rows,
    }


def get_draft_text_file(draft: PlaybookDraft, *, path: str = "") -> DraftFileSnapshot:
    _inspected, files, entrypoint = _load_draft_files(draft)
    selected = normalize_bundle_path(path) if path else entrypoint
    if selected not in files:
        raise BundleValidationError("Draft file was not found", code="draft_file_not_found", status_code=404)
    if PurePosixPath(selected).suffix.casefold() not in TEXT_EXTENSIONS:
        raise BundleValidationError("Draft file is binary and cannot be opened", code="draft_file_binary", status_code=415)
    try:
        content = files[selected].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BundleValidationError(
            "Draft text file is not valid UTF-8", code="invalid_text_encoding", status_code=422
        ) from exc
    encoded = content.encode("utf-8")
    return DraftFileSnapshot(
        path=selected,
        content=content,
        size_bytes=len(encoded),
        sha256=hashlib.sha256(encoded).hexdigest(),
        is_entrypoint=selected == entrypoint,
        draft_version=draft.version,
    )


def get_base_text_file(draft: PlaybookDraft, *, path: str = "") -> DraftFileSnapshot:
    """Read a file from the immutable revision the draft was based on."""

    files, entrypoint = _load_base_revision_files(draft)
    selected = normalize_bundle_path(path) if path else entrypoint
    if selected not in files:
        raise BundleValidationError("Base file was not found", code="draft_base_file_not_found", status_code=404)
    if PurePosixPath(selected).suffix.casefold() not in TEXT_EXTENSIONS:
        raise BundleValidationError("Base file is binary and cannot be opened", code="draft_file_binary", status_code=415)
    try:
        content = files[selected].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BundleValidationError(
            "Base text file is not valid UTF-8", code="invalid_text_encoding", status_code=422
        ) from exc
    encoded = content.encode("utf-8")
    return DraftFileSnapshot(
        path=selected,
        content=content,
        size_bytes=len(encoded),
        sha256=hashlib.sha256(encoded).hexdigest(),
        is_entrypoint=selected == entrypoint,
        draft_version=draft.version,
    )


def get_revision_text_file(revision: PlaybookRevision, *, path: str = "") -> DraftFileSnapshot:
    files, entrypoint = _load_revision_files(revision)
    selected = normalize_bundle_path(path) if path else entrypoint
    if selected not in files:
        raise BundleValidationError("Published file was not found", code="published_file_not_found", status_code=404)
    if PurePosixPath(selected).suffix.casefold() not in TEXT_EXTENSIONS:
        raise BundleValidationError("Published file is binary and cannot be opened", code="draft_file_binary", status_code=415)
    try:
        content = files[selected].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BundleValidationError(
            "Published text file is not valid UTF-8", code="invalid_text_encoding", status_code=422
        ) from exc
    encoded = content.encode("utf-8")
    return DraftFileSnapshot(
        path=selected,
        content=content,
        size_bytes=len(encoded),
        sha256=hashlib.sha256(encoded).hexdigest(),
        is_entrypoint=selected == entrypoint,
        draft_version=None,
    )


def update_draft_text_file(
    playbook,
    *,
    actor,
    path: str,
    content: Any,
    expected_draft_version: int,
    expected_bundle_hash: str,
) -> tuple[PlaybookDraft, DraftFileSnapshot, dict[str, Any]]:
    """Create a new bundle asset and move only the mutable draft to it."""

    selected = normalize_bundle_path(path)
    if not isinstance(content, str):
        raise BundleValidationError("Draft file content must be a string", code="draft_file_content_invalid")
    encoded = content.encode("utf-8")
    limits = BundleLimits.from_settings()
    if len(encoded) > limits.max_file_bytes:
        raise BundleValidationError(
            "Draft file exceeds the per-file size limit", code="file_size_limit", status_code=413
        )

    storage = get_playbook_bundle_storage()
    storage_key = ""
    try:
        with transaction.atomic():
            ensure_playbook_workspace(playbook, actor=actor)
            draft = (
                PlaybookDraft.objects.select_for_update()
                .select_related("asset_bundle", "base_revision", "playbook")
                .get(playbook=playbook)
            )
            if int(expected_draft_version) != draft.version:
                raise DraftConflict(draft.version, draft.content_hash, draft.updated_at.isoformat())
            _current, files, entrypoint = _load_draft_files(draft)
            current_bundle_hash = draft.bundle_hash or calculate_bundle_content_hash(files)
            if str(expected_bundle_hash or "") != current_bundle_hash:
                raise BundleValidationError(
                    "The draft bundle changed after it was opened",
                    code="playbook_draft_conflict",
                    status_code=409,
                    details={
                        "current_version": draft.version,
                        "current_hash": draft.content_hash,
                        "current_bundle_hash": current_bundle_hash,
                        "updated_at": draft.updated_at.isoformat(),
                    },
                )
            if selected not in files:
                raise BundleValidationError("Draft file was not found", code="draft_file_not_found", status_code=404)
            if not _is_editable_yaml_path(selected):
                raise BundleValidationError(
                    "This project file is read-only", code="draft_file_read_only", status_code=422
                )
            files[selected] = encoded
            canonical = build_canonical_zip(files)
            inspected = inspect_project_bundle(canonical, limits=limits)
            blocking_findings = blocking_secret_findings(inspected.secret_findings)
            if blocking_findings:
                raise BundleValidationError(
                    "Draft project contains secret material; use managed secret bindings",
                    code="secret_material_detected",
                    status_code=422,
                    details={"findings": blocking_findings[:20]},
                )
            try:
                entrypoint_source = files[entrypoint].decode("utf-8")
            except (KeyError, UnicodeDecodeError) as exc:
                raise BundleValidationError(
                    "Draft bundle entrypoint is not valid UTF-8", code="invalid_entrypoint", status_code=422
                ) from exc
            try:
                entrypoint_safety = validate_ansible_source(entrypoint_source, path=entrypoint)
            except PlaybookSourceSafetyError as exc:
                raise BundleValidationError(
                    str(exc), code=exc.code, status_code=exc.status_code, details=exc.details
                ) from exc
            controller_findings = analyze_project_files_controller_policy(
                {item.path: item.content for item in inspected.files},
                skip_paths={entrypoint},
            )
            if controller_findings:
                raise BundleValidationError(
                    "Draft project contains controller-side operations that are not allowed",
                    code="controller_policy_violation",
                    status_code=422,
                    details={"issues": controller_findings[:20]},
                )

            next_source = draft.source_yaml
            next_tasks = draft.tasks if isinstance(draft.tasks, list) else []
            if selected == entrypoint:
                try:
                    parsed = parse_ansible_playbook(content, entrypoint)
                except ValueError as exc:
                    raise BundleValidationError(
                        "Entrypoint is not a supported Ansible playbook", code="invalid_entrypoint"
                    ) from exc
                next_source = entrypoint_safety.source_yaml
                next_tasks = parsed.get("tasks") or []

            storage_key = storage.save(canonical, content_hash=inspected.content_hash)
            asset = PlaybookAssetBundle.objects.create(
                storage_key=storage_key,
                manifest=[item.manifest_item() for item in inspected.files],
                content_hash=inspected.content_hash,
                size_bytes=inspected.total_size,
                file_count=len(inspected.files),
                scan_status=PlaybookAssetBundle.SCAN_CLEAN,
                scan_report={
                    "archive_format": "zip",
                    "entrypoint": entrypoint,
                    "manifest": inspected.manifest,
                    "parent_bundle_hash": draft.bundle_hash,
                    "checks": {
                        "paths": "clean",
                        "links": "clean",
                        "limits": "clean",
                        "secrets": "clean",
                        "controller_policy": "clean",
                    },
                },
                created_by=actor,
            )
            draft.source_yaml = next_source
            draft.tasks = next_tasks
            draft.content_format = PlaybookRevision.FORMAT_ANSIBLE_YAML
            draft.asset_bundle = asset
            draft.bundle_hash = inspected.content_hash
            draft.content_hash = calculate_content_hash(
                content_format=draft.content_format,
                source_yaml=next_source,
                tasks=next_tasks,
                bundle_hash=inspected.content_hash,
            )
            draft.version += 1
            draft.last_editor = actor
            draft.save()
            record_playbook_event(
                playbook=playbook,
                actor=actor,
                event_type="draft_file_saved",
                entity_type="draft",
                entity_id=draft.id,
                metadata={
                    "path": selected,
                    "version": draft.version,
                    "bundle_hash": inspected.content_hash,
                },
            )
    except Exception:
        if storage_key:
            storage.delete(storage_key)
        raise

    snapshot = get_draft_text_file(draft, path=selected)
    return draft, snapshot, draft_file_tree(draft)


def _load_draft_files(draft: PlaybookDraft) -> tuple[InspectedBundle | None, dict[str, bytes], str]:
    entrypoint = _entrypoint_for_draft(draft)
    if not draft.asset_bundle_id:
        if draft.content_format != PlaybookRevision.FORMAT_ANSIBLE_YAML:
            raise BundleValidationError(
                "Project files are available only for Ansible drafts",
                code="draft_files_unsupported",
                status_code=422,
            )
        return None, {entrypoint: (draft.source_yaml or "").encode("utf-8")}, entrypoint

    asset = draft.asset_bundle
    if asset is None or asset.scan_status != PlaybookAssetBundle.SCAN_CLEAN:
        raise BundleValidationError("Draft bundle is not approved", code="bundle_not_clean", status_code=409)
    limits = BundleLimits.from_settings()
    stored_limit = max(limits.max_archive_bytes, limits.max_total_bytes + limits.max_files * 1024)
    archive = get_playbook_bundle_storage().read(asset.storage_key, max_bytes=stored_limit)
    inspected = inspect_project_bundle(archive, limits=limits)
    if inspected.content_hash != asset.content_hash or (draft.bundle_hash and inspected.content_hash != draft.bundle_hash):
        raise BundleStorageError("Stored playbook bundle failed its integrity check")
    files = {item.path: item.content for item in inspected.files}
    if entrypoint not in files:
        raise BundleValidationError("Draft bundle entrypoint is missing", code="invalid_entrypoint", status_code=409)
    # The draft source is the current clone-on-write overlay until a new asset
    # is produced; immutable revisions and the original asset remain untouched.
    files[entrypoint] = (draft.source_yaml or "").encode("utf-8")
    return inspected, files, entrypoint


def _load_base_revision_files(draft: PlaybookDraft) -> tuple[dict[str, bytes], str]:
    revision = draft.base_revision
    if revision is None or revision.content_format != PlaybookRevision.FORMAT_ANSIBLE_YAML:
        raise BundleValidationError(
            "Draft has no immutable Ansible base revision",
            code="draft_base_unavailable",
            status_code=409,
        )
    return _load_revision_files(revision)


def _load_revision_files(revision: PlaybookRevision) -> tuple[dict[str, bytes], str]:
    if revision.content_format != PlaybookRevision.FORMAT_ANSIBLE_YAML:
        raise BundleValidationError(
            "Project files are available only for Ansible revisions",
            code="published_files_unsupported",
            status_code=422,
        )
    metadata = revision.metadata if isinstance(revision.metadata, dict) else {}
    candidate = metadata.get("bundle_entrypoint")
    entrypoint = normalize_bundle_path(candidate) if isinstance(candidate, str) and candidate else "playbook.yml"
    if not revision.asset_bundle_id:
        return {entrypoint: (revision.source_yaml or "").encode("utf-8")}, entrypoint

    asset = revision.asset_bundle
    if asset is None or asset.scan_status != PlaybookAssetBundle.SCAN_CLEAN:
        raise BundleValidationError("Base bundle is not approved", code="bundle_not_clean", status_code=409)
    limits = BundleLimits.from_settings()
    stored_limit = max(limits.max_archive_bytes, limits.max_total_bytes + limits.max_files * 1024)
    archive = get_playbook_bundle_storage().read(asset.storage_key, max_bytes=stored_limit)
    inspected = inspect_project_bundle(archive, limits=limits)
    if inspected.content_hash != asset.content_hash or (
        revision.bundle_hash and inspected.content_hash != revision.bundle_hash
    ):
        raise BundleStorageError("Stored base playbook bundle failed its integrity check")
    files = {item.path: item.content for item in inspected.files}
    if entrypoint not in files:
        raise BundleValidationError("Base bundle entrypoint is missing", code="invalid_entrypoint", status_code=409)
    return files, entrypoint


def _entrypoint_for_draft(draft: PlaybookDraft) -> str:
    if draft.asset_bundle_id and draft.asset_bundle:
        report = draft.asset_bundle.scan_report if isinstance(draft.asset_bundle.scan_report, dict) else {}
        candidate = report.get("entrypoint")
        if isinstance(candidate, str) and candidate:
            return normalize_bundle_path(candidate)
    if draft.base_revision_id and draft.base_revision:
        metadata = draft.base_revision.metadata if isinstance(draft.base_revision.metadata, dict) else {}
        candidate = metadata.get("bundle_entrypoint")
        if isinstance(candidate, str) and candidate:
            return normalize_bundle_path(candidate)
    return "playbook.yml"


def _is_editable_yaml_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if not parts or PurePosixPath(path).suffix.casefold() not in {".yml", ".yaml"}:
        return False
    if len(parts) == 1:
        return parts[0].casefold() not in {"requirements.yml", "requirements.yaml"}
    if parts[0] == "playbooks":
        return True
    return len(parts) >= 4 and parts[0] == "roles" and parts[2] in _EDITABLE_ROLE_SECTIONS


def is_editable_draft_yaml_path(path: str) -> bool:
    """Public path-policy predicate shared by editor and compatibility APIs."""

    try:
        normalized = normalize_bundle_path(path)
    except BundleValidationError:
        return False
    return _is_editable_yaml_path(normalized)
