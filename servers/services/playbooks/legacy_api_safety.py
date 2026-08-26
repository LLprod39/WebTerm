"""Typed safety facade for the legacy single-file playbook API.

The HTTP compatibility surface should not know how bundle, revision, and raw
source scanners are composed.  This module keeps that policy boundary cohesive
while preserving the existing error contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from servers.models_playbook_workspace import PlaybookRevision
from servers.services.playbooks.bundle_content import sanitize_preview_value
from servers.services.playbooks.revision_safety import (
    validate_legacy_playbook_safety,
    validate_revision_safety,
)
from servers.services.playbooks.source_guard import PlaybookSourceSafetyError, validate_ansible_source


class LegacySourceSafetyError(ValueError):
    """Stable, non-secret source failure for legacy API delivery."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details or {}


@dataclass(frozen=True)
class LegacySourceInspection:
    source_yaml: str
    content_hash: str
    compatibility: dict[str, Any]
    secret_findings: tuple[dict[str, str], ...]


def inspect_legacy_source(source_yaml: Any, *, path: str = "playbook.yml") -> LegacySourceInspection:
    try:
        result = validate_ansible_source(source_yaml, path=path)
    except PlaybookSourceSafetyError as exc:
        raise LegacySourceSafetyError(
            str(exc),
            code=exc.code,
            status_code=exc.status_code,
            details=exc.details,
        ) from exc
    return LegacySourceInspection(
        source_yaml=result.source_yaml,
        content_hash=result.content_hash,
        compatibility=result.compatibility,
        secret_findings=result.secret_findings,
    )


def sanitize_legacy_preview(value: Any) -> Any:
    return sanitize_preview_value(value)


def validate_legacy_playbook_egress(playbook: Any) -> None:
    if getattr(playbook, "published_revision_id", None):
        validate_revision_safety(playbook.published_revision)
    else:
        validate_legacy_playbook_safety(playbook)


def validate_legacy_revision_egress(revision: PlaybookRevision) -> None:
    validate_revision_safety(revision)
