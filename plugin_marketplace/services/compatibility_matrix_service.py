from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from app.plugins.validation import PluginValidationError, validate_plugin_manifest
from plugin_marketplace.models import MarketplaceCatalogItem, PluginCompatibilityJob
from plugin_marketplace.services.catalog_service import SUPPORTED_PLUGIN_API_VERSIONS, compatibility_report
from plugin_marketplace.services.compatibility_sandbox_service import add_sandbox_compatibility_checks
from plugin_marketplace.services.static_scan_service import scan_manifest

COMPATIBILITY_JOB_ISOLATION_MODES = frozenset(
    {
        "in_process_no_code",
        "subprocess_no_code",
        "subprocess_sandbox",
    }
)


def normalize_compatibility_isolation_mode(value: str | None) -> str:
    mode = str(value or "in_process_no_code").strip() or "in_process_no_code"
    if mode not in COMPATIBILITY_JOB_ISOLATION_MODES:
        allowed = ", ".join(sorted(COMPATIBILITY_JOB_ISOLATION_MODES))
        raise ValueError(f"Unsupported compatibility isolation mode '{mode}'. Allowed values: {allowed}.")
    return mode


def compatibility_checks_for_item(item: MarketplaceCatalogItem) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    manifest = item.manifest or {}
    try:
        parsed = validate_plugin_manifest(manifest).to_dict(include_surfaces=True)
    except PluginValidationError as exc:
        parsed = manifest if isinstance(manifest, dict) else {}
        checks.append({"name": "manifest_schema", "ok": False, "errors": exc.errors})
    else:
        checks.append({"name": "manifest_schema", "ok": True, "errors": []})

    api_version = str(parsed.get("api_version") or "")
    checks.append(
        {
            "name": "plugin_api_version",
            "ok": api_version in SUPPORTED_PLUGIN_API_VERSIONS,
            "api_version": api_version,
            "supported_api_versions": sorted(SUPPORTED_PLUGIN_API_VERSIONS),
        }
    )
    scan = scan_manifest(
        parsed,
        allow_sandboxed_code=bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES", False)),
        allow_dynamic_frontend_bundles=bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES", False)),
    )
    checks.append({"name": "static_no_code_scan", "ok": scan.passed, "findings": scan.to_dict()["findings"]})
    catalog_report = compatibility_report(item)
    checks.append({"name": "catalog_policy", "ok": catalog_report["compatible"], "errors": catalog_report["errors"]})
    return {
        "catalog_item_id": item.id,
        "plugin_id": item.plugin_id,
        "version": item.version,
        "compatible": all(check["ok"] for check in checks),
        "checks": checks,
    }


def compatibility_job_payload(job: PluginCompatibilityJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "catalog_item_id": job.catalog_item_id,
        "plugin_id": job.plugin_id,
        "version": job.version,
        "status": job.status,
        "isolation_mode": job.isolation_mode,
        "checks": job.checks,
        "report": job.report,
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def compatibility_matrix_for_item(item: MarketplaceCatalogItem) -> dict[str, Any]:
    result = compatibility_checks_for_item(item)
    latest_job = item.compatibility_jobs.order_by("-created_at", "-id").first()
    if latest_job:
        result["job"] = compatibility_job_payload(latest_job)
    return result


def build_compatibility_matrix() -> list[dict[str, Any]]:
    items = MarketplaceCatalogItem.objects.select_related("source").order_by("plugin_id", "-updated_at")
    return [compatibility_matrix_for_item(item) for item in items]


def _compatibility_isolation_mode() -> str:
    return normalize_compatibility_isolation_mode(
        str(getattr(settings, "PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_ISOLATION_MODE", "in_process_no_code") or "")
    )


def _compatibility_timeout_seconds() -> int:
    return int(getattr(settings, "PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_TIMEOUT_SECONDS", 20) or 20)


def _run_checks_in_subprocess(item: MarketplaceCatalogItem) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(settings.BASE_DIR) / "manage.py"),
        "plugin_compatibility_check",
        "--catalog-item-id",
        str(item.id),
    ]
    completed = subprocess.run(
        command,
        cwd=str(Path(settings.BASE_DIR)),
        capture_output=True,
        check=False,
        text=True,
        timeout=_compatibility_timeout_seconds(),
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "Compatibility subprocess failed.")
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("Compatibility subprocess returned a non-object payload.")
    return payload


def _run_job_checks(item: MarketplaceCatalogItem, isolation_mode: str) -> dict[str, Any]:
    if isolation_mode == "subprocess_no_code":
        return _run_checks_in_subprocess(item)
    if isolation_mode == "subprocess_sandbox":
        return add_sandbox_compatibility_checks(item, compatibility_checks_for_item(item))
    return compatibility_checks_for_item(item)


@transaction.atomic
def run_compatibility_job(
    item: MarketplaceCatalogItem,
    *,
    isolation_mode: str | None = None,
) -> PluginCompatibilityJob:
    mode = normalize_compatibility_isolation_mode(isolation_mode) if isolation_mode is not None else _compatibility_isolation_mode()
    job = PluginCompatibilityJob.objects.create(
        catalog_item=item,
        plugin_id=item.plugin_id,
        version=item.version,
        status=PluginCompatibilityJob.STATUS_RUNNING,
        isolation_mode=mode,
        started_at=timezone.now(),
    )
    try:
        report = _run_job_checks(item, mode)
    except Exception as exc:  # noqa: BLE001 - compatibility jobs must persist failure reports.
        job.status = PluginCompatibilityJob.STATUS_ERROR
        job.error = str(exc)
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "error", "completed_at", "updated_at"])
        return job
    job.report = report
    job.checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    job.status = PluginCompatibilityJob.STATUS_PASSED if report.get("compatible") else PluginCompatibilityJob.STATUS_FAILED
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "checks", "report", "completed_at", "updated_at"])
    compatibility = item.compatibility if isinstance(item.compatibility, dict) else {}
    compatibility["last_matrix"] = report
    compatibility["last_job"] = compatibility_job_payload(job)
    item.compatibility = compatibility
    item.save(update_fields=["compatibility", "updated_at"])
    return job


@transaction.atomic
def run_compatibility_matrix_update() -> list[dict[str, Any]]:
    results = []
    for item in MarketplaceCatalogItem.objects.select_for_update().select_related("source").order_by("plugin_id", "-updated_at"):
        job = run_compatibility_job(item)
        result = dict(job.report or compatibility_checks_for_item(item))
        result["job"] = compatibility_job_payload(job)
        results.append(result)
    return results


def list_compatibility_jobs(limit: int = 50) -> list[dict[str, Any]]:
    jobs = PluginCompatibilityJob.objects.select_related("catalog_item").order_by("-created_at", "-id")[:limit]
    return [compatibility_job_payload(job) for job in jobs]


def compatibility_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    total = len(items)
    compatible = sum(1 for item in items if item.get("compatible"))
    return {
        "total": total,
        "compatible": compatible,
        "incompatible": total - compatible,
    }


def incompatible_compatibility_messages(items: list[dict[str, Any]]) -> list[str]:
    messages: list[str] = []
    for item in items:
        if item.get("compatible"):
            continue
        plugin_id = item.get("plugin_id") or "unknown"
        version = item.get("version") or "unknown"
        errors: list[str] = []
        for check in item.get("checks") or []:
            if isinstance(check, dict) and not check.get("ok"):
                errors.extend(str(error) for error in check.get("errors") or [])
        detail = "; ".join(errors) if errors else "incompatible"
        messages.append(f"{plugin_id}@{version}: {detail}")
    return messages
