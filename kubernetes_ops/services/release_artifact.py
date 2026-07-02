from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from kubernetes_ops.services.release_contract import RELEASE_EVIDENCE_SCHEMA_VERSION


def build_kubernetes_release_evidence_artifact_report(*, require_ready: bool) -> dict[str, Any]:
    path = Path(settings.BASE_DIR) / "artifacts" / "kubernetes_ops_release_evidence.json"
    max_age_seconds = int(getattr(settings, "KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS", 86400) or 86400)
    approval_ref = str(getattr(settings, "KUBERNETES_OPS_PRODUCTION_APPROVAL_REF", "") or "").strip()
    if not path.exists():
        return _report(
            status="missing" if require_ready else "manual",
            path=path,
            max_age_seconds=max_age_seconds,
            detail="Release evidence artifact is required before sidebar enablement." if require_ready else "Release evidence artifact is not required until sidebar enablement.",
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _report(status="missing" if require_ready else "manual", path=path, max_age_seconds=max_age_seconds, detail=f"Release evidence artifact cannot be read: {exc}.")

    generated_at = str(payload.get("generated_at") or "")
    generated_dt = parse_datetime(generated_at)
    if generated_dt is not None and timezone.is_naive(generated_dt):
        generated_dt = timezone.make_aware(generated_dt, timezone=timezone.utc)
    age_seconds = int((timezone.now() - generated_dt).total_seconds()) if generated_dt is not None else None
    release_scope = payload.get("release_scope") if isinstance(payload.get("release_scope"), dict) else {}
    artifact_safety = payload.get("artifact_safety") if isinstance(payload.get("artifact_safety"), dict) else {}
    errors: list[str] = []
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != RELEASE_EVIDENCE_SCHEMA_VERSION:
        errors.append(f"schema_version is {schema_version or 'missing'}; expected {RELEASE_EVIDENCE_SCHEMA_VERSION}")
    if generated_dt is None:
        errors.append("generated_at is missing or invalid")
    elif age_seconds is not None and age_seconds > max_age_seconds:
        errors.append(f"artifact is stale: age_seconds={age_seconds} max_age_seconds={max_age_seconds}")
    if artifact_safety.get("success") is not True:
        errors.append(f"artifact_safety is {artifact_safety.get('status') or 'missing'}")
    if require_ready:
        if not payload.get("production_ready"):
            errors.append("production_ready is not true")
        if release_scope.get("status") != "ready":
            errors.append(f"release_scope is {release_scope.get('status') or 'missing'}")
        if approval_ref and str(release_scope.get("approval_ref") or "").strip() != approval_ref:
            errors.append("approval ref does not match current KUBERNETES_OPS_PRODUCTION_APPROVAL_REF")

    status = "ready" if not errors else ("missing" if require_ready else "manual")
    if status == "ready" and require_ready:
        detail = "Release evidence artifact is fresh and production-ready."
    elif status == "ready":
        detail = "Release evidence artifact is fresh; production readiness is enforced only during sidebar enablement."
    else:
        detail = "Release evidence artifact is not sidebar-ready: " + "; ".join(errors)
    return _report(
        status=status,
        path=path,
        max_age_seconds=max_age_seconds,
        detail=detail,
        payload=payload,
        generated_at=generated_at,
        age_seconds=age_seconds,
        errors=errors,
    )


def _report(
    *,
    status: str,
    path: Path,
    max_age_seconds: int,
    detail: str,
    payload: dict[str, Any] | None = None,
    generated_at: str = "",
    age_seconds: int | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    release_scope = payload.get("release_scope") if isinstance((payload or {}).get("release_scope"), dict) else {}
    artifact_safety = payload.get("artifact_safety") if isinstance((payload or {}).get("artifact_safety"), dict) else {}
    return {
        "status": status,
        "detail": detail,
        "path": str(path),
        "generated_at": generated_at,
        "age_seconds": age_seconds,
        "max_age_seconds": max_age_seconds,
        "production_ready": bool((payload or {}).get("production_ready")),
        "ready_for_sidebar": bool((payload or {}).get("ready_for_sidebar")),
        "schema_version": str((payload or {}).get("schema_version") or ""),
        "expected_schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
        "release_scope_status": str(release_scope.get("status") or ""),
        "release_scope_approval_ref": str(release_scope.get("approval_ref") or ""),
        "artifact_safety_status": str(artifact_safety.get("status") or ""),
        "artifact_safety_issue_count": int(artifact_safety.get("issue_count") or 0),
        "blockers": list((payload or {}).get("blockers") or []),
        "errors": errors or [],
    }
