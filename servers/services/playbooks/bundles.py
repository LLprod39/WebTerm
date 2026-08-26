"""Project bundle preview, transactional import and sanitized export."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils.text import slugify

from servers.models import Playbook, PlaybookAssetBundle, PlaybookDraft, PlaybookRevision
from servers.services.playbook_compatibility_analysis import analyze_playbook_compatibility
from servers.services.playbook_parser import parse_ansible_playbook
from servers.services.playbooks.audit import record_playbook_event
from servers.services.playbooks.bundle_archive import (
    CHECKSUMS_NAME,
    MANIFEST_KIND,
    MANIFEST_NAME,
    MANIFEST_SCHEMA_VERSION,
    BundleFile,
    BundleLimits,
    BundleValidationError,
    InspectedBundle,
    build_canonical_zip,
    inspect_project_bundle,
    normalize_bundle_path,
    sanitize_file_for_export,
)
from servers.services.playbooks.bundle_content import blocking_secret_findings, sanitize_preview_value
from servers.services.playbooks.bundle_storage import (
    BundleStorageError,
    PlaybookBundleStorage,
    get_playbook_bundle_storage,
)
from servers.services.playbooks.content import PlaybookContentError, calculate_content_hash, validate_content
from servers.services.playbooks.controller_policy import analyze_project_files_controller_policy
from servers.services.playbooks.sharing import sync_legacy_visibility_grant


@dataclass(frozen=True)
class BundleCommitResult:
    playbook: Playbook
    revision: PlaybookRevision
    asset_bundle: PlaybookAssetBundle
    preview: dict[str, Any]


@dataclass(frozen=True)
class BundleExport:
    content: bytes
    filename: str
    redaction_count: int


@dataclass(frozen=True)
class BundleRefreshResult:
    revision: PlaybookRevision
    asset_bundle: PlaybookAssetBundle
    base_revision: PlaybookRevision
    preview: dict[str, Any]
    diff: dict[str, Any]


def preview_project_bundle(
    archive: bytes,
    *,
    requested_entrypoint: str = "",
    limits: BundleLimits | None = None,
    allow_single_root: bool = False,
    allow_repository_metadata: bool = False,
    project_path: str = "",
) -> dict[str, Any]:
    try:
        inspected = inspect_project_bundle(
            archive,
            limits=limits,
            allow_single_root=allow_single_root,
            allow_repository_metadata=allow_repository_metadata,
            project_path=project_path,
        )
    except BundleValidationError as exc:
        if exc.code != "yaml_complexity_limit":
            raise
        return {
            "archive_format": "unavailable",
            "content_hash": hashlib.sha256(archive).hexdigest(),
            "file_count": 0,
            "total_size_bytes": len(archive),
            "files": [],
            "tree": {"entrypoint": "", "files": []},
            "manifest": {},
            "entrypoints": [],
            "selected_entrypoint": "",
            "secret_warnings": [],
            "controller_warnings": [],
            "complexity_warnings": [{"code": exc.code, "message": str(exc)}],
            "ignored_files": [],
            "dependencies": {"collections": [], "roles": []},
            "compatibility": None,
            "safe_to_commit": False,
            "project_path": str(project_path or ""),
        }
    selected = _select_entrypoint(inspected, requested_entrypoint, required=False)
    return _preview_payload(inspected, selected_entrypoint=selected)


def commit_project_bundle(
    archive: bytes,
    *,
    actor,
    requested_entrypoint: str = "",
    name: str = "",
    description: str = "",
    category: str = Playbook.CATEGORY_CUSTOM,
    visibility: str = Playbook.VISIBILITY_PRIVATE,
    tags: list[str] | None = None,
    storage: PlaybookBundleStorage | None = None,
    limits: BundleLimits | None = None,
    allow_single_root: bool = False,
    allow_repository_metadata: bool = False,
    project_path: str = "",
    source_metadata: dict[str, Any] | None = None,
) -> BundleCommitResult:
    """Commit one clean project atomically and clean up its artifact on rollback."""

    if not getattr(actor, "is_authenticated", False):
        raise BundleValidationError("Authentication is required", code="authentication_required", status_code=403)
    limits = limits or BundleLimits.from_settings()
    inspected = inspect_project_bundle(
        archive,
        limits=limits,
        allow_single_root=allow_single_root,
        allow_repository_metadata=allow_repository_metadata,
        project_path=project_path,
    )
    blocking_findings = blocking_secret_findings(inspected.secret_findings)
    if blocking_findings:
        raise BundleValidationError(
            "Bundle contains secret material and cannot be committed",
            code="secret_material_detected",
            status_code=422,
            details={"findings": blocking_findings},
        )
    entrypoint = _select_entrypoint(inspected, requested_entrypoint, required=True)
    controller_findings = _bundle_controller_findings(inspected, entrypoint=entrypoint)
    if controller_findings:
        raise BundleValidationError(
            "Bundle contains controller-side operations that are not allowed",
            code="controller_policy_violation",
            status_code=422,
            details={"issues": controller_findings[:20]},
        )
    file_map = inspected.file_map()
    source_yaml = file_map[entrypoint].content.decode("utf-8")

    try:
        parsed = parse_ansible_playbook(source_yaml, entrypoint)
        source_yaml, parsed_tasks = validate_content(
            content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
            source_yaml=source_yaml,
            tasks=parsed.get("tasks") or [],
        )
    except (ValueError, PlaybookContentError) as exc:
        raise BundleValidationError(
            "Entrypoint is not a supported Ansible playbook", code="invalid_entrypoint"
        ) from exc

    playbook_name = _clean_name(
        name or inspected.manifest.get("name") or parsed.get("name") or PurePosixPath(entrypoint).stem
    )
    playbook_description = str(description or inspected.manifest.get("description") or parsed.get("description") or "")[
        :4000
    ]
    category = (
        category if category in {choice for choice, _label in Playbook.CATEGORY_CHOICES} else Playbook.CATEGORY_CUSTOM
    )
    # New imports are owner-private. Legacy shared projects remain readable, but
    # accepting this request field would silently enroll an existing workspace.
    visibility = Playbook.VISIBILITY_PRIVATE
    normalized_tags = _normalize_tags(
        tags if tags is not None else inspected.manifest.get("tags") or parsed.get("tags") or []
    )
    canonical_archive = build_canonical_zip({item.path: item.content for item in inspected.files})
    storage = storage or get_playbook_bundle_storage()
    storage_key = storage.save(canonical_archive, content_hash=inspected.content_hash)

    try:
        with transaction.atomic():
            asset_bundle = PlaybookAssetBundle.objects.create(
                storage_key=storage_key,
                manifest=[item.manifest_item() for item in inspected.files],
                content_hash=inspected.content_hash,
                size_bytes=inspected.total_size,
                file_count=len(inspected.files),
                scan_status=PlaybookAssetBundle.SCAN_CLEAN,
                scan_report={
                    "archive_format": inspected.archive_format,
                    "entrypoint": entrypoint,
                    "project_path": inspected.project_path,
                    "manifest": inspected.manifest,
                    "checks": {
                        "paths": "clean",
                        "links": "clean",
                        "limits": "clean",
                        "secrets": "clean",
                    },
                },
                created_by=actor,
            )
            compatibility = analyze_playbook_compatibility(source_yaml)
            playbook = Playbook.objects.create(
                user=actor,
                name=playbook_name,
                description=playbook_description,
                kind=Playbook.KIND_ANSIBLE,
                category=category,
                visibility=visibility,
                tasks=parsed_tasks,
                source_yaml=source_yaml,
                tags=normalized_tags,
                fidelity=parsed.get("fidelity") if isinstance(parsed.get("fidelity"), dict) else {},
                compatibility=compatibility,
            )
            content_hash = calculate_content_hash(
                content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
                source_yaml=source_yaml,
                tasks=parsed_tasks,
                bundle_hash=inspected.content_hash,
            )
            revision = PlaybookRevision.objects.create(
                playbook=playbook,
                revision_number=1,
                author=actor,
                content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
                source_yaml=source_yaml,
                tasks=parsed_tasks,
                content_hash=content_hash,
                asset_bundle=asset_bundle,
                bundle_hash=inspected.content_hash,
                origin_type=PlaybookRevision.ORIGIN_IMPORTED,
                message="Imported project bundle",
                metadata={
                    "bundle_entrypoint": entrypoint,
                    "bundle_project_path": inspected.project_path,
                    "required_collections": list(inspected.dependencies.get("collections") or []),
                    "required_roles": list(inspected.dependencies.get("roles") or []),
                    **({"source": _safe_source_metadata(source_metadata)} if source_metadata else {}),
                },
            )
            playbook.origin_revision = revision
            playbook.published_revision = revision
            playbook.save(update_fields=["origin_revision", "published_revision", "updated_at"])
            PlaybookDraft.objects.create(
                playbook=playbook,
                base_revision=revision,
                content_format=revision.content_format,
                source_yaml=source_yaml,
                tasks=parsed_tasks,
                content_hash=content_hash,
                asset_bundle=asset_bundle,
                bundle_hash=inspected.content_hash,
                last_editor=actor,
            )
            sync_legacy_visibility_grant(playbook, actor=actor)
            record_playbook_event(
                playbook=playbook,
                actor=actor,
                event_type="bundle_imported",
                entity_type="revision",
                entity_id=revision.id,
                metadata={
                    "bundle_hash": inspected.content_hash,
                    "file_count": len(inspected.files),
                    "entrypoint": entrypoint,
                },
            )
    except Exception:
        storage.delete(storage_key)
        raise

    return BundleCommitResult(
        playbook=playbook,
        revision=revision,
        asset_bundle=asset_bundle,
        preview=_preview_payload(inspected, selected_entrypoint=entrypoint),
    )


def latest_gitlab_source_revision(playbook: Playbook) -> tuple[PlaybookRevision, dict[str, str]]:
    """Return the newest revision carrying allowlisted GitLab provenance."""

    revisions = playbook.content_revisions.select_related("asset_bundle").order_by("-revision_number")[:100]
    for revision in revisions:
        metadata = revision.metadata if isinstance(revision.metadata, dict) else {}
        source = metadata.get("source")
        if isinstance(source, dict) and source.get("type") == "gitlab":
            cleaned = _safe_source_metadata(source)
            if cleaned.get("host") and cleaned.get("project"):
                return revision, cleaned
    raise BundleValidationError(
        "Playbook has no refreshable GitLab source metadata",
        code="gitlab_source_unavailable",
        status_code=409,
    )


def bundle_refresh_diff(base_revision: PlaybookRevision, preview: dict[str, Any]) -> dict[str, Any]:
    base_manifest = (
        base_revision.asset_bundle.manifest
        if base_revision.asset_bundle_id
        and base_revision.asset_bundle
        and isinstance(base_revision.asset_bundle.manifest, list)
        else []
    )
    before = {
        str(item.get("path")): str(item.get("sha256") or "")
        for item in base_manifest
        if isinstance(item, dict) and item.get("path")
    }
    after = {
        str(item.get("path")): str(item.get("sha256") or "")
        for item in preview.get("files") or []
        if isinstance(item, dict) and item.get("path")
    }
    return {
        "from_bundle_hash": base_revision.bundle_hash,
        "to_bundle_hash": str(preview.get("content_hash") or ""),
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(path for path in set(before) & set(after) if before[path] != after[path]),
        "unchanged_count": sum(1 for path in set(before) & set(after) if before[path] == after[path]),
    }


def commit_refreshed_project_bundle(
    playbook: Playbook,
    archive: bytes,
    *,
    actor,
    base_revision: PlaybookRevision,
    requested_entrypoint: str = "",
    source_metadata: dict[str, Any],
    storage: PlaybookBundleStorage | None = None,
    limits: BundleLimits | None = None,
    allow_single_root: bool = True,
    allow_repository_metadata: bool = True,
) -> BundleRefreshResult:
    """Append an imported revision without changing published state or draft."""

    if not getattr(actor, "is_authenticated", False):
        raise BundleValidationError("Authentication is required", code="authentication_required", status_code=403)
    if base_revision.playbook_id != playbook.id:
        raise BundleValidationError("Refresh base does not belong to playbook", code="gitlab_refresh_base_changed")
    limits = limits or BundleLimits.from_settings()
    inspected = inspect_project_bundle(
        archive,
        limits=limits,
        allow_single_root=allow_single_root,
        allow_repository_metadata=allow_repository_metadata,
    )
    blocking_findings = blocking_secret_findings(inspected.secret_findings)
    if blocking_findings:
        raise BundleValidationError(
            "Bundle contains secret material and cannot be committed",
            code="secret_material_detected",
            status_code=422,
            details={"findings": blocking_findings},
        )
    entrypoint = _select_entrypoint(inspected, requested_entrypoint, required=True)
    controller_findings = _bundle_controller_findings(inspected, entrypoint=entrypoint)
    if controller_findings:
        raise BundleValidationError(
            "Bundle contains controller-side operations that are not allowed",
            code="controller_policy_violation",
            status_code=422,
            details={"issues": controller_findings[:20]},
        )
    source_yaml = inspected.file_map()[entrypoint].content.decode("utf-8")
    try:
        parsed = parse_ansible_playbook(source_yaml, entrypoint)
        source_yaml, parsed_tasks = validate_content(
            content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
            source_yaml=source_yaml,
            tasks=parsed.get("tasks") or [],
        )
    except (ValueError, PlaybookContentError) as exc:
        raise BundleValidationError(
            "Entrypoint is not a supported Ansible playbook", code="invalid_entrypoint"
        ) from exc

    preview = _preview_payload(inspected, selected_entrypoint=entrypoint)
    diff = bundle_refresh_diff(base_revision, preview)
    canonical_archive = build_canonical_zip({item.path: item.content for item in inspected.files})
    storage = storage or get_playbook_bundle_storage()
    storage_key = storage.save(canonical_archive, content_hash=inspected.content_hash)
    try:
        with transaction.atomic():
            locked = Playbook.objects.select_for_update().get(pk=playbook.pk)
            current_base, _current_source = latest_gitlab_source_revision(locked)
            if current_base.id != base_revision.id:
                raise BundleValidationError(
                    "The GitLab refresh base changed after preview",
                    code="gitlab_refresh_base_changed",
                    status_code=409,
                )
            asset_bundle = PlaybookAssetBundle.objects.create(
                storage_key=storage_key,
                manifest=[item.manifest_item() for item in inspected.files],
                content_hash=inspected.content_hash,
                size_bytes=inspected.total_size,
                file_count=len(inspected.files),
                scan_status=PlaybookAssetBundle.SCAN_CLEAN,
                scan_report={
                    "archive_format": inspected.archive_format,
                    "entrypoint": entrypoint,
                    "project_path": inspected.project_path,
                    "manifest": inspected.manifest,
                    "checks": {"paths": "clean", "links": "clean", "limits": "clean", "secrets": "clean"},
                },
                created_by=actor,
            )
            next_number = (locked.content_revisions.aggregate(value=Max("revision_number"))["value"] or 0) + 1
            content_hash = calculate_content_hash(
                content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
                source_yaml=source_yaml,
                tasks=parsed_tasks,
                bundle_hash=inspected.content_hash,
            )
            revision = PlaybookRevision.objects.create(
                playbook=locked,
                revision_number=next_number,
                parent=base_revision,
                author=actor,
                content_format=PlaybookRevision.FORMAT_ANSIBLE_YAML,
                source_yaml=source_yaml,
                tasks=parsed_tasks,
                content_hash=content_hash,
                asset_bundle=asset_bundle,
                bundle_hash=inspected.content_hash,
                origin_type=PlaybookRevision.ORIGIN_IMPORTED,
                message="Refreshed GitLab project snapshot",
                metadata={
                    "bundle_entrypoint": entrypoint,
                    "bundle_project_path": inspected.project_path,
                    "required_collections": list(inspected.dependencies.get("collections") or []),
                    "required_roles": list(inspected.dependencies.get("roles") or []),
                    "source": _safe_source_metadata(source_metadata),
                    "refresh_of_revision_id": base_revision.id,
                    "bundle_diff": diff,
                },
            )
            record_playbook_event(
                playbook=locked,
                actor=actor,
                event_type="gitlab_bundle_refreshed",
                entity_type="revision",
                entity_id=revision.id,
                metadata={
                    "base_revision_id": base_revision.id,
                    "bundle_hash": inspected.content_hash,
                    "added": len(diff["added"]),
                    "removed": len(diff["removed"]),
                    "changed": len(diff["changed"]),
                },
            )
    except Exception:
        storage.delete(storage_key)
        raise

    return BundleRefreshResult(
        revision=revision,
        asset_bundle=asset_bundle,
        base_revision=base_revision,
        preview=preview,
        diff=diff,
    )


def _safe_source_metadata(value: dict[str, Any]) -> dict[str, str]:
    """Persist provenance only; credentials and arbitrary provider payloads are never accepted."""

    allowed = {"type", "host", "project", "ref", "path", "commit_sha"}
    return {
        key: str(item)[:500]
        for key, item in value.items()
        if key in allowed and isinstance(item, (str, int)) and str(item).strip()
    }


def export_revision_bundle(
    revision: PlaybookRevision,
    *,
    actor=None,
    storage: PlaybookBundleStorage | None = None,
    limits: BundleLimits | None = None,
) -> BundleExport:
    """Export a revision without ORM metadata, inventory bindings or secret values."""

    from servers.services.playbooks.revision_safety import validate_revision_safety

    limits = limits or BundleLimits.from_settings()
    storage = storage or get_playbook_bundle_storage()
    validate_revision_safety(revision, storage=storage)
    inspected: InspectedBundle | None = None
    files: dict[str, BundleFile] = {}
    source_manifest: dict[str, Any] = {}

    if revision.asset_bundle_id:
        asset = revision.asset_bundle
        if asset.scan_status != PlaybookAssetBundle.SCAN_CLEAN:
            raise BundleValidationError(
                "Only clean asset bundles can be exported", code="bundle_not_clean", status_code=409
            )
        stored_limits = BundleLimits(
            max_archive_bytes=max(limits.max_archive_bytes, limits.max_total_bytes + limits.max_files * 1024),
            max_file_bytes=limits.max_file_bytes,
            max_total_bytes=limits.max_total_bytes,
            max_files=limits.max_files,
            max_yaml_aliases=limits.max_yaml_aliases,
        )
        archive = storage.read(asset.storage_key, max_bytes=stored_limits.max_archive_bytes)
        inspected = inspect_project_bundle(archive, limits=stored_limits)
        if inspected.content_hash != asset.content_hash or (
            revision.bundle_hash and inspected.content_hash != revision.bundle_hash
        ):
            raise BundleStorageError("Stored playbook bundle failed its integrity check")
        files = inspected.file_map()
        source_manifest = inspected.manifest

    if revision.content_format != PlaybookRevision.FORMAT_ANSIBLE_YAML or not revision.source_yaml.strip():
        raise BundleValidationError(
            "Project bundle export currently requires an Ansible YAML revision",
            code="unsupported_revision_format",
            status_code=422,
        )

    entrypoint = _export_entrypoint(revision, inspected)
    source_bytes = revision.source_yaml.encode("utf-8")
    files[entrypoint] = BundleFile(
        path=entrypoint,
        content=source_bytes,
        sha256=hashlib.sha256(source_bytes).hexdigest(),
        is_text=True,
    )

    export_files: dict[str, bytes] = {}
    redaction_count = 0
    for path, item in sorted(files.items()):
        if path in {MANIFEST_NAME, CHECKSUMS_NAME}:
            continue
        sanitized, count = sanitize_file_for_export(item)
        redaction_count += count
        if sanitized is not None:
            export_files[path] = sanitized

    payload_checksums = {
        path: hashlib.sha256(content).hexdigest()
        for path, content in sorted(export_files.items())
    }
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "name": revision.playbook.name[:200],
        "entrypoint": entrypoint,
        "required_collections": _safe_dependency_list(source_manifest.get("required_collections")),
        "required_roles": _safe_dependency_list(source_manifest.get("required_roles")),
        "revision": {
            "id": revision.id,
            "number": revision.revision_number,
            "content_hash": revision.content_hash,
            "bundle_hash": revision.bundle_hash,
        },
        "sanitized": True,
        "redaction_count": redaction_count,
        "checksum_algorithm": "sha256",
        "checksums_file": CHECKSUMS_NAME,
        "checksums": payload_checksums,
    }
    export_files[MANIFEST_NAME] = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    export_files[CHECKSUMS_NAME] = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {path}\n"
        for path, content in sorted(export_files.items())
    ).encode("utf-8")
    output = build_canonical_zip(export_files)

    if actor is not None:
        record_playbook_event(
            playbook=revision.playbook,
            actor=actor,
            event_type="revision_exported",
            entity_type="revision",
            entity_id=revision.id,
            metadata={"redaction_count": redaction_count, "file_count": len(export_files)},
        )

    filename = f"{slugify(revision.playbook.name) or 'playbook'}-r{revision.revision_number}.zip"
    return BundleExport(content=output, filename=filename, redaction_count=redaction_count)


def _preview_payload(inspected: InspectedBundle, *, selected_entrypoint: str) -> dict[str, Any]:
    from servers.services.playbooks.draft_files import is_editable_draft_yaml_path

    files = sanitize_preview_value([
        {
            **item.manifest_item(),
            "editable": is_editable_draft_yaml_path(item.path),
            "is_entrypoint": item.path == selected_entrypoint,
        }
        for item in inspected.files
    ])
    controller_findings = _bundle_controller_findings(inspected, entrypoint=selected_entrypoint)
    blocking_findings = blocking_secret_findings(inspected.secret_findings)
    compatibility: dict[str, Any] | None = None
    if selected_entrypoint:
        try:
            compatibility = analyze_playbook_compatibility(
                inspected.file_map()[selected_entrypoint].content.decode("utf-8")
            )
        except (KeyError, UnicodeDecodeError):
            compatibility = None
    dependencies = {
        "collections": list(inspected.dependencies.get("collections") or []),
        "roles": list(inspected.dependencies.get("roles") or []),
    }
    manifest = sanitize_preview_value(
        {
            **inspected.manifest,
            "required_collections": dependencies["collections"],
            "required_roles": dependencies["roles"],
        }
    )
    safe_dependencies = sanitize_preview_value(dependencies)
    safe_entrypoints = sanitize_preview_value(list(inspected.entrypoints))
    safe_compatibility = sanitize_preview_value(compatibility)
    safe_selected_entrypoint = sanitize_preview_value(selected_entrypoint)
    return {
        "archive_format": inspected.archive_format,
        "content_hash": inspected.content_hash,
        "file_count": len(inspected.files),
        "total_size_bytes": inspected.total_size,
        "files": files,
        "tree": {"entrypoint": safe_selected_entrypoint, "files": files},
        "manifest": manifest,
        "entrypoints": safe_entrypoints,
        "selected_entrypoint": safe_selected_entrypoint,
        "secret_warnings": sanitize_preview_value(list(inspected.secret_findings)),
        "controller_warnings": sanitize_preview_value(controller_findings),
        "complexity_warnings": [],
        "ignored_files": sanitize_preview_value(list(inspected.ignored_files)),
        "dependencies": safe_dependencies,
        "compatibility": safe_compatibility,
        "safe_to_commit": not blocking_findings and not controller_findings,
        "project_path": inspected.project_path,
    }


def _bundle_controller_findings(inspected: InspectedBundle, *, entrypoint: str) -> list[dict[str, Any]]:
    files = {item.path: item.content for item in inspected.files}
    findings = analyze_project_files_controller_policy(files)
    if entrypoint and entrypoint in files:
        try:
            report = analyze_playbook_compatibility(files[entrypoint].decode("utf-8"))
        except UnicodeDecodeError:
            report = {"issues": []}
        for issue in report.get("issues") or []:
            if isinstance(issue, dict) and str(issue.get("code") or "").startswith("controller_"):
                findings.append({**issue, "path": str(issue.get("path") or entrypoint)})
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in findings:
        key = (str(item.get("path") or ""), str(item.get("code") or ""), str(item.get("message") or ""))
        unique[key] = item
    return [unique[key] for key in sorted(unique)]


def _select_entrypoint(inspected: InspectedBundle, requested: str, *, required: bool) -> str:
    candidates = {item["path"] for item in inspected.entrypoints}
    selected = requested.strip() if isinstance(requested, str) else ""
    if selected:
        selected = normalize_bundle_path(selected)
        if selected not in candidates:
            raise BundleValidationError("Selected entrypoint is not a valid playbook", code="invalid_entrypoint")
        return selected
    manifest_entrypoint = str(inspected.manifest.get("entrypoint") or "")
    if manifest_entrypoint:
        return manifest_entrypoint
    if len(candidates) == 1:
        return next(iter(candidates))
    if required:
        raise BundleValidationError("Select one entrypoint before import", code="entrypoint_required")
    return ""


def _export_entrypoint(revision: PlaybookRevision, inspected: InspectedBundle | None) -> str:
    metadata = revision.metadata if isinstance(revision.metadata, dict) else {}
    candidate = metadata.get("bundle_entrypoint")
    if isinstance(candidate, str) and candidate:
        try:
            candidate = normalize_bundle_path(candidate)
        except BundleValidationError:
            candidate = ""
        if candidate and "/" not in candidate and PurePosixPath(candidate).suffix.lower() in {".yml", ".yaml"}:
            return candidate
    if inspected:
        manifest_entrypoint = inspected.manifest.get("entrypoint")
        if isinstance(manifest_entrypoint, str) and manifest_entrypoint:
            return manifest_entrypoint
        if len(inspected.entrypoints) == 1:
            return str(inspected.entrypoints[0]["path"])
    return "playbook.yml"


def _clean_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        raise BundleValidationError("Playbook name is required", code="name_required")
    return name[:200]


def _normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        tag = str(item or "").strip()
        if tag and tag not in output:
            output.append(tag[:80])
        if len(output) >= 20:
            break
    return output


def _safe_dependency_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item[:200] for item in value if isinstance(item, str) and item.strip()][:100]
