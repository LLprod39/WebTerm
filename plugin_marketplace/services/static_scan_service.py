from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

BLOCKED_NAMES = {
    "install.sh",
    "postinstall.sh",
    "setup.py",
    "manage.py",
}
DEPENDENCY_MANIFEST_NAMES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
}
BLOCKED_SUFFIXES = (".py", ".pyc", ".pyd", ".ps1", ".bat", ".cmd", ".sh", ".exe", ".dll", ".so", ".dylib")
DYNAMIC_FRONTEND_BUNDLE_RENDERERS = {"javascript", "remote", "web_worker"}
SUSPICIOUS_MANIFEST_KEYS = {
    "install_script",
    "postinstall",
    "dependencies",
    "python_dependencies",
    "node_dependencies",
    "raw_html",
    "inline_script",
}


@dataclass(frozen=True)
class StaticScanFinding:
    code: str
    severity: str
    message: str
    path: str = ""

    def to_dict(self) -> dict[str, str]:
        payload = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.path:
            payload["path"] = self.path
        return payload


@dataclass(frozen=True)
class StaticScanResult:
    passed: bool
    findings: tuple[StaticScanFinding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "findings": [item.to_dict() for item in self.findings],
        }


def _safe_zip_name(name: str) -> bool:
    item = PurePosixPath(name)
    if item.is_absolute() or ".." in item.parts:
        return False
    return bool(item.parts) and not any(part.startswith("\\") for part in item.parts)


def _sandbox_code_entry_allowed(name: str) -> bool:
    path = PurePosixPath(name)
    lowered = str(path).lower()
    return lowered.startswith("backend/") and lowered.endswith(".py")


def _valid_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdefABCDEF" for char in value)


def _dynamic_frontend_bundle_findings(kind: str, index: int, item: dict[str, Any]) -> list[StaticScanFinding]:
    renderer = str(item.get("renderer") or "").strip().lower()
    if renderer not in DYNAMIC_FRONTEND_BUNDLE_RENDERERS:
        return []
    bundle_url = str(item.get("bundle_url") or item.get("src") or "").strip()
    bundle_sha256 = str(item.get("bundle_sha256") or item.get("sha256") or "").strip()
    parsed = urlparse(bundle_url)
    findings: list[StaticScanFinding] = []
    if parsed.scheme != "https" or not parsed.netloc:
        findings.append(
            StaticScanFinding(
                code="dynamic_frontend_bundle_url",
                severity="blocker",
                message=f"surfaces.{kind}[{index}] dynamic frontend bundle URL must be HTTPS.",
            )
        )
    if not _valid_sha256_hex(bundle_sha256):
        findings.append(
            StaticScanFinding(
                code="dynamic_frontend_bundle_integrity",
                severity="blocker",
                message=f"surfaces.{kind}[{index}] dynamic frontend bundle must declare a SHA-256 digest.",
            )
        )
    return findings


def scan_package_entries(entries: list[tuple[str, int]], *, allow_sandboxed_code: bool = False) -> StaticScanResult:
    findings: list[StaticScanFinding] = []
    for name, file_size in entries:
        path_name = PurePosixPath(name).name.lower()
        if not _safe_zip_name(name):
            findings.append(
                StaticScanFinding(
                    code="unsafe_path",
                    severity="blocker",
                    path=name,
                    message="Package entry path escapes the archive root.",
                )
            )
        if path_name in BLOCKED_NAMES or (path_name in DEPENDENCY_MANIFEST_NAMES and not allow_sandboxed_code) or (
            path_name.endswith(BLOCKED_SUFFIXES) and not (allow_sandboxed_code and _sandbox_code_entry_allowed(name))
        ):
            findings.append(
                StaticScanFinding(
                    code="executable_entry",
                    severity="blocker",
                    path=name,
                    message="Executable, dependency, or install file is not allowed in no-code plugin packages.",
                )
            )
        if file_size > 2 * 1024 * 1024:
            findings.append(
                StaticScanFinding(
                    code="large_entry",
                    severity="warning",
                    path=name,
                    message="Package entry is larger than the first-version review threshold.",
                )
            )
    return StaticScanResult(
        passed=not any(item.severity == "blocker" for item in findings),
        findings=tuple(findings),
    )


def scan_manifest(
    manifest: dict[str, Any],
    *,
    allow_sandboxed_code: bool = False,
    allow_dynamic_frontend_bundles: bool = False,
) -> StaticScanResult:
    findings: list[StaticScanFinding] = []
    for key in sorted(SUSPICIOUS_MANIFEST_KEYS.intersection(manifest.keys())):
        findings.append(
            StaticScanFinding(
                code="unsupported_manifest_capability",
                severity="blocker",
                message=f"Manifest key '{key}' is not allowed before sandboxed execution support exists.",
            )
        )

    surfaces = manifest.get("surfaces") if isinstance(manifest.get("surfaces"), dict) else {}
    for kind, items in surfaces.items():
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            renderer = str(item.get("renderer") or "").lower()
            if renderer in {"html", "javascript", "remote", "iframe_sandbox", "web_worker"} and not (
                (allow_sandboxed_code and renderer == "iframe_sandbox")
                or (
                    allow_sandboxed_code
                    and allow_dynamic_frontend_bundles
                    and renderer in DYNAMIC_FRONTEND_BUNDLE_RENDERERS
                )
            ):
                findings.append(
                    StaticScanFinding(
                        code="dynamic_frontend_renderer",
                        severity="blocker",
                        message=f"surfaces.{kind}[{index}] requests dynamic frontend rendering.",
                    )
                )
            if allow_sandboxed_code and allow_dynamic_frontend_bundles:
                findings.extend(_dynamic_frontend_bundle_findings(kind, index, item))
            executor_ref = str(item.get("executor_ref") or item.get("executor") or "")
            if executor_ref and not (
                executor_ref.startswith("plugin_marketplace.demo.")
                or (allow_sandboxed_code and executor_ref.startswith("sandbox:"))
            ):
                findings.append(
                    StaticScanFinding(
                        code="untrusted_executor_ref",
                        severity="blocker",
                        message=f"surfaces.{kind}[{index}] declares an executor outside the trusted demo namespace.",
                    )
                )

    return StaticScanResult(
        passed=not any(item.severity == "blocker" for item in findings),
        findings=tuple(findings),
    )


def combine_scan_results(*results: StaticScanResult) -> StaticScanResult:
    findings: list[StaticScanFinding] = []
    for result in results:
        findings.extend(result.findings)
    return StaticScanResult(
        passed=not any(item.severity == "blocker" for item in findings),
        findings=tuple(findings),
    )
