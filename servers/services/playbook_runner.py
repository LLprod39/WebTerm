"""Execute multi-host playbook runs via SSH (runbook mode)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from django.db import close_old_connections
from django.utils import timezone

from app.core.redacted_logging import redacted_log_text
from core_ui.managed_secrets import get_playbook_run_variables
from servers.models import PlaybookRun, Server
from servers.services.playbook_runner_support import (
    DEFAULT_CONCURRENCY,
    MAX_CONCURRENCY,
    PlaybookRunExecutionFence,
    _empty_host_result,
    _execute_on_server,
    _is_cancelled,
    _persist_run,
    _summarize,
    build_inventory_for_servers,
    normalize_tasks,
    resolve_target_servers,
)
from servers.services.playbooks.target_identity import target_connection_identities_match

logger = logging.getLogger(__name__)

__all__ = [
    "build_inventory_for_servers",
    "execute_playbook_run",
    "normalize_tasks",
    "resolve_target_servers",
    "start_playbook_run_async",
]


def _secret_text_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _secret_text_values(nested)]
    if isinstance(value, (list, tuple, set)):
        return [item for nested in value for item in _secret_text_values(nested)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _redact_runtime_value(value: Any, *, secret_values: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return {key: _redact_runtime_value(item, secret_values=secret_values) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_runtime_value(item, secret_values=secret_values) for item in value]
    if not isinstance(value, str):
        return value
    text = redacted_log_text(value)
    for secret in secret_values:
        text = text.replace(secret, "[REDACTED:managed_secret]")
    return text


def _runtime_secret_context(
    run: PlaybookRun,
    run_id: int,
    *,
    master_password: str | None,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    runtime_variables = get_playbook_run_variables(run_id)
    variable_manifest = run.variable_manifest if isinstance(run.variable_manifest, dict) else {}
    secret_names = {
        str(name)
        for key in ("secret_names", "managed_secret_names")
        for name in (variable_manifest.get(key) if isinstance(variable_manifest.get(key), list) else [])
    }
    secret_payload = {name: runtime_variables[name] for name in secret_names if name in runtime_variables}
    secret_values = tuple(
        sorted(
            {str(master_password or ""), *_secret_text_values(secret_payload)} - {""},
            key=len,
            reverse=True,
        )
    )
    return runtime_variables, secret_values


def _redacted_run_fields(fields: dict[str, Any], *, secret_values: tuple[str, ...]) -> dict[str, Any]:
    return {
        name: _redact_runtime_value(value, secret_values=secret_values)
        for name, value in fields.items()
    }


def _estimated_total_kind(total: int) -> str:
    return "estimated" if total else "unknown"


def execute_playbook_run(
    run_id: int,
    *,
    master_password: str = "",
    execution_fence: PlaybookRunExecutionFence | None = None,
    lease_check: Callable[[], bool] | None = None,
) -> None:
    """Execute a PlaybookRun, optionally fenced to one durable claim attempt."""
    try:
        run = PlaybookRun.objects.select_related("user", "playbook", "revision__asset_bundle").get(pk=run_id)
    except PlaybookRun.DoesNotExist:
        return

    runtime_variables, secret_values = _runtime_secret_context(
        run,
        run_id,
        master_password=master_password,
    )

    def _lease_owned() -> bool:
        return lease_check is None or bool(lease_check())

    def _should_cancel() -> bool:
        return _is_cancelled(run_id) or not _lease_owned()

    def _save_run(**fields: Any) -> bool:
        if not _lease_owned():
            return False
        safe_fields = _redacted_run_fields(fields, secret_values=secret_values)
        return _persist_run(run_id, execution_fence=execution_fence, **safe_fields)

    snapshot = run.playbook_snapshot if isinstance(run.playbook_snapshot, dict) else {}
    tasks = normalize_tasks(snapshot.get("tasks") or [])
    has_ansible_source = bool(str(snapshot.get("source_yaml") or "").strip())
    options = run.options if isinstance(run.options, dict) else {}
    dry_run = bool(options.get("dry_run"))
    concurrency = int(options.get("concurrency") or DEFAULT_CONCURRENCY)
    concurrency = max(1, min(concurrency, MAX_CONCURRENCY))
    engine = str(options.get("engine") or "ansible").strip().lower()
    become = options.get("become", True)
    if become is None:
        become = True

    if has_ansible_source and engine not in {"ansible", "auto"}:
        _save_run(
            status=PlaybookRun.STATUS_FAILED,
            error_message="Ansible YAML cannot be executed by the shell engine",
            finished_at=timezone.now(),
            summary={"engine": "ansible", "hosts_total": 0},
        )
        return

    target_ids = {int(x) for x in (run.target_server_ids or [])}
    servers = resolve_target_servers(
        run.user,
        server_ids=sorted(target_ids),
        # Groups are audit metadata only after preparation. Re-resolving them
        # here could add hosts that joined a group after validation/snapshot.
        group_ids=[],
    )
    if not target_ids:
        _save_run(
            status=PlaybookRun.STATUS_FAILED,
            error_message="No accessible target servers",
            finished_at=timezone.now(),
            summary={"hosts_total": 0, "hosts_failed": 0, "hosts_ok": 0},
        )
        return
    if {server.id for server in servers} != target_ids or not target_connection_identities_match(
        snapshot.get("target_connection_identities"),
        servers,
    ):
        _save_run(
            status=PlaybookRun.STATUS_FAILED,
            error_message="Target authorization or connection identity changed after preflight",
            finished_at=timezone.now(),
            summary={
                "hosts_total": 0,
                "hosts_failed": 0,
                "hosts_ok": 0,
                "target_identity_changed": True,
            },
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
        from servers.services.playbook_execution_runtime import prepare_claim_runtime

        detection = detect_ansible()
        if detection.get("available") or engine == "ansible" or has_ansible_source:
            if not detection.get("available") and (engine == "ansible" or has_ansible_source):
                _save_run(
                    status=PlaybookRun.STATUS_FAILED,
                    error_message=detection.get("message") or "Ansible is not available on this host",
                    finished_at=timezone.now(),
                    summary={"engine": "ansible", "hosts_total": len(servers)},
                )
                return
            runtime_identity, runtime_ready = prepare_claim_runtime(
                run, detection, execution_fence, len(servers), _save_run
            )
            if not runtime_ready:
                return
            runtime_bundle = None
            if snapshot.get("asset_bundle_id"):
                try:
                    from servers.services.playbooks.bundle_runtime import (
                        BundleRuntimeError,
                        load_revision_runtime_bundle,
                    )

                    if run.revision is None or run.revision_id != snapshot.get("revision_id"):
                        raise BundleRuntimeError("The run revision no longer matches its immutable snapshot")
                    runtime_bundle = load_revision_runtime_bundle(run.revision)
                    if runtime_bundle is None or runtime_bundle.content_hash != snapshot.get("bundle_hash"):
                        raise BundleRuntimeError("The run bundle no longer matches its immutable snapshot")
                except BundleRuntimeError as exc:
                    _save_run(
                        status=PlaybookRun.STATUS_FAILED,
                        error_message=str(exc),
                        finished_at=timezone.now(),
                        summary={"engine": "ansible", "hosts_total": len(servers)},
                    )
                    return
            try:
                playbook_yaml = ensure_playbook_yaml(snapshot, become=bool(become))
            except Exception as exc:
                if engine == "ansible" or has_ansible_source:
                    _save_run(
                        status=PlaybookRun.STATUS_FAILED,
                        error_message=f"Cannot build Ansible YAML: {exc}",
                        finished_at=timezone.now(),
                    )
                    return
                playbook_yaml = ""
            if playbook_yaml:
                estimated_tasks = estimate_total_tasks(playbook_yaml)
                initial_progress = {
                    "engine": "ansible",
                    "task_number": 0,
                    "tasks_total": estimated_tasks or None,
                    "total_kind": _estimated_total_kind(estimated_tasks),
                    "hosts_total": len(servers),
                }
                _save_run(
                    status=PlaybookRun.STATUS_RUNNING,
                    started_at=timezone.now(),
                    host_results=[
                        _empty_host_result(
                            s, tasks or [{"id": "ansible", "command": "ansible-playbook", "description": "Ansible"}]
                        )
                        for s in servers
                    ],
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
                    _save_run(**fields)

                result = run_ansible_playbook(
                    playbook_yaml=playbook_yaml,
                    servers=servers,
                    dry_run=dry_run,
                    become=bool(become),
                    tags=str(options.get("tags") or ""),
                    skip_tags=str(options.get("skip_tags") or ""),
                    limit=str(options.get("limit") or ""),
                    extra_vars=runtime_variables,
                    master_password=master_password,
                    forks=concurrency,
                    cancel_check=_should_cancel,
                    progress_callback=_on_ansible_progress,
                    inventory_binding_groups=(
                        options.get("inventory_binding_groups")
                        if isinstance(options.get("inventory_binding_groups"), dict)
                        else None
                    ),
                    project_files=runtime_bundle.files if runtime_bundle else None,
                    project_entrypoint=runtime_bundle.entrypoint if runtime_bundle else "playbook.yml",
                    runtime_identity=runtime_identity,
                )
                host_results = result.get("host_results") or []
                summary = result.get("summary") or _summarize(host_results)
                summary["engine"] = "ansible"
                summary["ansible_method"] = result.get("method")
                if result.get("cancelled") or _should_cancel():
                    status = PlaybookRun.STATUS_CANCELLED
                elif result.get("ok"):
                    status = PlaybookRun.STATUS_COMPLETED
                elif summary.get("hosts_ok") or summary.get("hosts_partial"):
                    status = PlaybookRun.STATUS_PARTIAL
                else:
                    status = PlaybookRun.STATUS_FAILED
                final_log = "\n".join(log_lines) or str(result.get("raw_stdout") or "")
                _save_run(
                    status=status,
                    host_results=host_results,
                    summary=summary,
                    inventory_preview=result.get("inventory_preview") or "",
                    error_message=result.get("error") or "",
                    finished_at=timezone.now(),
                    live_log=final_log[-160_000:],
                    progress={**progress_holder, "finished": True},
                )
                return
        # Auto mode may fall through only for native command runbooks. Imported
        # Ansible source is never executed through its lossy shell projection.
        if has_ansible_source:
            _save_run(
                status=PlaybookRun.STATUS_FAILED,
                error_message="Ansible source requires an available Ansible runtime",
                finished_at=timezone.now(),
                summary={"engine": "ansible", "hosts_total": len(servers)},
            )
            return

    inventory = build_inventory_for_servers(servers)
    if not tasks:
        _save_run(
            status=PlaybookRun.STATUS_FAILED,
            error_message="No runnable shell tasks and Ansible engine did not run",
            finished_at=timezone.now(),
        )
        return
    host_results = [_empty_host_result(s, tasks) for s in servers]
    shell_tasks_total = len(tasks) * len(servers)
    _save_run(
        status=PlaybookRun.STATUS_RUNNING,
        started_at=timezone.now(),
        host_results=host_results,
        inventory_preview=inventory,
        error_message="",
        live_log="",
        progress={
            "engine": "shell",
            "tasks_total": shell_tasks_total,
            "tasks_done": 0,
            "total_kind": "exact",
            "hosts_total": len(servers),
        },
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
                "total_kind": "exact",
                "task": current,
                "hosts_total": len(servers),
            },
        }

    def _log_line(text: str) -> None:
        with progress_lock:
            log_lines.append(redacted_log_text(text))
            if len(log_lines) > 4000:
                del log_lines[: len(log_lines) - 3000]

    def _on_task_progress(hr: dict[str, Any]) -> None:
        with progress_lock:
            results_by_id[int(hr["server_id"])] = hr
            fields = _shell_progress()
        if fields:
            _save_run(**fields)

    def _run_one(server: Server) -> dict[str, Any]:
        close_old_connections()
        try:
            if _should_cancel():
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
                cancel_check=_should_cancel,
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
            _save_run(**fields)

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
                if _should_cancel():
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
        if _should_cancel():
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
            _save_run(
                status=PlaybookRun.STATUS_CANCELLED,
                host_results=ordered,
                summary=summary,
                finished_at=timezone.now(),
                live_log="\n".join(log_lines)[-160_000:],
                progress={
                    "engine": "shell",
                    "tasks_total": shell_tasks_total,
                    "tasks_done": done,
                    "total_kind": "exact",
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
            _save_run(
                status=status,
                host_results=ordered,
                summary=summary,
                finished_at=timezone.now(),
                live_log="\n".join(log_lines)[-160_000:],
                progress={
                    "engine": "shell",
                    "tasks_total": shell_tasks_total,
                    "tasks_done": shell_tasks_total,
                    "total_kind": "exact",
                    "hosts_total": len(servers),
                    "finished": True,
                },
            )

    except Exception as exc:
        safe_error = _redact_runtime_value(str(exc), secret_values=secret_values)
        logger.error("Playbook run failed run=%s: %s", run_id, safe_error)
        _save_run(
            status=PlaybookRun.STATUS_FAILED,
            error_message=str(safe_error)[:2000],
            finished_at=timezone.now(),
        )
    finally:
        close_old_connections()


def start_playbook_run_async(run_id: int, *, master_password: str = "") -> None:
    """Compatibility facade: enqueue for the durable execution plane."""
    from servers.playbooks.dispatch import enqueue_playbook_run_dispatch

    run = PlaybookRun.objects.get(pk=run_id)
    enqueue_playbook_run_dispatch(run=run, master_password=master_password)
