from __future__ import annotations

import re
from typing import TYPE_CHECKING

from studio.executor.change_preview import build_change_preview
from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.nodes.ops_alert_update import execute_alert_update as _execute_alert_update
from studio.executor.nodes.ops_context import load_owned_server as _load_owned_server
from studio.executor.nodes.ops_helpers import (
    ALERT_ACTIONS,
    BACKUP_RESTORE_CHECK_ACTIONS,
    DISK_CLEANUP_ACTIONS,
)
from studio.executor.nodes.ops_helpers import backup_restore_check_command as _backup_restore_check_command
from studio.executor.nodes.ops_helpers import coerce_bool as _coerce_bool
from studio.executor.nodes.ops_helpers import coerce_int as _coerce_int
from studio.executor.nodes.ops_helpers import compact_json as _compact_json
from studio.executor.nodes.ops_helpers import disk_cleanup_command as _disk_cleanup_command
from studio.executor.nodes.ops_helpers import parse_backup_file_rows as _parse_backup_file_rows
from studio.executor.nodes.ops_http_check import execute_http_check as _execute_http_check
from studio.executor.ops_runtime import ops_runtime as _ops_runtime
from studio.executor.registry import registry

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


def _ops_facade():
    """Resolve deps through ops.py so existing monkeypatches keep working."""
    from studio.executor.nodes import ops as ops_module

    return ops_module


@registry.register
class OpsDiskCleanupNode(BaseNode):
    node_type = "ops/disk_cleanup"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        ops = _ops_facade()
        config = self.node_data
        server = await _load_owned_server(ctx, config)
        secret = await ops._server_secret(server)
        action = str(config.get("action") or "inspect").strip().lower()
        if action not in DISK_CLEANUP_ACTIONS:
            return NodeResult(error="Unsupported disk cleanup action")

        before = await ops.get_linux_ui_disk(server, secret=secret)
        if action == "inspect":
            payload = {
                "server": {"id": server.id, "name": server.name, "host": server.host},
                "action": "inspect",
                **before,
            }
            text = f"Disk inspection for {server.name}: {payload.get('summary', {})}\n\n```json\n{_compact_json(payload)}\n```"
            return NodeResult(output={"output": text, "disk": payload})

        min_age_days = max(1, min(_coerce_int(config.get("min_age_days")) or 7, 365))
        max_entries = max(1, min(_coerce_int(config.get("max_entries")) or 50, 500))
        vacuum_time_days = max(1, min(_coerce_int(config.get("vacuum_time_days")) or 14, 365))
        vacuum_size_mb_raw = _coerce_int(config.get("vacuum_size_mb"))
        vacuum_size_mb = max(64, min(vacuum_size_mb_raw, 102400)) if vacuum_size_mb_raw else None
        dry_run = _coerce_bool(config.get("dry_run"), default=False)
        verify = _coerce_bool(config.get("verify"), default=True)

        try:
            command = _disk_cleanup_command(
                action,
                min_age_days=min_age_days,
                max_entries=max_entries,
                dry_run=dry_run,
                vacuum_time_days=vacuum_time_days,
                vacuum_size_mb=vacuum_size_mb,
            )
        except ValueError as exc:
            return NodeResult(error=str(exc))

        result = await ops._run_command_result(
            server,
            secret=secret,
            command=(f"{command}\naction_exit=$?\nprintf '\\n__ACTION_EXIT__=%s\\n' \"$action_exit\"\n"),
        )
        combined_output = f"{result.get('stdout') or ''}{result.get('stderr') or ''}"
        action_exit = _coerce_int(result.get("exit_code")) or 0
        exit_match = re.search(r"__ACTION_EXIT__=(\d+)", combined_output)
        if exit_match:
            action_exit = int(exit_match.group(1))
        plan_text = combined_output.partition("__PLAN__\n")[2].partition("__ACTION__\n")[0].strip()
        action_text = combined_output.partition("__ACTION__\n")[2].partition("__ACTION_EXIT__=")[0].strip()
        after = await ops.get_linux_ui_disk(server, secret=secret) if verify and not dry_run else {}
        planned_after = {
            "requested_action": action,
            "plan_excerpt": plan_text[:2000],
            "candidate_paths": [line for line in plan_text.splitlines() if line.startswith(("/tmp/", "/var/tmp/"))],
        }
        change_preview = build_change_preview(
            operation=f"disk.{action}",
            target={"server_id": server.id, "paths": ["/tmp", "/var/tmp"] if action == "tmp_cleanup" else ["journal"]},
            before={"summary": before.get("summary"), "cleanup_candidates": before.get("cleanup_candidates")},
            after=after or planned_after,
            dry_run=dry_run,
        )
        payload = {
            "server": {"id": server.id, "name": server.name, "host": server.host},
            "action": action,
            "dry_run": dry_run,
            "success": action_exit == 0,
            "exit_code": action_exit,
            "before_summary": before.get("summary"),
            "after_summary": after.get("summary") if isinstance(after, dict) else {},
            "plan_excerpt": plan_text[:2000],
            "action_excerpt": action_text[:3000],
            "min_age_days": min_age_days,
            "max_entries": max_entries,
            "vacuum_time_days": vacuum_time_days,
            "vacuum_size_mb": vacuum_size_mb,
        }
        status_text = "dry-run" if dry_run else "completed" if payload["success"] else "failed"
        text = f"Disk cleanup {action} on {server.name}: {status_text}\n\n```diff\n{change_preview['diff']}\n```"
        if payload["success"]:
            return NodeResult(
                output={"output": text, "disk_cleanup": payload, "change_preview": change_preview}
            )
        return NodeResult(
            error=payload["action_excerpt"] or "Disk cleanup failed",
            output={"output": text, "disk_cleanup": payload, "change_preview": change_preview},
        )


@registry.register
class OpsBackupRestoreCheckNode(BaseNode):
    node_type = "ops/backup_restore_check"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        ops = _ops_facade()
        config = self.node_data
        server = await _load_owned_server(ctx, config)
        secret = await ops._server_secret(server)
        action = str(config.get("action") or "inspect").strip().lower()
        if action not in BACKUP_RESTORE_CHECK_ACTIONS:
            return NodeResult(error="Unsupported backup restore check action")

        path = ctx.resolve_template(str(config.get("path") or "")).strip()
        if not path:
            return NodeResult(error="path is required")
        max_depth = max(1, min(_coerce_int(config.get("max_depth")) or 2, 5))
        max_files = max(1, min(_coerce_int(config.get("max_files")) or 20, 100))
        max_age_hours = max(1, min(_coerce_int(config.get("max_age_hours")) or 24, 8760))
        command = _backup_restore_check_command(path, action=action, max_depth=max_depth, max_files=max_files)

        result = await ops._run_command_result(server, secret=secret, command=command)
        combined_output = f"{result.get('stdout') or ''}{result.get('stderr') or ''}"
        files_raw = combined_output.partition("__FILES__\n")[2].partition("__VERIFY__\n")[0]
        verify_raw = combined_output.partition("__VERIFY__\n")[2].strip()
        files, summary = _parse_backup_file_rows(files_raw, max_age_hours=max_age_hours)
        verification_exit = _coerce_int(result.get("exit_code")) or 0
        match = re.search(r"verification_exit=(\d+)", verify_raw)
        if match:
            verification_exit = int(match.group(1))
        verification = {
            "requested": action == "verify_latest",
            "success": action == "inspect" or verification_exit == 0,
            "exit_code": verification_exit if action == "verify_latest" else None,
            "output_excerpt": verify_raw[:2000],
        }
        payload = {
            "server": {"id": server.id, "name": server.name, "host": server.host},
            "action": action,
            "path": path,
            "max_depth": max_depth,
            "max_files": max_files,
            "summary": summary,
            "files": files,
            "verification": verification,
        }
        status_text = "fresh" if summary.get("fresh") else "stale_or_missing"
        if action == "verify_latest":
            status_text = "verified" if verification["success"] else "verification_failed"
        text = (
            f"Backup restore check {action} on {server.name}: {status_text}\n\n```json\n{_compact_json(payload)}\n```"
        )
        if verification["success"]:
            return NodeResult(output={"output": text, "backup_restore_check": payload})
        return NodeResult(
            error=verification["output_excerpt"] or "Backup verification failed",
            output={"output": text, "backup_restore_check": payload},
        )


@registry.register
class OpsHttpCheckNode(BaseNode):
    node_type = "ops/http_check"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        # Resolve httpx through the ops facade so tests can monkeypatch ops.httpx.
        return await _execute_http_check(ctx, self.node_data, async_client_factory=_ops_facade().httpx.AsyncClient)


@registry.register
class OpsAlertUpdateNode(BaseNode):
    node_type = "ops/alert_update"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        ops = _ops_facade()
        config = self.node_data
        action = str(config.get("action") or "resolve").strip().lower()
        if action not in ALERT_ACTIONS:
            return NodeResult(error="Unsupported alert action")
        return await _execute_alert_update(
            ctx,
            config,
            ops_runtime=_ops_runtime,
            resolve_context_key=ops._resolve_context_key,
        )
