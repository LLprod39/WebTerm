"""Fail-closed draft promotion for approved server-memory assets."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from app.egress_redaction import redact_text
from core_ui.context_processors import user_can_feature
from servers.models import PlaybookRevision, PlaybookValidation, ServerMemoryAsset, ServerMemoryPromotion
from servers.services.memory_asset_access import has_memory_management_boundary
from servers.services.playbook_compatibility_analysis import analyze_playbook_compatibility, contains_literal_secrets
from servers.services.playbooks.access import capabilities_for
from servers.services.playbooks.bundle_archive import BundleFile
from servers.services.playbooks.bundle_content import scan_bundle_secrets
from servers.services.playbooks.content import validate_content
from servers.services.playbooks.revisions import (
    create_revision_from_draft,
    ensure_playbook_workspace,
    update_draft,
)
from servers.services.playbooks.validation import validate_revision

FEATURE_FLAG_SETTING = "SERVER_MEMORY_PROMOTION_ENABLED"
MAX_VALIDATION_RESULT_BYTES = 16_000
_HIGH_CONFIDENCE_SECRET_REPORTS = {
    "pem_block",
    "private_key_inline",
    "bearer_token",
    "auth_header",
    "connection_string",
    "aws_access_key",
    "github_pat",
    "openai_api_key",
    "gitlab_pat",
    "slack_token",
    "azure_sas_token",
}


class MemoryPromotionError(ValueError):
    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


def memory_promotion_enabled() -> bool:
    return bool(getattr(settings, FEATURE_FLAG_SETTING, False))


def promote_memory_asset(*, asset, actor, destination_kind: str, playbook=None) -> ServerMemoryPromotion:
    """Create and validate an unpublished draft revision, or fail closed."""
    if not memory_promotion_enabled():
        raise MemoryPromotionError("Memory promotion is disabled", code="promotion_disabled")

    asset = (
        ServerMemoryAsset.objects.select_related(
            "server",
            "current_snapshot",
            "generation_log",
            "current_snapshot__generation_log",
        )
        .filter(pk=getattr(asset, "pk", None))
        .first()
    )
    if asset is None or asset.current_snapshot is None:
        raise MemoryPromotionError("Memory asset has no current snapshot", code="source_missing")
    snapshot = asset.current_snapshot
    if not has_memory_management_boundary(actor=actor, server=asset.server):
        raise MemoryPromotionError("Promotion requires the staff server owner", code="promotion_forbidden")
    if (
        asset.lifecycle != ServerMemoryAsset.LIFECYCLE_APPROVED
        or asset.approved_by_id is None
        or asset.approved_at is None
    ):
        raise MemoryPromotionError("Only approved memory assets can be promoted", code="source_not_approved")
    if (
        snapshot.layer != snapshot.LAYER_CANONICAL
        or not snapshot.is_active
        or snapshot.archived_at is not None
        or snapshot.asset_id != asset.id
    ):
        raise MemoryPromotionError(
            "Promotion requires the active canonical current snapshot", code="source_not_canonical"
        )
    if destination_kind not in {choice[0] for choice in ServerMemoryPromotion.DESTINATION_CHOICES}:
        raise MemoryPromotionError("Unsupported promotion destination", code="destination_invalid")

    _require_destination_permission(destination_kind=destination_kind, actor=actor, asset=asset, playbook=playbook)
    target_id = (
        getattr(playbook, "pk", None)
        if destination_kind == ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION
        else None
    )
    idempotency_key = _idempotency_key(
        asset_id=asset.id,
        snapshot_id=snapshot.id,
        destination_kind=destination_kind,
        target_id=target_id,
    )
    with transaction.atomic():
        promotion, created = ServerMemoryPromotion.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                "source_asset": asset,
                "source_snapshot": snapshot,
                "destination_kind": destination_kind,
                "playbook": playbook,
                "generation_log": asset.generation_log or snapshot.generation_log,
                "requested_by": actor,
            },
        )
    if not created:
        return promotion

    computed_source_hash = _snapshot_content_sha256(snapshot)
    stored_source_hash = str(snapshot.content_hash or "").strip().lower()
    if stored_source_hash and (
        len(stored_source_hash) != 64
        or any(character not in "0123456789abcdef" for character in stored_source_hash)
        or not hmac.compare_digest(stored_source_hash, computed_source_hash)
    ):
        _mark_promotion(
            promotion,
            status=ServerMemoryPromotion.STATUS_REJECTED,
            result=_result_with_provenance(
                promotion=promotion,
                asset=asset,
                snapshot=snapshot,
                playbook=playbook,
                ok=False,
                code="source_integrity_mismatch",
            ),
        )
        raise MemoryPromotionError(
            "The source snapshot content hash does not match its content",
            code="source_integrity_mismatch",
        )

    if destination_kind != ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION:
        code = (
            "studio_draft_gateway_unavailable"
            if destination_kind == ServerMemoryPromotion.DESTINATION_STUDIO_SKILL
            else "knowledge_draft_gateway_unavailable"
        )
        _mark_promotion(
            promotion,
            status=ServerMemoryPromotion.STATUS_FAILED,
            result=_result_with_provenance(
                promotion=promotion,
                asset=asset,
                snapshot=snapshot,
                playbook=playbook,
                ok=False,
                code=code,
            ),
        )
        raise MemoryPromotionError("No safe draft-only destination gateway is available", code=code)

    try:
        draft_payload = _validated_playbook_payload(snapshot.content)
    except MemoryPromotionError as exc:
        _mark_promotion(
            promotion,
            status=ServerMemoryPromotion.STATUS_REJECTED,
            result=_result_with_provenance(
                promotion=promotion,
                asset=asset,
                snapshot=snapshot,
                playbook=playbook,
                ok=False,
                code=exc.code,
            ),
        )
        raise

    try:
        with transaction.atomic():
            published, draft = ensure_playbook_workspace(playbook, actor=actor)
            if draft.base_revision_id != published.id or draft.content_hash != published.content_hash:
                raise MemoryPromotionError(
                    "The playbook draft contains uncommitted changes",
                    code="playbook_draft_dirty",
                )
            draft = update_draft(
                playbook,
                actor=actor,
                expected_version=draft.version,
                content_format=draft_payload["content_format"],
                source_yaml=draft_payload["source_yaml"],
                tasks=draft_payload["tasks"],
            )
            revision = create_revision_from_draft(
                playbook,
                actor=actor,
                expected_version=draft.version,
                message=f"Draft from memory asset {asset.public_id}",
                origin_type=PlaybookRevision.ORIGIN_CONVERSION,
            )
            validation = validate_revision(
                revision=revision,
                user=actor,
                target_server_ids=[asset.server_id],
                target_group_ids=[],
                provided_variable_names=sorted(draft_payload["secret_references"]),
            )
        ready = validation.status == PlaybookValidation.STATUS_READY
        _mark_promotion(
            promotion,
            status=(ServerMemoryPromotion.STATUS_VALIDATED if ready else ServerMemoryPromotion.STATUS_REJECTED),
            result=_result_with_provenance(
                promotion=promotion,
                asset=asset,
                snapshot=snapshot,
                playbook=playbook,
                revision=revision,
                ok=ready,
                code="validation_ready" if ready else "validation_blocked",
                extra={
                    "validation": _compact_validation_result(validation),
                    "binding_required": bool(draft_payload["secret_references"]),
                    "managed_secret_reference_names": sorted(draft_payload["secret_references"]),
                },
            ),
            revision=revision,
            draft_created=True,
            validated=True,
        )
    except MemoryPromotionError as exc:
        if promotion.status == ServerMemoryPromotion.STATUS_REQUESTED:
            _mark_promotion(
                promotion,
                status=ServerMemoryPromotion.STATUS_REJECTED,
                result=_result_with_provenance(
                    promotion=promotion,
                    asset=asset,
                    snapshot=snapshot,
                    playbook=playbook,
                    ok=False,
                    code=exc.code,
                ),
            )
        raise
    except Exception as exc:
        _mark_promotion(
            promotion,
            status=ServerMemoryPromotion.STATUS_FAILED,
            result=_result_with_provenance(
                promotion=promotion,
                asset=asset,
                snapshot=snapshot,
                playbook=playbook,
                ok=False,
                code="draft_or_validation_failed",
                extra={"error_type": type(exc).__name__},
            ),
        )
        raise MemoryPromotionError("Draft promotion or validation failed", code="draft_or_validation_failed") from exc
    return ServerMemoryPromotion.objects.select_related("playbook_revision").get(pk=promotion.pk)


def _require_destination_permission(*, destination_kind: str, actor, asset, playbook) -> None:
    if destination_kind == ServerMemoryPromotion.DESTINATION_PLAYBOOK_REVISION:
        if playbook is None or playbook.project_id != asset.project_id:
            raise MemoryPromotionError("A playbook in the memory project is required", code="playbook_scope_invalid")
        if not user_can_feature(actor, "automation"):
            raise MemoryPromotionError("Automation permission is required", code="automation_forbidden")
        capabilities = capabilities_for(playbook, actor)
        if not (capabilities.can_edit and capabilities.can_validate):
            raise MemoryPromotionError(
                "Playbook edit and validation permissions are required", code="playbook_forbidden"
            )
        return
    if destination_kind == ServerMemoryPromotion.DESTINATION_STUDIO_SKILL:
        if not user_can_feature(actor, "studio_skills"):
            raise MemoryPromotionError("Studio skills permission is required", code="studio_forbidden")
        return
    if not user_can_feature(actor, "servers"):
        raise MemoryPromotionError("Servers permission is required", code="servers_forbidden")


def _validated_playbook_payload(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(str(content or ""))
    except (TypeError, ValueError) as exc:
        raise MemoryPromotionError("Memory draft payload must be a JSON object", code="draft_payload_invalid") from exc
    if not isinstance(payload, dict):
        raise MemoryPromotionError("Memory draft payload must be a JSON object", code="draft_payload_invalid")
    allowed_keys = {"content_format", "source_yaml", "tasks", "secret_references"}
    if set(payload) - allowed_keys:
        raise MemoryPromotionError("Memory draft payload contains unsupported fields", code="draft_payload_invalid")

    secret_references = payload.get("secret_references") or {}
    if not isinstance(secret_references, dict) or len(secret_references) > 100:
        raise MemoryPromotionError("Secret references must be a bounded object", code="secret_references_invalid")
    normalized_references: dict[str, str] = {}
    for raw_name, raw_ref in secret_references.items():
        name = str(raw_name).strip()
        reference = str(raw_ref).strip()
        if not name or len(name) > 128 or len(reference) > 300 or not reference.startswith("managed://"):
            raise MemoryPromotionError(
                "Only bounded ManagedSecret references are accepted", code="secret_references_invalid"
            )
        normalized_references[name] = reference

    content_format = str(payload.get("content_format") or "")
    try:
        source_yaml, tasks = validate_content(
            content_format=content_format,
            source_yaml=str(payload.get("source_yaml") or ""),
            tasks=payload.get("tasks") or [],
        )
    except (TypeError, ValueError) as exc:
        raise MemoryPromotionError("Memory draft content is invalid", code="draft_content_invalid") from exc
    _reject_literal_secrets(content_format=content_format, source_yaml=source_yaml, tasks=tasks)
    return {
        "content_format": content_format,
        "source_yaml": source_yaml,
        "tasks": tasks,
        "secret_references": normalized_references,
    }


def _reject_literal_secrets(*, content_format: str, source_yaml: str, tasks: list[dict[str, Any]]) -> None:
    material = source_yaml if content_format == PlaybookRevision.FORMAT_ANSIBLE_YAML else json.dumps(tasks)
    suffix = "yml" if content_format == PlaybookRevision.FORMAT_ANSIBLE_YAML else "json"
    encoded = material.encode("utf-8")
    item = BundleFile(
        path=f"promotion.{suffix}",
        content=encoded,
        sha256=hashlib.sha256(encoded).hexdigest(),
        is_text=True,
    )
    documents = {item.path: tasks} if content_format == PlaybookRevision.FORMAT_RUNBOOK_JSON else {}
    findings = scan_bundle_secrets([item], {}, documents)
    redaction = redact_text(material)
    high_confidence = set(redaction.report) & _HIGH_CONFIDENCE_SECRET_REPORTS
    if content_format == PlaybookRevision.FORMAT_ANSIBLE_YAML:
        report = analyze_playbook_compatibility(source_yaml)
        if contains_literal_secrets(report):
            findings.append({"path": item.path, "kind": "literal_secret"})
    if findings or high_confidence:
        raise MemoryPromotionError(
            "Literal secret-like material must be replaced with ManagedSecret references",
            code="literal_secret_rejected",
        )


def _idempotency_key(*, asset_id: int, snapshot_id: int, destination_kind: str, target_id: int | None) -> str:
    seed = f"memory-promotion-v1:{asset_id}:{snapshot_id}:{destination_kind}:{target_id or 0}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _mark_promotion(
    promotion: ServerMemoryPromotion,
    *,
    status: str,
    result: dict[str, Any],
    revision: PlaybookRevision | None = None,
    draft_created: bool = False,
    validated: bool = False,
) -> None:
    now = timezone.now()
    bounded = _bounded_result(result)
    updates: dict[str, Any] = {
        "status": status,
        "validation_result": bounded,
        "completed_at": now,
        "updated_at": now,
    }
    if validated:
        updates["validated_at"] = now
    if revision is not None:
        updates["playbook_revision"] = revision
    if draft_created:
        updates["draft_created_at"] = now
    ServerMemoryPromotion.objects.filter(pk=promotion.pk).update(**updates)
    for key, value in updates.items():
        setattr(promotion, key, value)


def _bounded_result(result: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    if len(encoded) <= MAX_VALIDATION_RESULT_BYTES:
        return result
    return {
        "ok": bool(result.get("ok")),
        "code": str(result.get("code") or "validation_result_truncated")[:80],
        "truncated": True,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "size_bytes": len(encoded),
        "source": result.get("source") or {},
        "destination": result.get("destination") or {},
    }


def _compact_validation_result(validation) -> dict[str, Any]:
    issues = validation.issues if isinstance(validation.issues, list) else []
    issue_codes = sorted({str(item.get("code") or "unknown")[:80] for item in issues if isinstance(item, dict)})[:50]
    return {
        "id": validation.id,
        "status": str(validation.status)[:20],
        "issue_count": len(issues),
        "issue_codes": issue_codes,
        "runtime_fingerprint_hash": str(validation.runtime_fingerprint_hash or "")[:64],
        "target_signature": str(validation.target_signature or "")[:64],
    }


def _result_with_provenance(
    *,
    promotion: ServerMemoryPromotion,
    asset: ServerMemoryAsset,
    snapshot,
    playbook,
    ok: bool,
    code: str,
    revision: PlaybookRevision | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": ok,
        "code": code,
        "source": {
            "asset_id": asset.id,
            "snapshot_id": snapshot.id,
            "snapshot_content_hash": _snapshot_content_sha256(snapshot),
            "generation_log_id": promotion.generation_log_id,
        },
        "destination": {
            "kind": promotion.destination_kind,
            "playbook_id": getattr(playbook, "id", None),
            "revision_id": getattr(revision, "id", None),
            "revision_content_hash": getattr(revision, "content_hash", ""),
            "skill_slug": promotion.skill_slug,
            "published": False,
        },
    }
    if extra:
        result.update(extra)
    return result


def _snapshot_content_sha256(snapshot) -> str:
    return hashlib.sha256(str(snapshot.content or "").encode("utf-8")).hexdigest()
