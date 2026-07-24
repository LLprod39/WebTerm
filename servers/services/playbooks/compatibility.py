"""Revision-scoped compatibility facts shared by APIs and validation."""

from __future__ import annotations

from typing import Any

from servers.services.playbook_compatibility_analysis import (
    COMPATIBILITY_ANALYZER_VERSION,
    analyze_playbook_compatibility,
)


def compatibility_for_revision(
    revision,
    *,
    bindings: dict[str, Any] | None = None,
    target_servers: list[Any] | None = None,
) -> dict[str, Any]:
    """Return compatibility derived from this exact immutable revision."""

    if revision.content_format == "ansible_yaml":
        report = analyze_playbook_compatibility(
            revision.source_yaml,
            bindings=bindings,
            target_servers=target_servers,
        )
    else:
        has_tasks = isinstance(revision.tasks, list) and any(
            isinstance(item, dict) and str(item.get("command") or "").strip() for item in revision.tasks
        )
        report = {
            "analyzer_version": COMPATIBILITY_ANALYZER_VERSION,
            "status": "ready" if has_tasks else "blocked",
            "ready": has_tasks,
            "host_selectors": [],
            "host_patterns": [],
            "missing_bindings": [],
            "required_variables": [],
            "dependencies": {"roles": [], "collections": [], "assets": []},
            "issues": (
                []
                if has_tasks
                else [
                    {
                        "code": "empty_runbook",
                        "severity": "error",
                        "message": "Runbook has no executable tasks",
                        "path": "playbook",
                    }
                ]
            ),
            "semantic_hash": revision.content_hash,
            "targets_count": len(target_servers or []),
        }
    return {
        **report,
        "revision_id": revision.id,
        "content_hash": revision.content_hash,
        "content_format": revision.content_format,
    }
