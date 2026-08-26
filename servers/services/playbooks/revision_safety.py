"""Fail-closed safety gate for persisted executable playbook revisions."""

from __future__ import annotations

from types import SimpleNamespace

from servers.models import Playbook, PlaybookDraft, PlaybookRevision
from servers.services.playbooks.bundle_archive import (
    BundleLimits,
    BundleValidationError,
    build_canonical_zip,
    inspect_project_bundle,
    normalize_bundle_path,
)
from servers.services.playbooks.bundle_content import blocking_secret_findings
from servers.services.playbooks.bundle_runtime import BundleRuntimeError, load_revision_runtime_bundle
from servers.services.playbooks.bundle_storage import PlaybookBundleStorage
from servers.services.playbooks.controller_policy import analyze_project_files_controller_policy
from servers.services.playbooks.source_guard import PlaybookSourceSafetyError, validate_ansible_source


def validate_revision_safety(
    revision: PlaybookRevision,
    *,
    storage: PlaybookBundleStorage | None = None,
) -> None:
    """Reject unsafe historical rows before publish, export, or new sharing."""

    if revision.content_format != PlaybookRevision.FORMAT_ANSIBLE_YAML:
        return
    metadata = revision.metadata if isinstance(revision.metadata, dict) else {}
    entrypoint = normalize_bundle_path(str(metadata.get("bundle_entrypoint") or "playbook.yml"))
    try:
        safety = validate_ansible_source(revision.source_yaml, path=entrypoint)
    except PlaybookSourceSafetyError as exc:
        raise BundleValidationError(
            str(exc),
            code=exc.code,
            status_code=422 if exc.status_code < 500 else exc.status_code,
            details=exc.details,
        ) from exc

    try:
        runtime_bundle = load_revision_runtime_bundle(revision, storage=storage)
    except BundleRuntimeError as exc:
        raise BundleValidationError(
            "Revision bundle failed its integrity check",
            code="revision_bundle_unsafe",
            status_code=422,
        ) from exc
    if runtime_bundle is None:
        return

    entrypoint = runtime_bundle.entrypoint
    files = dict(runtime_bundle.files)
    files[entrypoint] = safety.source_yaml.encode("utf-8")
    limits = BundleLimits.from_settings()
    inspected = inspect_project_bundle(build_canonical_zip(files), limits=limits)
    blocking_findings = blocking_secret_findings(inspected.secret_findings)
    if blocking_findings:
        raise BundleValidationError(
            "Revision bundle contains secret material",
            code="secret_material_detected",
            status_code=422,
            details={"findings": blocking_findings[:20]},
        )
    controller_findings = analyze_project_files_controller_policy(files, skip_paths={entrypoint})
    if controller_findings:
        raise BundleValidationError(
            "Revision bundle contains controller-side operations",
            code="controller_policy_violation",
            status_code=422,
            details={"issues": controller_findings[:20]},
        )


def validate_draft_safety(
    draft: PlaybookDraft,
    *,
    storage: PlaybookBundleStorage | None = None,
) -> None:
    """Apply the immutable-revision safety boundary to unpublished draft bytes."""

    base_metadata = (
        draft.base_revision.metadata
        if draft.base_revision_id and isinstance(draft.base_revision.metadata, dict)
        else {}
    )
    candidate = SimpleNamespace(
        content_format=draft.content_format,
        source_yaml=draft.source_yaml,
        asset_bundle_id=draft.asset_bundle_id,
        asset_bundle=draft.asset_bundle,
        bundle_hash=draft.bundle_hash,
        metadata=base_metadata,
    )
    validate_revision_safety(candidate, storage=storage)


def validate_legacy_playbook_safety(playbook: Playbook) -> None:
    """Validate a pre-workspace row before propagating it into immutable content."""

    content_format = (
        PlaybookRevision.FORMAT_ANSIBLE_YAML
        if (playbook.source_yaml or "").strip()
        else PlaybookRevision.FORMAT_RUNBOOK_JSON
    )
    candidate = SimpleNamespace(
        content_format=content_format,
        source_yaml=playbook.source_yaml or "",
        asset_bundle_id=None,
        asset_bundle=None,
        bundle_hash="",
        metadata={},
    )
    validate_revision_safety(candidate)
