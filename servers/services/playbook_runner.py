"""Execute multi-host playbook runs via SSH (runbook mode)."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from asgiref.sync import async_to_sync
from django.db import close_old_connections
from django.utils import timezone

from app.tools.ssh_tools import SSHExecuteTool, ssh_manager
from servers.models import Playbook, PlaybookRun, Server
from servers.secret_utils import get_server_auth_secret, get_server_sudo_secret
from servers.services.playbook_parser import build_inventory_ini
from servers.services.server_query import get_servers_for_user, user_has_server_capability

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 4
MAX_CONCURRENCY = 12
COMMAND_TIMEOUT_HINT = 300
_db_lock = threading.Lock()


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
                        item.get("continue_on_error")
                        if "continue_on_error" in item
                        else item.get("continueOnError")
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
                    item.get("continue_on_error")
                    if "continue_on_error" in item
                    else item.get("continueOnError")
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


def build_inventory_for_servers(servers: list[Server]) -> str:
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


def _persist_run(run_id: int, **fields: Any) -> None:
    close_old_connections()
    with _db_lock:
        PlaybookRun.objects.filter(pk=run_id).update(**fields)


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
            try:
                log_line(text)
            except Exception:
                pass

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
        for tr, task in zip(result["task_results"], tasks):
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
            try:
                async_to_sync(ssh_manager.disconnect)(conn_id)
            except Exception:
                pass

    if any_error and any_success:
        result["status"] = "partial"
    elif any_error:
        result["status"] = "error"
    elif was_cancelled:
        result["status"] = "partial" if any_success else "cancelled"
    else:
        result["status"] = "success"
    return result


def execute_playbook_run(run_id: int, *, master_password: str = "") -> None:
    """Execute a PlaybookRun in-process (call from background thread)."""
    try:
        run = PlaybookRun.objects.select_related("user", "playbook").get(pk=run_id)
    except PlaybookRun.DoesNotExist:
        return

    snapshot = run.playbook_snapshot if isinstance(run.playbook_snapshot, dict) else {}
    tasks = normalize_tasks(snapshot.get("tasks") or [])
    options = run.options if isinstance(run.options, dict) else {}
    dry_run = bool(options.get("dry_run"))
    concurrency = int(options.get("concurrency") or DEFAULT_CONCURRENCY)
    concurrency = max(1, min(concurrency, MAX_CONCURRENCY))
    engine = str(options.get("engine") or "ansible").strip().lower()
    become = options.get("become", True)
    if become is None:
        become = True

    servers = resolve_target_servers(
        run.user,
        server_ids=[int(x) for x in (run.target_server_ids or [])],
        group_ids=[int(x) for x in (run.target_group_ids or [])],
    )
    if not servers:
        _persist_run(
            run_id,
            status=PlaybookRun.STATUS_FAILED,
            error_message="No accessible target servers",
            finished_at=timezone.now(),
            summary={"hosts_total": 0, "hosts_failed": 0, "hosts_ok": 0},
        )
        return

    # Prefer real Ansible when available (or forced).
    use_ansible = engine in ("ansible", "auto")
    if engine == "shell":
        use_ansible = False
    if use_ansible:
        from servers.services.ansible_engine import (
            detect_ansible,
            ensure_playbook_yaml,
            estimate_total_tasks,
            run_ansible_playbook,
        )

        detection = detect_ansible()
        if detection.get("available") or engine == "ansible":
            if not detection.get("available") and engine == "ansible":
                _persist_run(
                    run_id,
                    status=PlaybookRun.STATUS_FAILED,
                    error_message=detection.get("message") or "Ansible is not available on this host",
                    finished_at=timezone.now(),
                    summary={"engine": "ansible", "hosts_total": len(servers)},
                )
                return
            try:
                playbook_yaml = ensure_playbook_yaml(snapshot, become=bool(become))
            except Exception as exc:
                if engine == "ansible":
                    _persist_run(
                        run_id,
                        status=PlaybookRun.STATUS_FAILED,
                        error_message=f"Cannot build Ansible YAML: {exc}",
                        finished_at=timezone.now(),
                    )
                    return
                playbook_yaml = ""
            if playbook_yaml:
                initial_progress = {
                    "engine": "ansible",
                    "task_number": 0,
                    "tasks_total": estimate_total_tasks(playbook_yaml) or None,
                    "hosts_total": len(servers),
                }
                _persist_run(
                    run_id,
                    status=PlaybookRun.STATUS_RUNNING,
                    started_at=timezone.now(),
                    host_results=[_empty_host_result(s, tasks or [{"id": "ansible", "command": "ansible-playbook", "description": "Ansible"}]) for s in servers],
                    inventory_preview="",
                    error_message="",
                    live_log="",
                    progress=initial_progress,
                )

                log_lines: list[str] = []
                progress_holder: dict[str, Any] = dict(initial_progress)
                throttle = {"t": 0.0}
                progress_lock = threading.Lock()

                def _on_ansible_progress(event: dict[str, Any]) -> None:
                    with progress_lock:
                        line = event.get("line")
                        if line is not None:
                            log_lines.append(str(line))
                            if len(log_lines) > 4000:
                                del log_lines[: len(log_lines) - 3000]
                        if isinstance(event.get("progress"), dict):
                            progress_holder.clear()
                            progress_holder.update(event["progress"])
                        now = time.monotonic()
                        if now - throttle["t"] < 0.7:
                            return
                        throttle["t"] = now
                        fields: dict[str, Any] = {
                            "live_log": "\n".join(log_lines)[-160_000:],
                            "progress": dict(progress_holder),
                        }
                        live_hosts = event.get("host_results")
                        if live_hosts:
                            fields["host_results"] = live_hosts
                    _persist_run(run_id, **fields)

                result = run_ansible_playbook(
                    playbook_yaml=playbook_yaml,
                    servers=servers,
                    dry_run=dry_run,
                    become=bool(become),
                    tags=str(options.get("tags") or ""),
                    limit=str(options.get("limit") or ""),
                    extra_vars=options.get("extra_vars") if isinstance(options.get("extra_vars"), dict) else None,
                    master_password=master_password,
                    forks=concurrency,
                    cancel_check=lambda: _is_cancelled(run_id),
                    progress_callback=_on_ansible_progress,
                )
                host_results = result.get("host_results") or []
                summary = result.get("summary") or _summarize(host_results)
                summary["engine"] = "ansible"
                summary["ansible_method"] = result.get("method")
                if result.get("cancelled") or _is_cancelled(run_id):
                    status = PlaybookRun.STATUS_CANCELLED
                elif result.get("ok"):
                    status = PlaybookRun.STATUS_COMPLETED
                elif summary.get("hosts_ok") or summary.get("hosts_partial"):
                    status = PlaybookRun.STATUS_PARTIAL
                else:
                    status = PlaybookRun.STATUS_FAILED
                final_log = "\n".join(log_lines) or str(result.get("raw_stdout") or "")
                _persist_run(
                    run_id,
                    status=status,
                    host_results=host_results,
                    summary=summary,
                    inventory_preview=result.get("inventory_preview") or "",
                    error_message=result.get("error") or "",
                    finished_at=timezone.now(),
                    live_log=final_log[-160_000:],
                    progress={**progress_holder, "finished": True},
                )
                if run.playbook_id:
                    close_old_connections()
                    with _db_lock:
                        Playbook.objects.filter(pk=run.playbook_id).update(
                            last_run_at=timezone.now(),
                            last_run_status=status,
                        )
                return
        # auto mode falls through to shell if ansible missing

    inventory = build_inventory_for_servers(servers)
    if not tasks:
        _persist_run(
            run_id,
            status=PlaybookRun.STATUS_FAILED,
            error_message="No runnable shell tasks and Ansible engine did not run",
            finished_at=timezone.now(),
        )
        return
    host_results = [_empty_host_result(s, tasks) for s in servers]
    shell_tasks_total = len(tasks) * len(servers)
    _persist_run(
        run_id,
        status=PlaybookRun.STATUS_RUNNING,
        started_at=timezone.now(),
        host_results=host_results,
        inventory_preview=inventory,
        error_message="",
        live_log="",
        progress={"engine": "shell", "tasks_total": shell_tasks_total, "tasks_done": 0, "hosts_total": len(servers)},
    )

    results_by_id: dict[int, dict[str, Any]] = {hr["server_id"]: hr for hr in host_results}
    log_lines: list[str] = []
    throttle = {"t": 0.0}
    progress_lock = threading.Lock()

    def _shell_progress(*, force: bool = False) -> dict[str, Any] | None:
        """Build (and rate-limit) live progress fields from current results. Call under progress_lock."""
        now = time.monotonic()
        if not force and now - throttle["t"] < 0.5:
            return None
        throttle["t"] = now
        ordered = [results_by_id[s.id] for s in servers if s.id in results_by_id]
        done = 0
        current = ""
        for hr in ordered:
            for t in hr.get("task_results") or []:
                st = t.get("status")
                if st in ("success", "error", "skipped"):
                    done += 1
                elif st == "running" and not current:
                    current = t.get("description") or t.get("command") or ""
        return {
            "host_results": ordered,
            "summary": _summarize(ordered),
            "live_log": "\n".join(log_lines)[-160_000:],
            "progress": {
                "engine": "shell",
                "tasks_total": shell_tasks_total,
                "tasks_done": done,
                "task": current,
                "hosts_total": len(servers),
            },
        }

    def _log_line(text: str) -> None:
        with progress_lock:
            log_lines.append(text)
            if len(log_lines) > 4000:
                del log_lines[: len(log_lines) - 3000]

    def _on_task_progress(hr: dict[str, Any]) -> None:
        with progress_lock:
            results_by_id[int(hr["server_id"])] = hr
            fields = _shell_progress()
        if fields:
            _persist_run(run_id, **fields)

    def _run_one(server: Server) -> dict[str, Any]:
        close_old_connections()
        try:
            if _is_cancelled(run_id):
                hr = _empty_host_result(server, tasks)
                hr["status"] = "cancelled"
                for tr in hr["task_results"]:
                    tr["status"] = "skipped"
                    tr["output"] = "Cancelled"
                return hr
            return _execute_on_server(
                server=server,
                tasks=tasks,
                dry_run=dry_run,
                master_password=master_password,
                cancel_check=lambda: _is_cancelled(run_id),
                on_task_progress=_on_task_progress,
                log_line=_log_line,
            )
        finally:
            close_old_connections()

    def _store_host_result(hr: dict[str, Any]) -> None:
        with progress_lock:
            results_by_id[int(hr["server_id"])] = hr
            fields = _shell_progress(force=True)
        if fields:
            _persist_run(run_id, **fields)

    try:
        # Sequential when single host or concurrency=1 (avoids sqlite lock issues in tests/dev)
        use_pool = concurrency > 1 and len(servers) > 1
        if use_pool:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {pool.submit(_run_one, s): s.id for s in servers}
                for fut in as_completed(futures):
                    try:
                        hr = fut.result()
                    except Exception as exc:
                        sid = futures[fut]
                        hr = results_by_id.get(sid) or {
                            "server_id": sid,
                            "server_name": f"Server #{sid}",
                            "task_results": [],
                            "status": "error",
                        }
                        hr["status"] = "error"
                        hr["task_results"] = hr.get("task_results") or []
                        for tr in hr["task_results"]:
                            if tr.get("status") in ("pending", "running"):
                                tr["status"] = "error"
                                tr["output"] = str(exc)
                        logger.exception("Playbook host execution failed run=%s server=%s", run_id, sid)
                    _store_host_result(hr)
        else:
            for s in servers:
                if _is_cancelled(run_id):
                    hr = _empty_host_result(s, tasks)
                    hr["status"] = "cancelled"
                    for tr in hr["task_results"]:
                        tr["status"] = "skipped"
                        tr["output"] = "Cancelled"
                    _store_host_result(hr)
                    continue
                try:
                    hr = _run_one(s)
                except Exception as exc:
                    logger.exception("Playbook host execution failed run=%s server=%s", run_id, s.id)
                    hr = _empty_host_result(s, tasks)
                    hr["status"] = "error"
                    for tr in hr["task_results"]:
                        tr["status"] = "error"
                        tr["output"] = str(exc)
                _store_host_result(hr)

        ordered = [results_by_id[s.id] for s in servers if s.id in results_by_id]
        if _is_cancelled(run_id):
            for hr in ordered:
                if hr.get("status") == "pending":
                    hr["status"] = "cancelled"
                    for tr in hr.get("task_results") or []:
                        if tr.get("status") in ("pending", "running"):
                            tr["status"] = "skipped"
                            tr["output"] = "Cancelled"
            summary = _summarize(ordered)
            done = sum(
                1
                for hr in ordered
                for t in hr.get("task_results") or []
                if t.get("status") in ("success", "error", "skipped")
            )
            _persist_run(
                run_id,
                status=PlaybookRun.STATUS_CANCELLED,
                host_results=ordered,
                summary=summary,
                finished_at=timezone.now(),
                live_log="\n".join(log_lines)[-160_000:],
                progress={
                    "engine": "shell",
                    "tasks_total": shell_tasks_total,
                    "tasks_done": done,
                    "hosts_total": len(servers),
                    "finished": True,
                },
            )
        else:
            summary = _summarize(ordered)
            summary["engine"] = "shell"
            if summary["hosts_failed"] == 0 and summary["hosts_partial"] == 0:
                status = PlaybookRun.STATUS_COMPLETED
            elif summary["hosts_ok"] == 0 and summary["hosts_partial"] == 0:
                status = PlaybookRun.STATUS_FAILED
            else:
                status = PlaybookRun.STATUS_PARTIAL
            _persist_run(
                run_id,
                status=status,
                host_results=ordered,
                summary=summary,
                finished_at=timezone.now(),
                live_log="\n".join(log_lines)[-160_000:],
                progress={
                    "engine": "shell",
                    "tasks_total": shell_tasks_total,
                    "tasks_done": shell_tasks_total,
                    "hosts_total": len(servers),
                    "finished": True,
                },
            )

        # Update playbook last run meta
        close_old_connections()
        with _db_lock:
            run.refresh_from_db()
            if run.playbook_id:
                Playbook.objects.filter(pk=run.playbook_id).update(
                    last_run_at=timezone.now(),
                    last_run_status=run.status,
                )
    except Exception as exc:
        logger.exception("Playbook run failed run=%s", run_id)
        _persist_run(
            run_id,
            status=PlaybookRun.STATUS_FAILED,
            error_message=str(exc)[:2000],
            finished_at=timezone.now(),
        )
    finally:
        close_old_connections()


def start_playbook_run_async(run_id: int, *, master_password: str = "") -> None:
    thread = threading.Thread(
        target=execute_playbook_run,
        kwargs={"run_id": run_id, "master_password": master_password},
        name=f"playbook-run-{run_id}",
        daemon=True,
    )
    thread.start()
