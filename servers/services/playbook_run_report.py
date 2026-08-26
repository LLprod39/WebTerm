"""Public, redacted report projection for PlaybookRun."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.utils import timezone

from app.core.redacted_logging import redacted_log_text
from app.egress_redaction import redact_egress_payload
from servers.models import PlaybookRun, PlaybookRunDispatch
from servers.services.playbook_progress_state import phase_for_run, total_kind_for_progress

REPORT_SCHEMA_VERSION = 2
TERMINAL_STATUSES = {
    PlaybookRun.STATUS_COMPLETED,
    PlaybookRun.STATUS_FAILED,
    PlaybookRun.STATUS_PARTIAL,
    PlaybookRun.STATUS_CANCELLED,
}
SAFE_OPTION_KEYS = (
    "engine",
    "dry_run",
    "concurrency",
    "become",
    "tags",
    "skip_tags",
    "limit",
    "rerun_of",
)
FAILED_HOST_STATUSES = {"error", "failed", "partial", "unreachable"}
FAILED_TASK_STATUSES = {"error", "failed", "unreachable"}


def _canonical_execution_status(value: Any) -> str:
    status = str(value or "pending").lower()
    if status in {"success", "completed", "ok"}:
        return "ok"
    if status in {"error", "failure", "failed", "partial"}:
        return "failed"
    if status in {"changed", "unreachable", "skipped", "running", "pending"}:
        return status
    if status in {"cancelled", "canceled"}:
        return "cancelled"
    return "pending"


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _duration_ms(run: PlaybookRun) -> int:
    if run.started_at is None:
        return 0
    end = run.finished_at or timezone.now()
    return max(int((end - run.started_at).total_seconds() * 1000), 0)


def _non_negative_int(value: Any, default: int = 0) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return default


def _public_payload(value: Any) -> Any:
    redacted, _report, _hashes = redact_egress_payload(value)
    return redacted


def safe_run_options(run: PlaybookRun) -> dict[str, Any]:
    raw = run.options if isinstance(run.options, dict) else {}
    return _public_payload({key: raw[key] for key in SAFE_OPTION_KEYS if key in raw})


def _dispatch_for_run(run: PlaybookRun) -> PlaybookRunDispatch | None:
    try:
        return run.dispatch
    except PlaybookRunDispatch.DoesNotExist:
        return None


def public_dispatch(dispatch: PlaybookRunDispatch | None) -> dict[str, Any] | None:
    if dispatch is None:
        return None
    stale = bool(
        dispatch.status == PlaybookRunDispatch.STATUS_CLAIMED
        and dispatch.lease_expires_at
        and dispatch.lease_expires_at <= timezone.now()
    )
    return {
        "status": dispatch.status,
        "queued_at": _iso(dispatch.queued_at),
        "claimed_at": _iso(dispatch.claimed_at),
        "completed_at": _iso(dispatch.completed_at),
        "attempt_count": int(dispatch.attempt_count or 0),
        "heartbeat_stale": stale,
        "mutation_safe_to_retry": bool(dispatch.mutation_safe_to_retry),
    }


def progress_snapshot(run: PlaybookRun, *, dispatch: PlaybookRunDispatch | None = None) -> dict[str, Any]:
    raw = dict(run.progress) if isinstance(run.progress, dict) else {}
    preferred_phase = str(raw.get("phase") or "")
    if run.status == PlaybookRun.STATUS_PENDING and dispatch is not None:
        if dispatch.status == PlaybookRunDispatch.STATUS_CLAIMED:
            preferred_phase = "preparing"
        elif dispatch.status == PlaybookRunDispatch.STATUS_QUEUED:
            preferred_phase = "queued"
    phase = phase_for_run(
        status=run.status,
        cancel_requested=bool(run.cancel_requested),
        preferred=preferred_phase,
    )
    total_kind = total_kind_for_progress(raw)
    total = raw.get("tasks_total")
    total = _non_negative_int(total) if total is not None else None
    if total == 0:
        total = None
    if total_kind == "exact":
        completed = _non_negative_int(raw.get("tasks_done"))
    elif total_kind == "estimated":
        completed = _non_negative_int(raw.get("task_number"))
    else:
        completed = None
    percent: int | None = None
    if total_kind == "exact" and total:
        percent = min(round((_non_negative_int(completed) / total) * 100), 100)
    start_cursor = _non_negative_int(raw.get("log_start_cursor"))
    end_cursor = max(
        _non_negative_int(raw.get("log_end_cursor"), start_cursor + len(run.live_log or "")),
        start_cursor + len(run.live_log or ""),
    )
    return {
        "state_version": _non_negative_int(raw.get("state_version")),
        "phase": phase,
        "total_kind": total_kind,
        "completed": completed,
        "total": total,
        "percent": percent,
        "indeterminate": total_kind != "exact",
        "engine": str(raw.get("engine") or (run.options or {}).get("engine") or ""),
        "play": redacted_log_text(raw.get("play"), limit=500),
        "task": redacted_log_text(raw.get("task"), limit=1_000),
        "task_number": _non_negative_int(raw.get("task_number")) or None,
        "hosts_seen": _non_negative_int(raw.get("hosts_seen")),
        "hosts_total": _non_negative_int(raw.get("hosts_total")),
        "counts": _public_payload(raw.get("counts") if isinstance(raw.get("counts"), dict) else {}),
        "is_terminal": run.status in TERMINAL_STATUSES,
        "log_start_cursor": start_cursor,
        "log_end_cursor": end_cursor,
        "log_truncated": bool(raw.get("log_truncated") or start_cursor > 0),
    }


def _task_counts(tasks: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "total": len(tasks),
        "ok": 0,
        "changed": 0,
        "failed": 0,
        "unreachable": 0,
        "skipped": 0,
        "cancelled": 0,
        "running": 0,
        "pending": 0,
    }
    for task in tasks:
        status = str(task.get("status") or "pending").lower()
        if status in {"success", "completed", "ok"}:
            counts["ok"] += 1
        elif status == "changed":
            counts["changed"] += 1
        elif status in {"error", "failed"}:
            counts["failed"] += 1
        elif status == "unreachable":
            counts["unreachable"] += 1
        elif status == "skipped":
            counts["skipped"] += 1
        elif status in {"cancelled", "canceled"}:
            counts["cancelled"] += 1
        elif status == "running":
            counts["running"] += 1
        else:
            counts["pending"] += 1
    return counts


def host_summary(run: PlaybookRun, host: dict[str, Any]) -> dict[str, Any]:
    tasks = [item for item in (host.get("task_results") or []) if isinstance(item, dict)]
    first_failure = next((item for item in tasks if str(item.get("status") or "") in FAILED_TASK_STATUSES), None)
    server_id = _non_negative_int(host.get("server_id")) or None
    return _public_payload(
        {
            "server_id": server_id,
            "server_name": str(host.get("server_name") or (f"Server #{server_id}" if server_id else "Host")),
            "host": str(host.get("host") or ""),
            "status": _canonical_execution_status(host.get("status")),
            "task_counts": _task_counts(tasks),
            "first_failure": (
                {
                    "task_id": str(first_failure.get("task_id") or ""),
                    "task_name": str(first_failure.get("description") or first_failure.get("command") or "Task"),
                    "message": redacted_log_text(first_failure.get("output"), limit=2_000),
                }
                if first_failure
                else None
            ),
            "detail_url": (f"/servers/api/playbooks/runs/{run.id}/hosts/{server_id}/" if server_id is not None else ""),
        }
    )


def public_host_detail(run: PlaybookRun, host: dict[str, Any]) -> dict[str, Any]:
    compact = host_summary(run, host)
    tasks = []
    for item in host.get("task_results") or []:
        if not isinstance(item, dict):
            continue
        tasks.append(
            {
                "task_id": str(item.get("task_id") or ""),
                "name": str(item.get("description") or item.get("command") or "Task"),
                "command": str(item.get("command") or ""),
                "description": str(item.get("description") or ""),
                "status": _canonical_execution_status(item.get("status")),
                "exit_code": item.get("exit_code") if isinstance(item.get("exit_code"), int) else None,
                "output": redacted_log_text(item.get("output"), limit=50_000),
            }
        )
    return _public_payload({**compact, "tasks": tasks})


def failed_host_ids(run: PlaybookRun) -> list[int]:
    result: list[int] = []
    for host in run.host_results if isinstance(run.host_results, list) else []:
        if not isinstance(host, dict) or str(host.get("status") or "").lower() not in FAILED_HOST_STATUSES:
            continue
        server_id = _non_negative_int(host.get("server_id"))
        if server_id:
            result.append(server_id)
    return sorted(set(result))


def _first_failed_host_task(run: PlaybookRun) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    first_host: dict[str, Any] | None = None
    first_task: dict[str, Any] | None = None
    for host in run.host_results if isinstance(run.host_results, list) else []:
        if not isinstance(host, dict):
            continue
        candidate = next(
            (
                item
                for item in (host.get("task_results") or [])
                if isinstance(item, dict) and str(item.get("status") or "").lower() in FAILED_TASK_STATUSES
            ),
            None,
        )
        if candidate or str(host.get("status") or "").lower() in FAILED_HOST_STATUSES:
            first_host, first_task = host, candidate
            break
    return first_host, first_task


def _classify_failure(
    run: PlaybookRun,
    *,
    summary: dict[str, Any],
    message: str,
    first_host: dict[str, Any] | None,
    first_task: dict[str, Any] | None,
) -> tuple[str, str, bool, str]:
    """Return the stable public failure code, message, retry flag and next action."""

    lowered = message.lower()
    code = "execution_failed"
    suggested_action = "Review the failed host and task, then start a new preflight or retry failed hosts."
    retryable = bool(run.playbook_id and run.revision_id and failed_host_ids(run))
    if run.status == PlaybookRun.STATUS_CANCELLED:
        code, message, retryable = "cancelled", "Playbook execution was cancelled.", False
        suggested_action = "Start a new run when you are ready."
    elif summary.get("authorization_or_identity_changed"):
        code, retryable = "target_changed", False
        suggested_action = "Review target access and connection identity, then complete a new preflight."
    elif summary.get("runtime_mismatch") or summary.get("runtime_identity_mismatch"):
        code, retryable = "runtime_mismatch", False
        suggested_action = "Revalidate the published revision against the current Ansible runtime."
    elif summary.get("interrupted"):
        code = "worker_interrupted"
        retryable = bool(not summary.get("retry_suppressed") and retryable)
        suggested_action = "Confirm the previous worker stopped safely before retrying."
    elif "timeout" in lowered or "timed out" in lowered:
        code = "timeout"
    elif "ansible" in lowered and ("unavailable" in lowered or "requires" in lowered):
        code = "runtime_unavailable"
        retryable = False
        suggested_action = "Restore the Ansible runtime and run preflight again."
    elif first_host and (str(first_host.get("status") or "").lower() == "unreachable" or "unreachable" in lowered):
        code = "host_unreachable"
    elif first_task:
        code = "task_failed"
    return code, message, retryable, suggested_action


def structured_failure(run: PlaybookRun) -> dict[str, Any] | None:
    if run.status not in {PlaybookRun.STATUS_FAILED, PlaybookRun.STATUS_PARTIAL, PlaybookRun.STATUS_CANCELLED}:
        return None
    summary = run.summary if isinstance(run.summary, dict) else {}
    first_host, first_task = _first_failed_host_task(run)
    message = str(run.error_message or (first_task or {}).get("output") or "Playbook execution failed")
    code, message, retryable, suggested_action = _classify_failure(
        run,
        summary=summary,
        message=message,
        first_host=first_host,
        first_task=first_task,
    )

    return _public_payload(
        {
            "code": code,
            "message": redacted_log_text(message, limit=4_000),
            "host_id": _non_negative_int((first_host or {}).get("server_id")) or None,
            "host_name": str((first_host or {}).get("server_name") or ""),
            "task_id": str((first_task or {}).get("task_id") or ""),
            "task_name": str((first_task or {}).get("description") or (first_task or {}).get("command") or ""),
            "retryable": retryable,
            "suggested_action": suggested_action,
        }
    )


def build_retry_context(run: PlaybookRun) -> dict[str, Any]:
    manifest = run.variable_manifest if isinstance(run.variable_manifest, dict) else {}
    variable_names = manifest.get("names") if isinstance(manifest.get("names"), list) else []
    managed_names = (
        manifest.get("managed_secret_names") if isinstance(manifest.get("managed_secret_names"), list) else []
    )
    failed_ids = failed_host_ids(run)
    blockers: list[dict[str, str]] = []
    if run.status not in {PlaybookRun.STATUS_FAILED, PlaybookRun.STATUS_PARTIAL}:
        blockers.append({"code": "run_not_retryable", "message": "Only failed or partial runs can retry failed hosts."})
    if not failed_ids:
        blockers.append({"code": "no_failed_hosts", "message": "No failed hosts were recorded."})
    if run.playbook_id is None or run.revision_id is None:
        blockers.append(
            {"code": "immutable_revision_missing", "message": "The original immutable revision is unavailable."}
        )
    return _public_payload(
        {
            "run_id": run.id,
            "can_retry": not blockers,
            "blockers": blockers,
            "playbook_id": run.playbook_id,
            "revision_id": run.revision_id,
            "validation_id": run.validation_id,
            "binding_profile_id": run.binding_profile_id,
            "failed_server_ids": failed_ids,
            "options": safe_run_options(run),
            "required_variable_names": [str(item) for item in variable_names[:100]],
            "managed_variable_names": [str(item) for item in managed_names[:100]],
            "values_redacted": True,
            "rerun_endpoint": f"/servers/api/playbooks/runs/{run.id}/rerun-failed/",
        }
    )


def build_playbook_run_report(run: PlaybookRun) -> dict[str, Any]:
    dispatch = _dispatch_for_run(run)
    progress = progress_snapshot(run, dispatch=dispatch)
    snapshot = run.playbook_snapshot if isinstance(run.playbook_snapshot, dict) else {}
    hosts = [
        host_summary(run, host)
        for host in (run.host_results if isinstance(run.host_results, list) else [])
        if isinstance(host, dict)
    ]
    retry_context = build_retry_context(run)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run": {
            "id": run.id,
            "playbook_id": run.playbook_id,
            "playbook_name": redacted_log_text(
                snapshot.get("name") or (run.playbook.name if run.playbook_id and run.playbook else "Playbook"),
                limit=200,
            ),
            "revision_id": run.revision_id,
            "validation_id": run.validation_id,
            "binding_profile_id": run.binding_profile_id,
            "binding_profile_name": redacted_log_text(
                run.binding_profile.name if run.binding_profile_id and run.binding_profile else "",
                limit=200,
            ),
            "status": run.status,
            "cancel_requested": bool(run.cancel_requested),
            "target_count": len(run.target_server_ids or []),
            "options": safe_run_options(run),
            "created_at": _iso(run.created_at),
            "started_at": _iso(run.started_at),
            "finished_at": _iso(run.finished_at),
            "duration_ms": _duration_ms(run),
        },
        "progress": progress,
        "summary": _public_payload(run.summary if isinstance(run.summary, dict) else {}),
        "failure": structured_failure(run),
        "hosts": hosts,
        "dispatch": public_dispatch(dispatch),
        "log": {
            "start_cursor": progress["log_start_cursor"],
            "end_cursor": progress["log_end_cursor"],
            "truncated": progress["log_truncated"],
            "url": f"/servers/api/playbooks/runs/{run.id}/log/",
        },
        "actions": {
            "can_cancel": run.status not in TERMINAL_STATUSES and not run.cancel_requested,
            "can_retry_failed": bool(retry_context["can_retry"]),
            "can_export": run.status in TERMINAL_STATUSES,
            "retry_context_url": f"/servers/api/playbooks/runs/{run.id}/retry-context/",
            "export_url": f"/servers/api/playbooks/runs/{run.id}/export/",
        },
    }


def report_etag(report: dict[str, Any]) -> str:
    stable = dict(report)
    if isinstance(report.get("run"), dict):
        stable["run"] = dict(report["run"])
        stable["run"].pop("duration_ms", None)
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f'W/"{hashlib.sha256(encoded).hexdigest()}"'


def compact_run_report_item(run: PlaybookRun) -> dict[str, Any]:
    dispatch = _dispatch_for_run(run)
    progress = progress_snapshot(run, dispatch=dispatch)
    snapshot = run.playbook_snapshot if isinstance(run.playbook_snapshot, dict) else {}
    return {
        "id": run.id,
        "playbook_id": run.playbook_id,
        "playbook_name": redacted_log_text(
            snapshot.get("name") or (run.playbook.name if run.playbook else "Playbook"), limit=200
        ),
        "status": run.status,
        "phase": progress["phase"],
        "state_version": progress["state_version"],
        "total_kind": progress["total_kind"],
        "progress_percent": progress["percent"],
        "summary": _public_payload(run.summary if isinstance(run.summary, dict) else {}),
        "failure": structured_failure(run),
        "created_at": _iso(run.created_at),
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
    }


def markdown_report(report: dict[str, Any]) -> str:
    run = report["run"]
    progress = report["progress"]
    summary = report["summary"]
    lines = [
        f"# Ansible run #{run['id']}: {run['playbook_name']}",
        "",
        f"- Status: {run['status']}",
        f"- Phase: {progress['phase']}",
        f"- Created: {run['created_at'] or '-'}",
        f"- Started: {run['started_at'] or '-'}",
        f"- Finished: {run['finished_at'] or '-'}",
        "",
        "## Summary",
        "",
    ]
    for key, value in sorted(summary.items()):
        lines.append(f"- {key}: {value}")
    if report.get("failure"):
        failure = report["failure"]
        lines.extend(["", "## Failure", "", f"- Code: {failure['code']}", f"- Message: {failure['message']}"])
    lines.extend(["", "## Hosts", ""])
    for host in report["hosts"]:
        lines.append(
            f"- {host['server_name']}: {host['status']} ({host['task_counts']['ok']}/{host['task_counts']['total']} OK)"
        )
    return "\n".join(lines).rstrip() + "\n"
