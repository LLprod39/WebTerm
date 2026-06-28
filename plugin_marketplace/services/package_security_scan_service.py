from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.db import transaction

from app.plugins.validation import PluginValidationError, validate_plugin_manifest
from plugin_marketplace.models import PluginPackage
from plugin_marketplace.services.package_attestation_service import append_package_attestation
from plugin_marketplace.services.signing_service import canonical_manifest_hash, package_signature_status
from plugin_marketplace.services.sandbox_policy_service import sandbox_policy_for_package
from plugin_marketplace.services.static_scan_service import scan_manifest

SECURITY_SCAN_PROVIDER_LOCAL = "local_static"
SECURITY_SCAN_PROVIDER_EXTERNAL = "external"
DEFAULT_BLOCK_SEVERITIES = {"critical", "high"}
DEFAULT_PASS_STATUSES = {"clean", "ok", "pass", "passed", "success"}


def _security_scan_provider() -> str:
    provider = str(getattr(settings, "PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER", SECURITY_SCAN_PROVIDER_LOCAL) or "").strip()
    return provider or SECURITY_SCAN_PROVIDER_LOCAL


def _external_auth_headers() -> dict[str, str]:
    token = str(getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_AUTH_TOKEN", "") or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _configured_block_severities() -> set[str]:
    configured = getattr(settings, "PLUGIN_MARKETPLACE_SECURITY_SCAN_BLOCK_SEVERITIES", None)
    if configured is None:
        return set(DEFAULT_BLOCK_SEVERITIES)
    if isinstance(configured, str):
        configured = configured.split(",")
    return {str(item or "").strip().lower() for item in configured if str(item or "").strip()}


def _configured_pass_statuses() -> set[str]:
    configured = getattr(settings, "PLUGIN_MARKETPLACE_SECURITY_SCAN_PASS_STATUSES", None)
    if configured is None:
        return set(DEFAULT_PASS_STATUSES)
    if isinstance(configured, str):
        configured = configured.split(",")
    return {str(item or "").strip().lower() for item in configured if str(item or "").strip()}


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    timeout = int(getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_TIMEOUT_SECONDS", 20) or 20)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", **_external_auth_headers()},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("External security scanner returned a non-object response.")
    return parsed


def _finding_severity(finding: Any) -> str:
    if not isinstance(finding, dict):
        return ""
    return str(finding.get("severity") or finding.get("level") or finding.get("risk") or "").strip().lower()


def _blocking_findings(findings: list[Any], block_severities: set[str]) -> list[dict[str, Any]]:
    return [finding for finding in findings if isinstance(finding, dict) and _finding_severity(finding) in block_severities]


def _external_scan_passed(response: dict[str, Any], findings: list[Any], blocking_findings: list[dict[str, Any]]) -> bool:
    raw_passed = response.get("passed")
    if isinstance(raw_passed, bool):
        provider_passed = raw_passed
    else:
        raw_status = str(response.get("status") or response.get("result") or "").strip().lower()
        if not raw_status:
            return False
        provider_passed = raw_status in _configured_pass_statuses()
    return bool(provider_passed) and not blocking_findings


def _scan_payload(package: PluginPackage) -> dict[str, Any]:
    manifest = package.manifest if isinstance(package.manifest, dict) else {}
    return {
        "plugin_id": package.plugin_id,
        "version": package.version,
        "package_hash": package.package_hash,
        "manifest_hash": canonical_manifest_hash(manifest),
        "signature_status": package_signature_status(package),
        "manifest": manifest,
        "sbom": package.sbom if isinstance(package.sbom, dict) else {},
        "dependency_scan": package.dependency_scan if isinstance(package.dependency_scan, dict) else {},
        "provenance": package.provenance if isinstance(package.provenance, dict) else {},
    }


def _local_security_report(package: PluginPackage) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    manifest = package.manifest if isinstance(package.manifest, dict) else {}
    try:
        parsed = validate_plugin_manifest(manifest).to_dict(include_surfaces=True)
    except PluginValidationError as exc:
        parsed = manifest
        checks.append({"name": "manifest_schema", "ok": False, "errors": exc.errors})
    else:
        checks.append({"name": "manifest_schema", "ok": True, "errors": []})
    static_scan = scan_manifest(
        parsed,
        allow_sandboxed_code=bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES", False)),
        allow_dynamic_frontend_bundles=bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES", False)),
    )
    dependency_scan = package.dependency_scan if isinstance(package.dependency_scan, dict) else {}
    checks.append({"name": "static_no_code_scan", "ok": static_scan.passed, "findings": static_scan.to_dict()["findings"]})
    checks.append(
        {
            "name": "dependency_manifest_blockers",
            "ok": bool(dependency_scan.get("passed", True)),
            "blockers": dependency_scan.get("blockers", []),
            "summary": dependency_scan.get("summary", {}),
        }
    )
    checks.append({"name": "sbom_present", "ok": bool(package.sbom), "summary": (package.sbom or {}).get("summary", {})})
    sandbox_policy = sandbox_policy_for_package(package)
    checks.append({"name": "sandbox_policy", "ok": bool(sandbox_policy.get("allowed", False)), "policy": sandbox_policy})
    return {
        "provider": SECURITY_SCAN_PROVIDER_LOCAL,
        "scanner": "webtrerm-static-sca",
        "passed": all(check["ok"] for check in checks),
        "checks": checks,
        "findings": static_scan.to_dict()["findings"],
    }


def _external_security_report(package: PluginPackage) -> dict[str, Any]:
    endpoint = str(getattr(settings, "PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_ENDPOINT", "") or "").strip()
    if not endpoint:
        raise ValueError("External security scanner endpoint is not configured.")
    try:
        response = _post_json(endpoint, _scan_payload(package))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ValueError(f"External security scanner failed: {exc}") from exc
    findings = response.get("findings") if isinstance(response.get("findings"), list) else []
    block_severities = _configured_block_severities()
    blocked = _blocking_findings(findings, block_severities)
    raw_status = str(response.get("status") or "")
    raw_result = str(response.get("result") or "")
    verdict_present = isinstance(response.get("passed"), bool) or bool(raw_status.strip() or raw_result.strip())
    return {
        "provider": SECURITY_SCAN_PROVIDER_EXTERNAL,
        "scanner": str(response.get("scanner") or "external"),
        "passed": _external_scan_passed(response, findings, blocked),
        "findings": findings,
        "blocked_findings": blocked,
        "block_severities": sorted(block_severities),
        "summary": response.get("summary") if isinstance(response.get("summary"), dict) else {},
        "raw_status": raw_status,
        "raw_result": raw_result,
        "verdict_present": verdict_present,
    }


@transaction.atomic
def run_package_security_scan(package_id: int, *, actor=None, request=None) -> PluginPackage:
    package = PluginPackage.objects.select_for_update().get(id=package_id)
    provider = _security_scan_provider()
    if provider == SECURITY_SCAN_PROVIDER_EXTERNAL:
        report = _external_security_report(package)
    else:
        report = _local_security_report(package)
    status = "passed" if report.get("passed") else "failed"
    append_package_attestation(
        package,
        kind="security_scan",
        status=status,
        report=report,
        actor=actor,
        request=request,
    )
    package.refresh_from_db()
    return package
