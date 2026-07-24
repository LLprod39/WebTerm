"""Playbook runner helpers: task normalization, targeting, inventory, per-server execution.

Extracted from playbook_runner.py to keep modules under the size limit.
Re-exported from servers.services.playbook_runner for backward compatibility.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from asgiref.sync import async_to_sync
from django.db import close_old_connections, transaction
from django.utils import timezone

from app.tools.ssh_tools import SSHExecuteTool, ssh_manager
from servers.models import PlaybookRun, PlaybookRunDispatch, Server
from servers.secret_utils import get_server_auth_secret, get_server_sudo_secret
from servers.services.playbook_parser import build_inventory_ini
from servers.services.playbook_run_state import (
    TERMINAL_PLAYBOOK_RUN_STATUSES,
    transition_playbook_run,
)
from servers.services.server_query import get_servers_for_user, user_has_server_capability

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 4
MAX_CONCURRENCY = 12
COMMAND_TIMEOUT_HINT = 300
_db_lock = threading.Lock()


@dataclass(frozen=True)
class PlaybookRunExecutionFence:
    dispatch_id: int
    claimed_by: str
    attempt_count: int


def normalize_tasks(raw_tasks: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_tasks, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_tasks):
        if not isinstance(item, dict):
            continue
        command = str(item.get("command") or "").strip()
        if not command:
            continue
        # Skip pure comment placeholders (unsupported ansible modules)
        if command.lstrip().startswith("#"):
            out.append(
                {
                    "id": str(item.get("id") or f"t_{idx}"),
                    "command": command,
                    "description": str(item.get("description") or ""),
                    "continue_on_error": bool(
                        item.get("continue_on_error") if "continue_on_error" in item else item.get("continueOnError")
                    ),
                    "skipped_module": True,
                }
            )
            continue
        out.append(
            {
                "id": str(item.get("id") or f"t_{idx}"),
                "command": command,
                "description": str(item.get("description") or ""),
                "continue_on_error": bool(
                    item.get("continue_on_error") if "continue_on_error" in item else item.get("continueOnError")
                ),
                "skipped_module": False,
            }
        )
    return out


def resolve_target_servers(
    user,
    *,
    server_ids: list[int] | None = None,
    group_ids: list[int] | None = None,
) -> list[Server]:
    qs = get_servers_for_user(user).filter(is_active=True)
    selected: dict[int, Server] = {}

    if server_ids:
        for server in qs.filter(id__in=list(server_ids)):
            if user_has_server_capability(server, user, "execute_command"):
                selected[server.id] = server

    if group_ids:
        for server in qs.filter(group_id__in=list(group_ids)):
            if user_has_server_capability(server, user, "execute_command"):
                selected[server.id] = server

    return list(selected.values())


def build_inventory_for_servers(
    servers: list[Server],
    *,
    extra_groups: dict[str, list[int]] | None = None,
) -> str:
    payload = [
        {
            "id": s.id,
            "name": s.name,
            "host": s.host,
            "port": s.port,
            "username": s.username,
            "detected_os": getattr(s, "detected_os", "") or "",
        }
        for s in servers
    ]
    groups: dict[str, list[int]] = {}
    for s in servers:
        if s.group_id and s.group:
            groups.setdefault(s.group.name, []).append(s.id)
    for name, server_ids in (extra_groups or {}).items():
        groups[name] = [server_id for server_id in server_ids if server_id in {server.id for server in servers}]
    return build_inventory_ini(payload, groups)


def _empty_host_result(server: Server, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "server_id": server.id,
        "server_name": server.name,
        "host": server.host,
        "status": "pending",
        "task_results": [
            {
                "task_id": t["id"],
                "command": t["command"],
                "description": t.get("description") or "",
                "status": "pending",
                "output": "",
                "exit_code": None,
            }
            for t in tasks
        ],
    }


def _summarize(host_results: list[dict[str, Any]]) -> dict[str, Any]:
    hosts_total = len(host_results)
    hosts_ok = 0
    hosts_failed = 0
    hosts_partial = 0
    tasks_ok = 0
    tasks_failed = 0
    tasks_skipped = 0
    for host in host_results:
        tr = host.get("task_results") or []
        ok = sum(1 for t in tr if t.get("status") == "success")
        failed = sum(1 for t in tr if t.get("status") == "error")
        skipped = sum(1 for t in tr if t.get("status") == "skipped")
        tasks_ok += ok
        tasks_failed += failed
        tasks_skipped += skipped
        if failed and ok:
            hosts_partial += 1
        elif failed:
            hosts_failed += 1
        elif host.get("status") in ("success", "completed") or (ok and not failed):
            hosts_ok += 1
    return {
        "hosts_total": hosts_total,
        "hosts_ok": hosts_ok,
        "hosts_failed": hosts_failed,
        "hosts_partial": hosts_partial,
        "tasks_ok": tasks_ok,
        "tasks_failed": tasks_failed,
        "tasks_skipped": tasks_skipped,
    }


def playbook_run_fence_is_owned(fence: PlaybookRunExecutionFence) -> bool:
    close_old_connections()
    return PlaybookRunDispatch.objects.filter(
        pk=fence.dispatch_id,
        status=PlaybookRunDispatch.STATUS_CLAIMED,
        claimed_by=fence.claimed_by,
        attempt_count=fence.attempt_count,
        lease_expires_at__gt=timezone.now(),
    ).exists()


def _write_run_fields(run_id: int, fields: dict[str, Any], *, fenced: bool) -> bool:
    status = fields.pop("status", None)
    if status in TERMINAL_PLAYBOOK_RUN_STATUSES:
        return transition_playbook_run(run_id, status, **fields).transitioned
    if status is not None:
        fields["status"] = status
    queryset = PlaybookRun.objects.filter(pk=run_id)
    if fenced:
        queryset = queryset.exclude(status__in=TERMINAL_PLAYBOOK_RUN_STATUSES)
    return bool(queryset.update(**fields))


def _persist_run(
    run_id: int,
    *,
    execution_fence: PlaybookRunExecutionFence | None = None,
    **fields: Any,
) -> bool:
    close_old_connections()
    with _db_lock:
        if execution_fence is None:
            return _write_run_fields(run_id, fields, fenced=False)
        with transaction.atomic():
            owns_claim = (
                PlaybookRunDispatch.objects.select_for_update()
                .filter(
                    pk=execution_fence.dispatch_id,
                    status=PlaybookRunDispatch.STATUS_CLAIMED,
                    claimed_by=execution_fence.claimed_by,
                    attempt_count=execution_fence.attempt_count,
                    lease_expires_at__gt=timezone.now(),
                )
                .exists()
            )
            if not owns_claim:
                return False
            return _write_run_fields(run_id, fields, fenced=True)


def _is_cancelled(run_id: int) -> bool:
    close_old_connections()
    with _db_lock:
        return PlaybookRun.objects.filter(pk=run_id, cancel_requested=True).exists()


def _execute_on_server(
    *,
    server: Server,
    tasks: list[dict[str, Any]],
    dry_run: bool,
    master_password: str,
    cancel_check: Callable[[], bool] | None = None,
    on_task_progress: Callable[[dict[str, Any]], None] | None = None,
    log_line: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    def _notify() -> None:
        if on_task_progress:
            try:
                on_task_progress(result)
            except Exception:
                logger.debug("playbook progress callback failed", exc_info=True)

    def _log(text: str) -> None:
        if log_line:
            with contextlib.suppress(Exception):
                log_line(text)

    result = _empty_host_result(server, tasks)
    password = None
    sudo_password = None
    try:
        if server.auth_method in ("password", "key_password"):
            password = get_server_auth_secret(server, master_password=master_password, fallback_plain="")
        sudo_password = get_server_sudo_secret(server, master_password=master_password, fallback_plain="")
    except Exception as exc:
        result["status"] = "error"
        for tr in result["task_results"]:
            tr["status"] = "error"
            tr["output"] = f"Secret resolve failed: {exc}"
            tr["exit_code"] = 1
        return result

    if dry_run:
        result["status"] = "success"
        for tr, task in zip(result["task_results"], tasks, strict=False):
            if task.get("skipped_module"):
                tr["status"] = "skipped"
                tr["output"] = "Dry-run: unsupported/imported module (comment placeholder)"
            else:
                tr["status"] = "success"
                tr["output"] = f"[dry-run] would execute:\n{task['command']}"
                tr["exit_code"] = 0
        return result

    conn_id = None
    try:
        conn_id = async_to_sync(ssh_manager.connect)(
            host=server.host,
            username=server.username,
            password=password,
            key_path=server.key_path if server.auth_method in ("key", "key_password") else None,
            port=server.port,
            network_config=server.network_config or {},
            server=server,
        )
    except Exception as exc:
        result["status"] = "error"
        for tr in result["task_results"]:
            tr["status"] = "error"
            tr["output"] = f"SSH connect failed: {exc}"
            tr["exit_code"] = 1
        return result

    execute_tool = SSHExecuteTool()
    should_skip = False
    was_cancelled = False
    any_error = False
    any_success = False

    try:
        for idx, task in enumerate(tasks):
            tr = result["task_results"][idx]
            if should_skip:
                tr["status"] = "skipped"
                tr["output"] = "Skipped due to previous error"
                continue
            if was_cancelled or (cancel_check and cancel_check()):
                was_cancelled = True
                tr["status"] = "skipped"
                tr["output"] = "Cancelled"
                continue
            if task.get("skipped_module"):
                tr["status"] = "skipped"
                tr["output"] = "Skipped: unsupported Ansible module (import placeholder)"
                continue

            tr["status"] = "running"
            _log(f"TASK [{task.get('description') or task['command']}] — {server.name}")
            _notify()
            try:
                exec_result = async_to_sync(execute_tool.execute)(
                    conn_id=conn_id,
                    command=task["command"],
                    sudo_auth_mode=getattr(server, "sudo_auth_mode", "none"),
                    sudo_password=sudo_password,
                )
                stdout = str(exec_result.get("stdout") or "")
                stderr = str(exec_result.get("stderr") or "")
                exit_code = int(exec_result.get("exit_code") or 0)
                output = (stdout + ("\n" + stderr if stderr else "")).strip()
                tr["exit_code"] = exit_code
                tr["output"] = output[:50_000]
                if exit_code == 0:
                    tr["status"] = "success"
                    any_success = True
                    _log(f"ok: [{server.name}]")
                else:
                    tr["status"] = "error"
                    any_error = True
                    _log(f"failed: [{server.name}] rc={exit_code}")
                    if not task.get("continue_on_error"):
                        should_skip = True
            except Exception as exc:
                tr["status"] = "error"
                tr["output"] = str(exc)[:50_000]
                tr["exit_code"] = 1
                any_error = True
                _log(f"failed: [{server.name}] {str(exc)[:200]}")
                if not task.get("continue_on_error"):
                    should_skip = True
            _notify()
    finally:
        if conn_id:
            with contextlib.suppress(Exception):
                async_to_sync(ssh_manager.disconnect)(conn_id)

    if any_error and any_success:
        result["status"] = "partial"
    elif any_error:
        result["status"] = "error"
    elif was_cancelled:
        result["status"] = "partial" if any_success else "cancelled"
    else:
        result["status"] = "success"
    return result
