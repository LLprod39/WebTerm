from __future__ import annotations

import io
import json
import zipfile
from pathlib import PurePosixPath
from typing import Any

from django.conf import settings

from plugin_marketplace.models import MarketplaceCatalogItem, PluginPackage
from plugin_marketplace.services.backend_sandbox_runner_service import execute_sandbox_package
from plugin_marketplace.services.package_retention_service import PackageRetentionError, read_retained_package_bytes

MANIFEST_NAME = "webtrerm.plugin.json"


def _sandbox_executor_refs(manifest: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    surfaces = manifest.get("surfaces") if isinstance(manifest.get("surfaces"), dict) else {}
    for items in surfaces.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            ref = str(item.get("executor_ref") or item.get("executor") or "").strip()
            if ref.startswith("sandbox:") and ref not in refs:
                refs.append(ref)
    actions = manifest.get("actions") if isinstance(manifest.get("actions"), list) else []
    for item in actions:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("executor_ref") or "").strip()
        if ref.startswith("sandbox:") and ref not in refs:
            refs.append(ref)
    return refs


def _compatibility_test_cases(manifest: dict[str, Any], executor_refs: list[str]) -> list[dict[str, Any]]:
    raw_cases = manifest.get("compatibility_tests")
    if not isinstance(raw_cases, list):
        raw_cases = (
            (manifest.get("testing") or {}).get("compatibility") if isinstance(manifest.get("testing"), dict) else []
        )
    cases = []
    for index, item in enumerate(raw_cases if isinstance(raw_cases, list) else []):
        if not isinstance(item, dict):
            continue
        ref = str(item.get("executor_ref") or item.get("executor") or "").strip()
        if not ref.startswith("sandbox:"):
            continue
        cases.append(
            {
                "id": str(item.get("id") or f"case-{index + 1}"),
                "executor_ref": ref,
                "payload": item.get("payload")
                if isinstance(item.get("payload"), dict)
                else {"surface": "compatibility_job", "arguments": {}},
                "expect": item.get("expect") if isinstance(item.get("expect"), dict) else {},
            }
        )
    return cases


def _retained_package_manifest(package_bytes: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
            names = [
                info.filename
                for info in archive.infolist()
                if not info.is_dir() and PurePosixPath(info.filename).name == MANIFEST_NAME
            ]
            manifest_name = MANIFEST_NAME if MANIFEST_NAME in names else names[0]
            manifest = json.loads(archive.read(manifest_name).decode("utf-8"))
    except (IndexError, KeyError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile):
        return {}
    return manifest if isinstance(manifest, dict) else {}


def _sandbox_enabled() -> bool:
    return bool(getattr(settings, "PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES", False)) and bool(
        getattr(settings, "PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED", False)
    )


def _retained_package_for_item(item: MarketplaceCatalogItem) -> PluginPackage | None:
    return (
        PluginPackage.objects.filter(plugin_id=item.plugin_id, version=item.version)
        .exclude(provenance={})
        .order_by("-updated_at", "-id")
        .first()
    )


def _run_smoke_worker(package_bytes: bytes, executor_ref: str) -> dict[str, Any]:
    return execute_sandbox_package(
        package_bytes=package_bytes,
        executor_ref=executor_ref,
        payload={"surface": "compatibility_job", "arguments": {}},
        smoke_only=True,
        timeout_seconds=int(getattr(settings, "PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_TIMEOUT_SECONDS", 20) or 20),
    )


def _run_test_case(package_bytes: bytes, test_case: dict[str, Any]) -> dict[str, Any]:
    return execute_sandbox_package(
        package_bytes=package_bytes,
        executor_ref=str(test_case["executor_ref"]),
        payload=test_case["payload"],
        smoke_only=False,
        timeout_seconds=int(getattr(settings, "PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_TIMEOUT_SECONDS", 20) or 20),
    )


def _value_at_path(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _expectation_passed(result: dict[str, Any], expect: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    checks = []
    for path, expected in expect.items():
        actual = _value_at_path(result, str(path))
        checks.append({"path": str(path), "expected": expected, "actual": actual, "ok": actual == expected})
    return all(check["ok"] for check in checks), checks


def add_sandbox_compatibility_checks(item: MarketplaceCatalogItem, report: dict[str, Any]) -> dict[str, Any]:
    checks = list(report.get("checks") if isinstance(report.get("checks"), list) else [])
    manifest = item.manifest if isinstance(item.manifest, dict) else {}
    refs = _sandbox_executor_refs(manifest)
    if not refs:
        checks.append(
            {
                "name": "sandbox_executor_smoke",
                "ok": True,
                "skipped": True,
                "reason": "No sandbox executor refs declared.",
            }
        )
    elif not _sandbox_enabled():
        checks.append(
            {
                "name": "sandbox_executor_smoke",
                "ok": False,
                "executor_refs": refs,
                "error": "Sandbox compatibility mode is not enabled.",
            }
        )
    else:
        package = _retained_package_for_item(item)
        if package is None:
            checks.append(
                {
                    "name": "sandbox_executor_smoke",
                    "ok": False,
                    "executor_refs": refs,
                    "error": "Retained plugin package was not found.",
                }
            )
        else:
            try:
                retention = (package.provenance or {}).get("retention") if isinstance(package.provenance, dict) else {}
                package_bytes = read_retained_package_bytes(retention if isinstance(retention, dict) else {})
            except PackageRetentionError as exc:
                checks.append({"name": "sandbox_executor_smoke", "ok": False, "executor_refs": refs, "error": str(exc)})
            else:
                retained_manifest = _retained_package_manifest(package_bytes)
                test_cases = _compatibility_test_cases(retained_manifest, refs)
                for test_case in test_cases:
                    if test_case["executor_ref"] not in refs:
                        refs.append(test_case["executor_ref"])
                results = [{"executor_ref": ref, "result": _run_smoke_worker(package_bytes, ref)} for ref in refs]
                checks.append(
                    {
                        "name": "sandbox_executor_smoke",
                        "ok": all(item["result"].get("success") for item in results),
                        "executor_refs": refs,
                        "results": results,
                    }
                )
                if test_cases:
                    case_results = []
                    for test_case in test_cases:
                        result = _run_test_case(package_bytes, test_case)
                        expectations_ok, expectation_checks = _expectation_passed(result, test_case["expect"])
                        case_results.append(
                            {
                                "id": test_case["id"],
                                "executor_ref": test_case["executor_ref"],
                                "result": result,
                                "expectations": expectation_checks,
                                "ok": bool(result.get("success")) and expectations_ok,
                            }
                        )
                    checks.append(
                        {
                            "name": "sandbox_compatibility_tests",
                            "ok": all(case["ok"] for case in case_results),
                            "cases": case_results,
                        }
                    )
    updated = dict(report)
    updated["checks"] = checks
    updated["compatible"] = all(check.get("ok") for check in checks)
    return updated
