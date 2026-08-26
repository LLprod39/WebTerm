"""Versioned progress state for PlaybookRun without a schema migration."""

from __future__ import annotations

from typing import Any

from app.core.redacted_logging import redacted_log_text
from app.egress_redaction import redact_egress_payload
from servers.models import PlaybookRun

PROGRESS_SCHEMA_VERSION = 2
PROGRESS_PHASES = {"queued", "preparing", "executing", "cancelling", "finished"}
TOTAL_KINDS = {"exact", "estimated", "unknown"}
_MISSING = object()


def redact_playbook_run_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Redact execution-controlled fields before they cross the DB boundary."""
    sanitized = dict(fields)
    for name in ("live_log", "error_message"):
        if name in sanitized:
            sanitized[name] = redacted_log_text(sanitized.get(name))
    for name in ("host_results", "summary", "progress"):
        if name not in sanitized:
            continue
        value, _report, _hashes = redact_egress_payload(sanitized.get(name))
        sanitized[name] = value
    return sanitized


def phase_for_run(*, status: str, cancel_requested: bool = False, preferred: str = "") -> str:
    if status in {
        PlaybookRun.STATUS_COMPLETED,
        PlaybookRun.STATUS_FAILED,
        PlaybookRun.STATUS_PARTIAL,
        PlaybookRun.STATUS_CANCELLED,
    }:
        return "finished"
    if cancel_requested:
        return "cancelling"
    if status == PlaybookRun.STATUS_RUNNING:
        return "executing"
    return preferred if preferred in {"queued", "preparing"} else "queued"


def total_kind_for_progress(progress: dict[str, Any]) -> str:
    explicit = str(progress.get("total_kind") or "")
    if explicit in TOTAL_KINDS:
        return explicit
    total = progress.get("tasks_total")
    if not isinstance(total, int) or isinstance(total, bool) or total <= 0:
        return "unknown"
    return "exact" if str(progress.get("engine") or "").lower() == "shell" else "estimated"


def _integer(value: Any, default: int = 0) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return default


def _suffix_prefix_overlap(previous: str, current: str) -> int:
    """Find retained overlap cheaply for bounded (<=160k) log windows."""
    if not previous or not current:
        return 0
    prefix = [0] * len(current)
    matched = 0
    for index in range(1, len(current)):
        while matched and current[index] != current[matched]:
            matched = prefix[matched - 1]
        if current[index] == current[matched]:
            matched += 1
        prefix[index] = matched
    matched = 0
    for character in previous[-len(current) :]:
        while matched and character != current[matched]:
            matched = prefix[matched - 1]
        if character == current[matched]:
            matched += 1
        if matched == len(current):
            # A full match is useful only when it reaches the previous suffix;
            # otherwise continue looking for the longest suffix match.
            matched = prefix[matched - 1]
    if previous.endswith(current):
        return len(current)
    return matched


def evolve_playbook_progress(
    previous: Any,
    incoming: Any = None,
    *,
    status: str,
    cancel_requested: bool = False,
    previous_log: str = "",
    current_log: object = _MISSING,
    preferred_phase: str = "",
) -> dict[str, Any]:
    """Merge one persisted state change and advance monotonic version/log cursors."""
    before = dict(previous) if isinstance(previous, dict) else {}
    merged = dict(before)
    if isinstance(incoming, dict):
        merged.update(incoming)

    merged["schema_version"] = PROGRESS_SCHEMA_VERSION
    merged["state_version"] = _integer(before.get("state_version")) + 1
    preferred = str(preferred_phase or merged.get("phase") or "")
    merged["phase"] = phase_for_run(
        status=status,
        cancel_requested=cancel_requested,
        preferred=preferred,
    )
    merged["total_kind"] = total_kind_for_progress(merged)

    old_text = str(previous_log or "")
    old_start = _integer(before.get("log_start_cursor"))
    old_end = max(_integer(before.get("log_end_cursor"), old_start + len(old_text)), old_start + len(old_text))
    new_start = old_start
    new_end = old_end
    truncated = bool(before.get("log_truncated"))

    if current_log is not _MISSING:
        new_text = str(current_log or "")
        if new_text == old_text:
            pass
        elif old_text and new_text.startswith(old_text):
            new_end = old_end + len(new_text) - len(old_text)
        elif not old_text:
            new_start = old_end
            new_end = new_start + len(new_text)
        else:
            overlap = _suffix_prefix_overlap(old_text, new_text)
            new_start = old_end - overlap
            new_end = new_start + len(new_text)
            truncated = True

    merged["log_start_cursor"] = new_start
    merged["log_end_cursor"] = new_end
    merged["log_truncated"] = bool(truncated or new_start > 0)
    return merged


def mark_playbook_progress(
    run: PlaybookRun,
    *,
    phase: str = "",
    status: str | None = None,
    cancel_requested: bool | None = None,
) -> None:
    """Persist a lifecycle-only progress change on an already locked run."""
    run.progress = evolve_playbook_progress(
        run.progress,
        status=status or run.status,
        cancel_requested=run.cancel_requested if cancel_requested is None else cancel_requested,
        previous_log=run.live_log,
        preferred_phase=phase,
    )
    run.save(update_fields=["progress"])
