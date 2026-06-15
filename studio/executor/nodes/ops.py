from __future__ import annotations

import json
import hashlib
import re
import shlex
from typing import TYPE_CHECKING, Any

import httpx
from asgiref.sync import sync_to_async

from servers.linux_ui import (
    LOG_SOURCES,
    _run_command_result,
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
    run_linux_ui_docker_action,
    run_linux_ui_process_action,
    run_linux_ui_service_action,
)
from servers.sftp import read_text_file, write_text_file
from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry
from studio.services import get_owned_server

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext

SERVER_SNAPSHOT_SECTIONS = {
    "overview",
    "services",
    "processes",
    "docker",
    "logs",
    "disk",
    "network",
    "packages",
}
SERVICE_ACTIONS = {"start", "stop", "restart", "reload"}
DOCKER_ACTIONS = {"start", "stop", "restart"}
PROCESS_ACTIONS = {"terminate", "kill_force"}
ALERT_ACTIONS = {"resolve"}
FILE_ACTIONS = {"read", "write"}
PACKAGE_ACTIONS = {"list_updates", "install", "update", "remove"}
DISK_CLEANUP_ACTIONS = {"inspect", "journal_vacuum", "tmp_cleanup"}
BACKUP_RESTORE_CHECK_ACTIONS = {"inspect", "verify_latest"}
PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:@~/-]{0,127}$")
LOG_QUERY_SOURCES = set(LOG_SOURCES) | {"docker"}


def _compact_json(value: Any, *, limit: int = 3500) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n..."


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _coerce_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _normalise_packages(value: Any) -> list[str]:
    source_items = value if isinstance(value, list) else [value]
    raw_items: list[str] = []
    for item in source_items:
        raw_items.extend(part for part in re.split(r"[\s,]+", str(item or "")) if part)
    packages: list[str] = []
    for item in raw_items:
        package = str(item or "").strip()
        if not package:
            continue
        if not PACKAGE_NAME_RE.fullmatch(package):
            raise ValueError(f"Invalid package name: {package}")
        if package not in packages:
            packages.append(package)
    return packages


def _package_command(package_manager: str, action: str, packages: list[str]) -> str:
    quoted = " ".join(shlex.quote(package) for package in packages)
    if package_manager == "apt":
        if action == "install":
            return f"DEBIAN_FRONTEND=noninteractive apt-get install -y -- {quoted}"
        if action == "update":
            return f"DEBIAN_FRONTEND=noninteractive apt-get install --only-upgrade -y -- {quoted}"
        if action == "remove":
            return f"DEBIAN_FRONTEND=noninteractive apt-get remove -y -- {quoted}"
    if package_manager in {"dnf", "yum"} and action in {"install", "update", "remove"}:
        return f"{package_manager} -y {action} {quoted}"
    raise ValueError("Unsupported package action")


def _disk_cleanup_command(action: str, *, min_age_days: int, max_entries: int, dry_run: bool, vacuum_time_days: int, vacuum_size_mb: int | None) -> str:
    dry = "1" if dry_run else "0"
    if action == "journal_vacuum":
        vacuum_args = [f"--vacuum-time={vacuum_time_days}d"]
        if vacuum_size_mb:
            vacuum_args.append(f"--vacuum-size={vacuum_size_mb}M")
        command = "journalctl " + " ".join(vacuum_args)
        return (
            "set -u\n"
            "printf '__PLAN__\\n'\n"
            "journalctl --disk-usage 2>&1 || true\n"
            f"printf 'planned_command=%s\\n' {shlex.quote(command)}\n"
            "printf '__ACTION__\\n'\n"
            f"if [ {dry} -eq 1 ]; then printf 'dry_run=true\\n'; else {command} 2>&1; fi\n"
        )
    if action == "tmp_cleanup":
        return (
            "set -u\n"
            "printf '__PLAN__\\n'\n"
            f"find /tmp /var/tmp -xdev -mindepth 1 -mtime +{min_age_days} -print 2>/dev/null | head -n {max_entries}\n"
            "printf '__ACTION__\\n'\n"
            f"if [ {dry} -eq 1 ]; then printf 'dry_run=true\\n'; "
            "else "
            f"find /tmp /var/tmp -xdev -mindepth 1 -mtime +{min_age_days} -print 2>/dev/null | head -n {max_entries} | "
            "while IFS= read -r path; do "
            "case \"$path\" in /tmp/*|/var/tmp/*) rm -rf -- \"$path\" && printf 'removed=%s\\n' \"$path\" ;; *) printf 'skipped=%s\\n' \"$path\" ;; esac; "
            "done; "
            "fi\n"
        )
    raise ValueError("Unsupported disk cleanup action")


def _backup_restore_check_command(path: str, *, action: str, max_depth: int, max_files: int) -> str:
    quoted_path = shlex.quote(path)
    return (
        "set -u\n"
        f"BACKUP_DIR={quoted_path}\n"
        f"MAX_DEPTH={max_depth}\n"
        f"MAX_FILES={max_files}\n"
        "printf '__FILES__\\n'\n"
        "if [ ! -d \"$BACKUP_DIR\" ]; then printf 'missing_dir\\t0\\t%s\\n' \"$BACKUP_DIR\"; exit 0; fi\n"
        "find \"$BACKUP_DIR\" -maxdepth \"$MAX_DEPTH\" -type f -printf '%T@\\t%s\\t%p\\n' 2>/dev/null | sort -nr | head -n \"$MAX_FILES\"\n"
        "printf '__VERIFY__\\n'\n"
        f"if [ {1 if action == 'verify_latest' else 0} -eq 0 ]; then printf 'verification=skipped\\n'; exit 0; fi\n"
        "latest=$(find \"$BACKUP_DIR\" -maxdepth \"$MAX_DEPTH\" -type f -printf '%T@\\t%s\\t%p\\n' 2>/dev/null | sort -nr | head -n 1 | cut -f3-)\n"
        "if [ -z \"$latest\" ]; then printf 'verification=no_files\\n'; exit 3; fi\n"
        "printf 'latest=%s\\n' \"$latest\"\n"
        "case \"$latest\" in\n"
        "  *.tar) tar -tf \"$latest\" >/dev/null 2>&1 ;;\n"
        "  *.tar.gz|*.tgz) tar -tzf \"$latest\" >/dev/null 2>&1 ;;\n"
        "  *.gz) gzip -t \"$latest\" >/dev/null 2>&1 ;;\n"
        "  *.zip) if command -v unzip >/dev/null 2>&1; then unzip -t \"$latest\" >/dev/null 2>&1; else printf 'verification=missing_unzip\\n'; exit 4; fi ;;\n"
        "  *) printf 'verification=unsupported_extension\\n'; exit 2 ;;\n"
        "esac\n"
        "status=$?\n"
        "printf 'verification_exit=%s\\n' \"$status\"\n"
        "exit \"$status\"\n"
    )


def _parse_backup_file_rows(raw: str, *, max_age_hours: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import time

    files: list[dict[str, Any]] = []
    missing_dir = ""
    now = time.time()
    for line in str(raw or "").splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        if parts[0] == "missing_dir":
            missing_dir = parts[2]
            continue
        try:
            mtime = float(parts[0])
            size = int(float(parts[1]))
        except (TypeError, ValueError):
            continue
        age_hours = max(0.0, (now - mtime) / 3600)
        files.append(
            {
                "path": parts[2],
                "size_bytes": size,
                "size_mb": round(size / (1024 * 1024), 2),
                "mtime_epoch": mtime,
                "age_hours": round(age_hours, 2),
            }
        )
    latest = files[0] if files else None
    summary = {
        "file_count": len(files),
        "latest_path": latest.get("path") if latest else "",
        "latest_age_hours": latest.get("age_hours") if latest else None,
        "latest_size_mb": latest.get("size_mb") if latest else None,
        "fresh": bool(latest and float(latest.get("age_hours") or 0) <= max_age_hours),
        "max_age_hours": max_age_hours,
        "missing_dir": missing_dir,
    }
    return files, summary


def _resolve_context_key(ctx: "ExecutionContext", config: dict[str, Any], field: str, default_key: str = "") -> Any:
    direct = config.get(field)
    if direct not in (None, ""):
        if isinstance(direct, str):
            return ctx.resolve_template(direct)
        return direct
    key = str(config.get(f"{field}_context_key") or default_key or field).strip()
    return ctx.get_variable(key, "") if key else ""


async def _load_owned_server(ctx: "ExecutionContext", config: dict[str, Any]):
    server_id = _coerce_int(_resolve_context_key(ctx, config, "server_id", "server_id"))
    if not server_id:
        raise ValueError("server_id is required or must be present in pipeline context.")
    server = await sync_to_async(get_owned_server)(ctx.user, server_id)
    if server is None:
        raise ValueError(f"Server not found or inaccessible: {server_id}")
    return server


async def _server_secret(server) -> str:
    from servers.monitor import _decrypt_server_secret

    return await sync_to_async(_decrypt_server_secret, thread_sensitive=True)(server)


@registry.register
class OpsLogQueryNode(BaseNode):
    node_type = "ops/log_query"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        config = self.node_data
        server = await _load_owned_server(ctx, config)
        secret = await _server_secret(server)
        source = str(config.get("source") or "journal").strip().lower()
        if source not in LOG_QUERY_SOURCES:
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

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
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

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
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

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
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

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
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

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
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

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        config = self.node_data
        server = await _load_owned_server(ctx, config)
        secret = await _server_secret(server)
        service = ctx.resolve_template(str(config.get("service") or ""))
        action = str(config.get("action") or "restart").strip().lower()
        if action not in SERVICE_ACTIONS:
            return NodeResult(error="Unsupported service action")
        if not service.strip():
            return NodeResult(error="service is required")

        preflight = await get_linux_ui_service_logs(server, secret=secret, service=service, lines=40)
        result = await run_linux_ui_service_action(server, secret=secret, service=service, action=action)
        verify = None
        if _coerce_bool(config.get("verify"), default=True):
            verify = await get_linux_ui_service_logs(server, secret=secret, service=service, lines=40)
        output = {
            "server": server.name,
            "service": result.get("service") or service,
            "action": action,
            "success": bool(result.get("success")),
            "dangerous": bool(result.get("dangerous")),
            "preflight_source": preflight.get("source"),
            "status_excerpt": result.get("status_excerpt") or result.get("output") or "",
            "verification_source": (verify or {}).get("source"),
        }
        status_text = "completed" if output["success"] else "failed"
        text = f"Service action {action} {output['service']} on {server.name}: {status_text}\n\n```json\n{_compact_json(output)}\n```"
        if output["success"]:
            return NodeResult(output={"output": text, "action_result": output})
        return NodeResult(error=str(result.get("output") or "Service action failed"), output={"output": text, "action_result": output})


@registry.register
class OpsDockerActionNode(BaseNode):
    node_type = "ops/docker_action"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        config = self.node_data
        server = await _load_owned_server(ctx, config)
        secret = await _server_secret(server)
        container = ctx.resolve_template(str(config.get("container") or ctx.get_variable("container_name", "")))
        action = str(config.get("action") or "restart").strip().lower()
        if action not in DOCKER_ACTIONS:
            return NodeResult(error="Unsupported docker action")
        if not container.strip():
            return NodeResult(error="container is required")

        before = await get_linux_ui_docker(server, secret=secret)
        result = await run_linux_ui_docker_action(server, secret=secret, container=container, action=action)
        after = await get_linux_ui_docker(server, secret=secret) if _coerce_bool(config.get("verify"), default=True) else None
        logs = None
        if _coerce_bool(config.get("include_logs"), default=True):
            logs = await get_linux_ui_docker_logs(server, secret=secret, container=container, lines=_coerce_int(config.get("lines")) or 80)
        output = {
            "server": server.name,
            "container": result.get("container") or container,
            "action": action,
            "success": bool(result.get("success")),
            "dangerous": bool(result.get("dangerous")),
            "before_summary": before.get("summary"),
            "after_summary": (after or {}).get("summary"),
            "inspect_excerpt": result.get("inspect_excerpt") or "",
            "logs_excerpt": (logs or {}).get("content", "")[:1500],
        }
        status_text = "completed" if output["success"] else "failed"
        text = f"Docker action {action} {output['container']} on {server.name}: {status_text}\n\n```json\n{_compact_json(output)}\n```"
        if output["success"]:
            return NodeResult(output={"output": text, "action_result": output})
        return NodeResult(error=str(result.get("output") or "Docker action failed"), output={"output": text, "action_result": output})


@registry.register
class OpsProcessActionNode(BaseNode):
    node_type = "ops/process_action"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        config = self.node_data
        server = await _load_owned_server(ctx, config)
        secret = await _server_secret(server)
        pid = _resolve_context_key(ctx, config, "pid", "pid")
        action = str(config.get("action") or "terminate").strip().lower()
        if action not in PROCESS_ACTIONS:
            return NodeResult(error="Unsupported process action")
        result = await run_linux_ui_process_action(server, secret=secret, pid=pid, action=action)
        output = {
            "server": server.name,
            "pid": result.get("pid"),
            "action": action,
            "success": bool(result.get("success")),
            "dangerous": bool(result.get("dangerous")),
            "still_running": bool(result.get("still_running")),
            "process_excerpt": result.get("process_excerpt") or "",
        }
        text = f"Process action {action} PID {output['pid']} on {server.name}: {'completed' if output['success'] else 'failed'}\n\n```json\n{_compact_json(output)}\n```"
        if output["success"]:
            return NodeResult(output={"output": text, "action_result": output})
        return NodeResult(error=str(result.get("output") or "Process action failed"), output={"output": text, "action_result": output})


@registry.register
class OpsHttpCheckNode(BaseNode):
    node_type = "ops/http_check"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        config = self.node_data
        url = ctx.resolve_template(str(config.get("url") or ""))
        if not url:
            return NodeResult(error="url is required")
        method = str(config.get("method") or "GET").strip().upper()
        if method not in {"GET", "HEAD"}:
            return NodeResult(error="method must be GET or HEAD")
        expected_status = [_coerce_int(item) for item in _coerce_list(config.get("expected_status"))]
        expected = {item for item in expected_status if item is not None} or set(range(200, 400))
        timeout = max(1, min(_coerce_int(config.get("timeout_seconds")) or 15, 120))
        retries = max(1, min(_coerce_int(config.get("retries")) or 1, 5))
        body_contains = ctx.resolve_template(str(config.get("body_contains") or ""))
        last_error = ""
        response_payload: dict[str, Any] = {}

        for attempt in range(1, retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    response = await client.request(method, url)
                body = response.text[:2000] if method != "HEAD" else ""
                response_payload = {
                    "url": url,
                    "method": method,
                    "status_code": response.status_code,
                    "attempt": attempt,
                    "body_excerpt": body,
                }
                if response.status_code not in expected:
                    last_error = f"Unexpected status {response.status_code}"
                    continue
                if body_contains and body_contains not in body:
                    last_error = "Expected body text was not found"
                    continue
                text = f"HTTP check passed: {method} {url} -> {response.status_code}"
                return NodeResult(output={"output": text, "http_check": response_payload})
            except Exception as exc:
                last_error = str(exc)
                response_payload = {"url": url, "method": method, "attempt": attempt, "error": last_error}

        return NodeResult(
            error=last_error or "HTTP check failed",
            output={"output": f"HTTP check failed: {method} {url}: {last_error}", "http_check": response_payload},
        )


@registry.register
class OpsAlertUpdateNode(BaseNode):
    node_type = "ops/alert_update"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        from django.utils import timezone
        from servers.models import ServerAlert

        config = self.node_data
        action = str(config.get("action") or "resolve").strip().lower()
        if action not in ALERT_ACTIONS:
            return NodeResult(error="Unsupported alert action")
        alert_id = _coerce_int(_resolve_context_key(ctx, config, "alert_id", "alert_id"))
        if not alert_id:
            return NodeResult(error="alert_id is required or must be present in pipeline context")

        def _resolve_alert():
            alert = ServerAlert.objects.select_related("server").filter(id=alert_id, server__user=ctx.user).first()
            if alert is None:
                return None
            if action == "resolve":
                alert.is_resolved = True
                alert.resolved_at = timezone.now()
                alert.resolved_by = ctx.user if getattr(ctx.user, "is_authenticated", False) else None
                alert.save(update_fields=["is_resolved", "resolved_at", "resolved_by"])
            return alert

        alert = await sync_to_async(_resolve_alert, thread_sensitive=True)()
        if alert is None:
            return NodeResult(error=f"Alert not found or inaccessible: {alert_id}")
        output = {
            "alert_id": alert.id,
            "action": action,
            "title": alert.title,
            "server": alert.server.name,
            "is_resolved": alert.is_resolved,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "note": ctx.resolve_template(str(config.get("note") or "")),
        }
        return NodeResult(output={"output": f"Alert #{alert.id} {action}: {alert.title}", "alert": output})
