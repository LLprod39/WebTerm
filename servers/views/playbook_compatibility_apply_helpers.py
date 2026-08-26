"""Typed helpers for compatibility proposal application."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.db import transaction

from servers.models_playbooks import PlaybookCompatibilityRevision
from servers.services.playbook_compatibility_ai import (
    PlaybookAdaptationError,
    compare_yaml_fragment_semantics,
    validate_yaml_fragment_safety,
)
from servers.services.playbook_compatibility_analysis import analyze_playbook_compatibility, compare_semantics
from servers.services.playbooks.draft_files import update_draft_text_file
from servers.services.playbooks.source_guard import PlaybookSourceSafetyError, validate_ansible_source


class CompatibilityApplyInputError(ValueError):
    pass


class CompatibilityApplyEvaluationError(ValueError):
    def __init__(self, message: str, *, code: str, status: int, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details or {}


@dataclass(frozen=True)
class CompatibilityBaseExpectation:
    path: str
    content_hash: str
    draft_version: int | None
    revision_id: int | None
    bundle_hash: str


@dataclass(frozen=True)
class CompatibilityEvaluation:
    adapted_yaml: str
    guard: dict[str, Any]
    report: dict[str, Any]
    status: str


def parse_base_expectation(data: dict[str, Any]) -> CompatibilityBaseExpectation:
    path = str(data.get("path") or data.get("base_path") or "").strip()
    content_hash = str(data.get("expected_content_hash") or data.get("base_content_hash") or "").strip().lower()
    version_value = data.get("expected_draft_version", data.get("base_version"))
    try:
        draft_version = int(version_value) if version_value is not None else None
        revision_id = int(data["base_revision_id"]) if data.get("base_revision_id") is not None else None
    except (TypeError, ValueError) as exc:
        raise CompatibilityApplyInputError("Compatibility base fields are invalid") from exc
    bundle_hash_present = "expected_bundle_hash" in data or "base_bundle_hash" in data
    bundle_hash = str(data.get("expected_bundle_hash", data.get("base_bundle_hash", "")) or "").strip().lower()
    if not (
        path
        and _is_sha256(content_hash)
        and (draft_version is not None or revision_id is not None)
        and bundle_hash_present
        and _is_sha256(bundle_hash)
    ):
        raise CompatibilityApplyInputError(
            "path, expected_content_hash, expected_bundle_hash and either "
            "expected_draft_version or base_revision_id are required"
        )
    return CompatibilityBaseExpectation(path, content_hash, draft_version, revision_id, bundle_hash)


def expectation_is_stale(
    expectation: CompatibilityBaseExpectation,
    *,
    current: dict[str, Any],
    selected_path: str,
) -> bool:
    return bool(
        current["path"] != selected_path
        or current["content_hash"] != expectation.content_hash
        or (
            expectation.draft_version is not None
            and current["draft_version"] != expectation.draft_version
        )
        or (expectation.revision_id is not None and current["base_revision_id"] != expectation.revision_id)
        or current["bundle_hash"] != expectation.bundle_hash
    )


def evaluate_compatibility_apply(
    *,
    source: str,
    adapted_yaml: str,
    snapshot,
    bindings: dict[str, Any],
    target_servers: list[Any],
    syntax_validator: Callable[..., dict[str, Any]],
) -> CompatibilityEvaluation:
    if snapshot.is_entrypoint:
        guard, report, normalized_yaml = _evaluate_entrypoint(
            source=source,
            adapted_yaml=adapted_yaml,
            path=snapshot.path,
            bindings=bindings,
            target_servers=target_servers,
            syntax_validator=syntax_validator,
        )
    else:
        guard, report = _evaluate_fragment(source=source, adapted_yaml=adapted_yaml, path=snapshot.path)
        normalized_yaml = adapted_yaml
    has_blocker = any(item.get("severity") == "error" for item in report.get("issues") or [])
    status = (
        PlaybookCompatibilityRevision.STATUS_VALIDATED
        if guard["passed"] and not has_blocker
        else PlaybookCompatibilityRevision.STATUS_REJECTED
    )
    return CompatibilityEvaluation(normalized_yaml, guard, report, status)


@transaction.atomic
def persist_compatibility_apply(
    *,
    playbook,
    actor,
    draft,
    snapshot,
    current_base: dict[str, Any],
    data: dict[str, Any],
    bindings: dict[str, Any],
    source: str,
    evaluation: CompatibilityEvaluation,
):
    revision = PlaybookCompatibilityRevision.objects.create(
        playbook=playbook,
        user=actor,
        source_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        adapted_yaml=evaluation.adapted_yaml,
        inventory_bindings=bindings,
        report=evaluation.report,
        semantic_guard=evaluation.guard,
        change_summary=[str(item) for item in data.get("changes") or []][:20],
        status=evaluation.status,
        source_revision=draft.base_revision,
    )
    saved_draft = None
    if evaluation.status == PlaybookCompatibilityRevision.STATUS_VALIDATED:
        saved_draft, _snapshot, _tree = update_draft_text_file(
            playbook,
            actor=actor,
            path=snapshot.path,
            content=evaluation.adapted_yaml,
            expected_draft_version=draft.version,
            expected_bundle_hash=current_base["bundle_hash"],
        )
    return revision, saved_draft


def compatibility_revision_payload(revision) -> dict[str, Any]:
    return {
        "id": revision.id,
        "status": revision.status,
        "report": revision.report,
        "semantic_guard": revision.semantic_guard,
        "change_summary": revision.change_summary,
        "created_at": revision.created_at.isoformat(),
    }


def compatibility_failure_message(guard: dict[str, Any], report: dict[str, Any]) -> str:
    if not guard.get("passed"):
        violations = [str(item) for item in guard.get("violations") or [] if str(item).strip()]
        detail = "; ".join(violations[:3]) or "protected playbook logic changed"
        return f"AI patch rejected: {detail}"
    blockers = [
        str(item.get("message") or item.get("code") or "Unknown blocker")
        for item in report.get("issues") or []
        if item.get("severity") == "error"
    ]
    if blockers:
        return "Adaptation blocked: " + "; ".join(blockers[:3])
    return "Adaptation failed an unknown compatibility check"


def _evaluate_entrypoint(
    *,
    source: str,
    adapted_yaml: str,
    path: str,
    bindings: dict[str, Any],
    target_servers: list[Any],
    syntax_validator: Callable[..., dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    try:
        safety = validate_ansible_source(adapted_yaml, path=path)
    except PlaybookSourceSafetyError as exc:
        raise CompatibilityApplyEvaluationError(
            str(exc), code=exc.code, status=exc.status_code, details=exc.details
        ) from exc
    guard = compare_semantics(source, adapted_yaml)
    report = analyze_playbook_compatibility(safety.source_yaml, bindings=bindings, target_servers=target_servers)
    if guard["passed"] and not any(item.get("severity") == "error" for item in report.get("issues") or []):
        syntax_check = syntax_validator(adapted_yaml, allow_dependency_setup=False)
        report["syntax_check"] = syntax_check
        if syntax_check.get("passed") is False:
            report.setdefault("issues", []).append(
                {
                    "code": "ansible_syntax_check",
                    "severity": "error",
                    "message": syntax_check.get("message") or "Ansible syntax check failed",
                    "path": "playbook",
                }
            )
    return guard, report, safety.source_yaml


def _evaluate_fragment(*, source: str, adapted_yaml: str, path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        validate_yaml_fragment_safety(adapted_yaml, path=path)
    except PlaybookAdaptationError as exc:
        raise CompatibilityApplyEvaluationError(
            str(exc), code="playbook_fragment_invalid", status=422
        ) from exc
    guard = compare_yaml_fragment_semantics(source, adapted_yaml, path=path)
    report = {
        "status": "ready" if guard["passed"] else "blocked",
        "ready": bool(guard["passed"]),
        "issues": []
        if guard["passed"]
        else [
            {
                "code": "fragment_semantics_changed",
                "severity": "error",
                "message": guard["violations"][0],
                "path": path,
            }
        ],
        "syntax_check": {"status": "passed", "passed": True, "method": "safe-yaml"},
    }
    return guard, report


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
