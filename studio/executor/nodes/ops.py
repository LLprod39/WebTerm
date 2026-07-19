from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any

import httpx

from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.nodes.ops_actions import (
    execute_docker_action as _execute_docker_action,
)
from studio.executor.nodes.ops_actions import (
    execute_process_action as _execute_process_action,
)
from studio.executor.nodes.ops_actions import (
    execute_service_action as _execute_service_action,
)
from studio.executor.nodes.ops_alert_update import execute_alert_update as _execute_alert_update
from studio.executor.nodes.ops_context import load_owned_server as _load_owned_server
from studio.executor.nodes.ops_context import resolve_context_key as _resolve_context_key
from studio.executor.nodes.ops_context import server_secret as _server_secret
from studio.executor.nodes.ops_helpers import (
    ALERT_ACTIONS,
    BACKUP_RESTORE_CHECK_ACTIONS,
    DISK_CLEANUP_ACTIONS,
    DOCKER_ACTIONS,
    FILE_ACTIONS,
    PACKAGE_ACTIONS,
    PROCESS_ACTIONS,
    SERVER_SNAPSHOT_SECTIONS,
    SERVICE_ACTIONS,
)
from studio.executor.nodes.ops_helpers import backup_restore_check_command as _backup_restore_check_command
from studio.executor.nodes.ops_helpers import coerce_bool as _coerce_bool
from studio.executor.nodes.ops_helpers import coerce_int as _coerce_int
from studio.executor.nodes.ops_helpers import coerce_list as _coerce_list
from studio.executor.nodes.ops_helpers import compact_json as _compact_json
from studio.executor.nodes.ops_helpers import disk_cleanup_command as _disk_cleanup_command
from studio.executor.nodes.ops_helpers import normalise_packages as _normalise_packages
from studio.executor.nodes.ops_helpers import package_command as _package_command
from studio.executor.nodes.ops_helpers import parse_backup_file_rows as _parse_backup_file_rows
from studio.executor.nodes.ops_http_check import execute_http_check as _execute_http_check
from studio.executor.ops_runtime import (
    get_linux_ui_capabilities,
    get_linux_ui_disk,
    get_linux_ui_docker,
    get_linux_ui_docker_logs,
    get_linux_ui_logs,
    get_linux_ui_network,
    get_linux_ui_overview,
    get_linux_ui_packages,
    get_linux_ui_processes,
    get_linux_ui_service_logs,
    get_linux_ui_services,
    read_text_file,
    run_linux_ui_docker_action,
    run_linux_ui_process_action,
    run_linux_ui_service_action,
    write_text_file,
)
from studio.executor.ops_runtime import (
    log_query_sources as _log_query_sources,
)
from studio.executor.ops_runtime import (
    ops_runtime as _ops_runtime,
)
from studio.executor.ops_runtime import (
    run_command_result as _run_command_result,
)
from studio.executor.registry import registry

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


@registry.register
class OpsLogQueryNode(BaseNode):
    node_type = "ops/log_query"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        config = self.node_data
        server = await _load_owned_server(ctx, config)
        secret = await _server_secret(server)
        source = str(config.get("source") or "journal").strip().lower()
        if source not in _log_query_sources():
            return NodeResult(error="Unsupported log source")

        lines = _coerce_int(config.get("lines")) or 120
        service = ctx.resolve_template(str(config.get("service") or ctx.get_variable("service_name", "")))
        container = ctx.resolve_template(str(config.get("container") or ctx.get_variable("container_name", "")))
        filter_text = ctx.resolve_template(str(config.get("filter_text") or "")).strip()

        if source == "service" and not service.strip():
            return NodeResult(error="service is required for service log source")
        if source == "docker" and not container.strip():
            return NodeResult(error="container is required for docker log source")

        if source == "docker":
            logs = await get_linux_ui_docker_logs(server, secret=secret, container=container, lines=lines)
            content = str(logs.get("content") or "")
            payload: dict[str, Any] = {
                "server": {"id": server.id, "name": server.name, "host": server.host},
                "source": "docker",
                "container": logs.get("container") or container,
                "lines": logs.get("lines") or lines,
                "content": content,
            }
        else:
            logs = await get_linux_ui_logs(server, secret=secret, source=source, lines=lines, service=service)
            content = str(logs.get("content") or "")
            payload = {
                "server": {"id": server.id, "name": server.name, "host": server.host},
                "source": logs.get("source") or source,
                "service": logs.get("service") or service,
                "lines": logs.get("lines") or lines,
                "available": logs.get("available"),
                "content": content,
            }

        if filter_text:
            needle = filter_text.lower()
            matched_lines = [line for line in content.splitlines() if needle in line.lower()]
            payload["filter_text"] = filter_text
            payload["match_count"] = len(matched_lines)
            payload["matched_lines"] = matched_lines[:80]

        target = payload.get("container") or payload.get("service") or payload.get("source")
        text = f"Log query {source} on {server.name}: {target}\n\n```json\n{_compact_json(payload)}\n```"
        return NodeResult(output={"output": text, "logs": payload})


@registry.register
class OpsFileActionNode(BaseNode):
    node_type = "ops/file_action"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        config = self.node_data
        server = await _load_owned_server(ctx, config)
        secret = await _server_secret(server)
        action = str(config.get("action") or "read").strip().lower()
        if action not in FILE_ACTIONS:
            return NodeResult(error="Unsupported file action")

        path = ctx.resolve_template(str(config.get("path") or "")).strip()
        if not path:
            return NodeResult(error="path is required")

        max_bytes = _coerce_int(config.get("max_bytes")) or 131072
        max_bytes = max(1024, min(max_bytes, 1048576))

        if action == "read":
            result = await read_text_file(server, secret=secret, path=path, max_bytes=max_bytes)
            payload = {
                "server": {"id": server.id, "name": server.name, "host": server.host},
                "action": "read",
                "path": result.get("path"),
                "filename": result.get("filename"),
                "size": result.get("size"),
                "encoding": result.get("encoding"),
                "content": result.get("content") or "",
            }
            text = f"File read on {server.name}: {payload['path']}\n\n```text\n{str(payload['content'])[:4000]}\n```"
            return NodeResult(output={"output": text, "file": payload})

        content = ctx.resolve_template(str(config.get("content") or ""))
        if not content and not _coerce_bool(config.get("allow_empty_content"), default=False):
            return NodeResult(error="content is required for write action")
        result = await write_text_file(server, secret=secret, path=path, content=content, max_bytes=max_bytes)
        content_hash = hashlib.sha256(str(content).encode("utf-8")).hexdigest()
        payload = {
            "server": {"id": server.id, "name": server.name, "host": server.host},
            "action": "write",
            "path": result.get("path"),
            "filename": result.get("filename"),
            "size": result.get("size"),
            "encoding": result.get("encoding"),
            "content_sha256": content_hash,
        }
        text = f"File write on {server.name}: {payload['path']} ({payload['size']} bytes, sha256={content_hash[:12]})"
        return NodeResult(output={"output": text, "file": payload})


@registry.register
class OpsPackageActionNode(BaseNode):
    node_type = "ops/package_action"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        config = self.node_data
        server = await _load_owned_server(ctx, config)
        secret = await _server_secret(server)
        action = str(config.get("action") or "list_updates").strip().lower()
        if action not in PACKAGE_ACTIONS:
            return NodeResult(error="Unsupported package action")

        if action == "list_updates":
            packages = await get_linux_ui_packages(server, secret=secret)
            payload = {
                "server": {"id": server.id, "name": server.name, "host": server.host},
                "action": "list_updates",
                **packages,
            }
            update_candidates = (payload.get("summary") or {}).get("update_candidates", 0)
            text = f"Package update check for {server.name}: {update_candidates} update candidate(s)"
            return NodeResult(output={"output": text, "packages": payload})

        try:
            raw_packages = config.get("packages")
            if isinstance(raw_packages, list):
                resolved_packages = [ctx.resolve_template(str(item or "")) for item in raw_packages]
            else:
                resolved_packages = ctx.resolve_template(str(raw_packages or ""))
            package_names = _normalise_packages(resolved_packages)
        except ValueError as exc:
            return NodeResult(error=str(exc))
        if not package_names:
            return NodeResult(error="packages are required for mutating package actions")

        capabilities = await get_linux_ui_capabilities(server, secret=secret)
        package_manager = str(capabilities.get("package_manager") or "")
        if package_manager not in {"apt", "dnf", "yum"}:
            return NodeResult(error="No supported package manager found")
        try:
            command = _package_command(package_manager, action, package_names)
        except ValueError as exc:
            return NodeResult(error=str(exc))

        result = await _run_command_result(
            server,
            secret=secret,
            command=(
                f"{command} 2>&1\n"
                "action_exit=$?\n"
                "printf '\\n__ACTION_EXIT__=%s\\n' \"$action_exit\"\n"
            ),
        )
        combined_output = f"{result.get('stdout') or ''}{result.get('stderr') or ''}"
        action_exit = _coerce_int(result.get("exit_code")) or 0
        exit_match = re.search(r"__ACTION_EXIT__=(\d+)", combined_output)
        if exit_match:
            action_exit = int(exit_match.group(1))
        verification = await get_linux_ui_packages(server, secret=secret) if _coerce_bool(config.get("verify"), default=True) else {}
        payload = {
            "server": {"id": server.id, "name": server.name, "host": server.host},
            "action": action,
            "package_manager": package_manager,
            "packages": package_names,
            "success": action_exit == 0,
            "exit_code": action_exit,
            "output_excerpt": combined_output[:3000],
            "verification_summary": verification.get("summary") if isinstance(verification, dict) else {},
        }
        status_text = "completed" if payload["success"] else "failed"
        text = f"Package action {action} on {server.name}: {status_text} ({', '.join(package_names)})\n\n```text\n{payload['output_excerpt']}\n```"
        if payload["success"]:
            return NodeResult(output={"output": text, "package_action": payload})
        return NodeResult(error=payload["output_excerpt"] or "Package action failed", output={"output": text, "package_action": payload})


@registry.register
class OpsServerSnapshotNode(BaseNode):
    node_type = "ops/server_snapshot"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        config = self.node_data
        server = await _load_owned_server(ctx, config)
        secret = await _server_secret(server)
        raw_sections = _coerce_list(config.get("sections")) or ["overview", "services", "docker", "disk"]
        sections = [str(item).strip().lower() for item in raw_sections if str(item).strip().lower() in SERVER_SNAPSHOT_SECTIONS]
        if not sections:
            sections = ["overview"]

        limit = _coerce_int(config.get("limit")) or 80
        lines = _coerce_int(config.get("lines")) or 80
        service = ctx.resolve_template(str(config.get("service") or ""))
        log_source = str(config.get("log_source") or "journal").strip().lower() or "journal"
        payload: dict[str, Any] = {"server": {"id": server.id, "name": server.name, "host": server.host}, "sections": {}}

        if "overview" in sections:
            payload["sections"]["overview"] = await get_linux_ui_overview(server, secret=secret)
        if "services" in sections:
            payload["sections"]["services"] = await get_linux_ui_services(server, secret=secret, limit=limit)
        if "processes" in sections:
            payload["sections"]["processes"] = await get_linux_ui_processes(server, secret=secret, limit=limit)
        if "docker" in sections:
            payload["sections"]["docker"] = await get_linux_ui_docker(server, secret=secret)
        if "logs" in sections:
            payload["sections"]["logs"] = await get_linux_ui_logs(server, secret=secret, source=log_source, lines=lines, service=service)
        if "disk" in sections:
            payload["sections"]["disk"] = await get_linux_ui_disk(server, secret=secret)
        if "network" in sections:
            payload["sections"]["network"] = await get_linux_ui_network(server, secret=secret)
        if "packages" in sections:
            payload["sections"]["packages"] = await get_linux_ui_packages(server, secret=secret)

        text = f"Server snapshot for {server.name} ({server.host})\n\n```json\n{_compact_json(payload)}\n```"
        return NodeResult(output={"output": text, "snapshot": payload})


@registry.register
class OpsDiskCleanupNode(BaseNode):
    node_type = "ops/disk_cleanup"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        config = self.node_data
        server = await _load_owned_server(ctx, config)
        secret = await _server_secret(server)
        action = str(config.get("action") or "inspect").strip().lower()
        if action not in DISK_CLEANUP_ACTIONS:
            return NodeResult(error="Unsupported disk cleanup action")

        before = await get_linux_ui_disk(server, secret=secret)
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

        result = await _run_command_result(
            server,
            secret=secret,
            command=(
                f"{command}\n"
                "action_exit=$?\n"
                "printf '\\n__ACTION_EXIT__=%s\\n' \"$action_exit\"\n"
            ),
        )
        combined_output = f"{result.get('stdout') or ''}{result.get('stderr') or ''}"
        action_exit = _coerce_int(result.get("exit_code")) or 0
        exit_match = re.search(r"__ACTION_EXIT__=(\d+)", combined_output)
        if exit_match:
            action_exit = int(exit_match.group(1))
        plan_text = combined_output.partition("__PLAN__\n")[2].partition("__ACTION__\n")[0].strip()
        action_text = combined_output.partition("__ACTION__\n")[2].partition("__ACTION_EXIT__=")[0].strip()
        after = await get_linux_ui_disk(server, secret=secret) if verify else {}
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
        text = f"Disk cleanup {action} on {server.name}: {status_text}\n\n```text\n{payload['action_excerpt'] or payload['plan_excerpt']}\n```"
        if payload["success"]:
            return NodeResult(output={"output": text, "disk_cleanup": payload})
        return NodeResult(error=payload["action_excerpt"] or "Disk cleanup failed", output={"output": text, "disk_cleanup": payload})


@registry.register
class OpsBackupRestoreCheckNode(BaseNode):
    node_type = "ops/backup_restore_check"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        config = self.node_data
        server = await _load_owned_server(ctx, config)
        secret = await _server_secret(server)
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

        result = await _run_command_result(server, secret=secret, command=command)
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
        text = f"Backup restore check {action} on {server.name}: {status_text}\n\n```json\n{_compact_json(payload)}\n```"
        if verification["success"]:
            return NodeResult(output={"output": text, "backup_restore_check": payload})
        return NodeResult(error=verification["output_excerpt"] or "Backup verification failed", output={"output": text, "backup_restore_check": payload})


@registry.register
class OpsServiceActionNode(BaseNode):
    node_type = "ops/service_action"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        config = self.node_data
        action = str(config.get("action") or "restart").strip().lower()
        if action not in SERVICE_ACTIONS:
            return NodeResult(error="Unsupported service action")
        return await _execute_service_action(
            ctx,
            config,
            load_owned_server=_load_owned_server,
            server_secret=_server_secret,
            resolve_context_key=_resolve_context_key,
            get_service_logs=get_linux_ui_service_logs,
            run_service_action=run_linux_ui_service_action,
        )


@registry.register
class OpsDockerActionNode(BaseNode):
    node_type = "ops/docker_action"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        config = self.node_data
        action = str(config.get("action") or "restart").strip().lower()
        if action not in DOCKER_ACTIONS:
            return NodeResult(error="Unsupported docker action")
        return await _execute_docker_action(
            ctx,
            config,
            load_owned_server=_load_owned_server,
            server_secret=_server_secret,
            get_docker=get_linux_ui_docker,
            get_docker_logs=get_linux_ui_docker_logs,
            run_docker_action=run_linux_ui_docker_action,
        )


@registry.register
class OpsProcessActionNode(BaseNode):
    node_type = "ops/process_action"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        config = self.node_data
        action = str(config.get("action") or "terminate").strip().lower()
        if action not in PROCESS_ACTIONS:
            return NodeResult(error="Unsupported process action")
        return await _execute_process_action(
            ctx,
            config,
            load_owned_server=_load_owned_server,
            server_secret=_server_secret,
            resolve_context_key=_resolve_context_key,
            run_process_action=run_linux_ui_process_action,
        )


@registry.register
class OpsHttpCheckNode(BaseNode):
    node_type = "ops/http_check"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        return await _execute_http_check(ctx, self.node_data, async_client_factory=httpx.AsyncClient)

@registry.register
class OpsAlertUpdateNode(BaseNode):
    node_type = "ops/alert_update"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        config = self.node_data
        action = str(config.get("action") or "resolve").strip().lower()
        if action not in ALERT_ACTIONS:
            return NodeResult(error="Unsupported alert action")
        return await _execute_alert_update(
            ctx,
            config,
            ops_runtime=_ops_runtime,
            resolve_context_key=_resolve_context_key,
        )
