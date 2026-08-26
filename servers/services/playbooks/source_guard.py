"""Fail-closed validation for editable Ansible YAML sources."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from servers.services.playbook_compatibility_analysis import analyze_playbook_compatibility
from servers.services.playbooks.bundle_archive import BundleFile, BundleLimits, BundleValidationError
from servers.services.playbooks.bundle_content import safe_yaml_load, sanitize_preview_value, scan_bundle_secrets
from servers.services.playbooks.content import MAX_YAML_BYTES, PlaybookContentError

_BLOCKED_SECRET_FINDINGS = frozenset(
    {
        "credential_pattern",
        "encrypted_vault",
        "private_key",
        "sensitive_assignment",
        "sensitive_value",
        "suspicious_filename",
    }
)


class PlaybookSourceSafetyError(PlaybookContentError):
    """Stable validation failure that is safe to return to an API caller."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "playbook_source_invalid",
        status_code: int = 422,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details or {}


@dataclass(frozen=True)
class SourceSafetyResult:
    source_yaml: str
    content_hash: str
    document: Any
    compatibility: dict[str, Any]
    secret_findings: tuple[dict[str, str], ...]


def validate_ansible_source(source_yaml: Any, *, path: str = "playbook.yml") -> SourceSafetyResult:
    """Validate exact UTF-8 bytes without truncating or echoing unsafe values."""

    source = source_yaml if isinstance(source_yaml, str) else str(source_yaml or "")
    try:
        encoded = source.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PlaybookSourceSafetyError(
            "Ansible YAML must be valid UTF-8",
            code="playbook_source_encoding",
            status_code=400,
        ) from exc
    if len(encoded) > MAX_YAML_BYTES:
        raise PlaybookSourceSafetyError(
            f"YAML cannot exceed {MAX_YAML_BYTES} UTF-8 bytes",
            code="playbook_source_size_limit",
            status_code=413,
            details={"max_bytes": MAX_YAML_BYTES, "actual_bytes": len(encoded)},
        )
    if not source.strip():
        raise PlaybookSourceSafetyError("Ansible YAML cannot be empty", code="playbook_source_empty", status_code=400)

    limits = BundleLimits.from_settings()
    try:
        document = safe_yaml_load(path, encoded, limits)
    except UnicodeDecodeError as exc:  # Defensive: source is already a Python string.
        raise PlaybookSourceSafetyError(
            "Ansible YAML must be valid UTF-8", code="playbook_source_encoding", status_code=400
        ) from exc
    except BundleValidationError as exc:
        raise PlaybookSourceSafetyError(
            str(exc), code=exc.code, status_code=exc.status_code, details=exc.details
        ) from exc

    compatibility = analyze_playbook_compatibility(source)
    invalid_yaml = [
        item
        for item in compatibility.get("issues") or []
        if isinstance(item, dict) and item.get("code") == "invalid_yaml"
    ]
    if invalid_yaml:
        raise PlaybookSourceSafetyError(
            "YAML is not a supported Ansible playbook",
            code="invalid_ansible_playbook",
            details={"issues": invalid_yaml[:20]},
        )

    controller_findings = [
        item
        for item in compatibility.get("issues") or []
        if isinstance(item, dict) and str(item.get("code") or "").startswith("controller_")
    ]
    if controller_findings:
        raise PlaybookSourceSafetyError(
            "Playbook contains controller-side operations that are not allowed",
            code="controller_policy_violation",
            details={"issues": sanitize_preview_value(controller_findings[:20])},
        )

    item = BundleFile(
        path=path,
        content=encoded,
        sha256=hashlib.sha256(encoded).hexdigest(),
        is_text=True,
    )
    yaml_documents = {path: document}
    secret_findings = tuple(
        finding
        for finding in scan_bundle_secrets([item], yaml_documents, {})
        if finding.get("kind") in _BLOCKED_SECRET_FINDINGS
    )
    literal_secret_findings = [
        item
        for item in compatibility.get("issues") or []
        if isinstance(item, dict) and item.get("code") == "literal_secret"
    ]
    if secret_findings or literal_secret_findings:
        details: dict[str, Any] = {"findings": list(secret_findings)[:20]}
        if literal_secret_findings:
            details["issues"] = literal_secret_findings[:20]
        raise PlaybookSourceSafetyError(
            "Playbook contains literal secret material; use managed secret bindings",
            code="secret_material_detected",
            details=details,
        )

    return SourceSafetyResult(
        source_yaml=source,
        content_hash=item.sha256,
        document=document,
        compatibility=compatibility,
        secret_findings=secret_findings,
    )
