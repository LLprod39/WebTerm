from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING, Any

import httpx  # noqa: F401 — re-exported for OpsHttpCheckNode monkeypatches

from studio.executor.change_preview import build_change_preview
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
from studio.executor.nodes.ops_context import load_owned_server as _load_owned_server
from studio.executor.nodes.ops_context import resolve_context_key as _resolve_context_key
from studio.executor.nodes.ops_context import server_secret as _server_secret
from studio.executor.nodes.ops_helpers import (
    DOCKER_ACTIONS,
    FILE_ACTIONS,
    PACKAGE_ACTIONS,
    PROCESS_ACTIONS,
    SERVER_SNAPSHOT_SECTIONS,
    SERVICE_ACTIONS,
)
from studio.executor.nodes.ops_helpers import coerce_bool as _coerce_bool
from studio.executor.nodes.ops_helpers import coerce_int as _coerce_int
from studio.executor.nodes.ops_helpers import coerce_list as _coerce_list
from studio.executor.nodes.ops_helpers import compact_json as _compact_json
from studio.executor.nodes.ops_helpers import normalise_packages as _normalise_packages
from studio.executor.nodes.ops_helpers import package_command as _package_command
from studio.executor.nodes.ops_nodes_extra import (  # noqa: F401
    OpsAlertUpdateNode,
    OpsBackupRestoreCheckNode,
    OpsDiskCleanupNode,
    OpsHttpCheckNode,
)
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
    run_command_result as _run_command_result,
)
from studio.executor.registry import registry

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


logger = logging.getLogger(__name__)


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
        dry_run = _coerce_bool(config.get("dry_run"), default=False)
        if dry_run:
            try:
                existing = await read_text_file(server, secret=secret, path=path, max_bytes=max_bytes)
            except Exception as exc:
                logger.info(
                    "File dry-run could not read existing target on server %s (%s); treating it as unavailable",
                    server.id,
                    type(exc).__name__,
                )
                existing = {"path": path, "size": None, "exists": None}
            result = {
                "path": existing.get("path") or path,
                "filename": existing.get("filename") or path.rsplit("/", 1)[-1],
                "size": len(content.encode("utf-8")),
                "encoding": "utf-8",
                "previous_content": existing.get("content") if "content" in existing else None,
                "previous_size": existing.get("size"),
                "existed": existing.get("exists", True),
            }
        else:
            result = await write_text_file(server, secret=secret, path=path, content=content, max_bytes=max_bytes)
        content_hash = hashlib.sha256(str(content).encode("utf-8")).hexdigest()
        previous_content = result.get("previous_content")
        before = (
            previous_content
            if isinstance(previous_content, str)
            else ""
            if result.get("existed") is False
            else {"state": "unavailable"}
        )
        change_preview = build_change_preview(
            operation="file.write",
            target={"server_id": server.id, "path": result.get("path") or path},
            before=before,
            after=content,
            dry_run=dry_run,
        )
        payload = {
            "server": {"id": server.id, "name": server.name, "host": server.host},
            "action": "write",
            "path": result.get("path"),
            "filename": result.get("filename"),
            "size": result.get("size"),
            "encoding": result.get("encoding"),
            "content_sha256": content_hash,
            "dry_run": dry_run,
            "existed": bool(result.get("existed")),
        }
        status_text = "preview" if dry_run else "completed"
        text = (
            f"File write {status_text} on {server.name}: {payload['path']} "
            f"({payload['size']} bytes, sha256={content_hash[:12]})\n\n```diff\n{change_preview['diff']}\n```"
        )
        return NodeResult(output={"output": text, "file": payload, "change_preview": change_preview})


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

        dry_run = _coerce_bool(config.get("dry_run"), default=False)
        before = await get_linux_ui_packages(server, secret=secret)
        if dry_run:
            combined_output = ""
            action_exit: int | None = None
            verification: dict[str, Any] = {}
        else:
            result = await _run_command_result(
                server,
                secret=secret,
                command=(f"{command} 2>&1\naction_exit=$?\nprintf '\\n__ACTION_EXIT__=%s\\n' \"$action_exit\"\n"),
            )
            combined_output = f"{result.get('stdout') or ''}{result.get('stderr') or ''}"
            action_exit = _coerce_int(result.get("exit_code")) or 0
            exit_match = re.search(r"__ACTION_EXIT__=(\d+)", combined_output)
            if exit_match:
                action_exit = int(exit_match.group(1))
            verification = (
                await get_linux_ui_packages(server, secret=secret)
                if _coerce_bool(config.get("verify"), default=True)
                else {}
            )
        planned_after = {
            "package_manager": package_manager,
            "requested_action": action,
            "requested_packages": package_names,
        }
        change_preview = build_change_preview(
            operation=f"package.{action}",
            target={"server_id": server.id, "packages": package_names},
            before=before,
            after=verification or planned_after,
            dry_run=dry_run,
        )
        payload = {
            "server": {"id": server.id, "name": server.name, "host": server.host},
            "action": action,
            "package_manager": package_manager,
            "packages": package_names,
            "success": dry_run or action_exit == 0,
            "exit_code": action_exit,
            "output_excerpt": combined_output[:3000],
            "verification_summary": verification.get("summary") if isinstance(verification, dict) else {},
            "dry_run": dry_run,
        }
        status_text = "preview" if dry_run else "completed" if payload["success"] else "failed"
        text = (
            f"Package action {action} on {server.name}: {status_text} ({', '.join(package_names)})"
            f"\n\n```diff\n{change_preview['diff']}\n```"
        )
        if payload["success"]:
            return NodeResult(output={"output": text, "package_action": payload, "change_preview": change_preview})
        return NodeResult(
            error=payload["output_excerpt"] or "Package action failed",
            output={"output": text, "package_action": payload, "change_preview": change_preview},
        )


@registry.register
class OpsServerSnapshotNode(BaseNode):
    node_type = "ops/server_snapshot"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        config = self.node_data
        server = await _load_owned_server(ctx, config)
        secret = await _server_secret(server)
        raw_sections = _coerce_list(config.get("sections")) or ["overview", "services", "docker", "disk"]
        sections = [
            str(item).strip().lower() for item in raw_sections if str(item).strip().lower() in SERVER_SNAPSHOT_SECTIONS
        ]
        if not sections:
            sections = ["overview"]

        limit = _coerce_int(config.get("limit")) or 80
        lines = _coerce_int(config.get("lines")) or 80
        service = ctx.resolve_template(str(config.get("service") or ""))
        log_source = str(config.get("log_source") or "journal").strip().lower() or "journal"
        payload: dict[str, Any] = {
            "server": {"id": server.id, "name": server.name, "host": server.host},
            "sections": {},
        }

        if "overview" in sections:
            payload["sections"]["overview"] = await get_linux_ui_overview(server, secret=secret)
        if "services" in sections:
            payload["sections"]["services"] = await get_linux_ui_services(server, secret=secret, limit=limit)
        if "processes" in sections:
            payload["sections"]["processes"] = await get_linux_ui_processes(server, secret=secret, limit=limit)
        if "docker" in sections:
            payload["sections"]["docker"] = await get_linux_ui_docker(server, secret=secret)
        if "logs" in sections:
            payload["sections"]["logs"] = await get_linux_ui_logs(
                server, secret=secret, source=log_source, lines=lines, service=service
            )
        if "disk" in sections:
            payload["sections"]["disk"] = await get_linux_ui_disk(server, secret=secret)
        if "network" in sections:
            payload["sections"]["network"] = await get_linux_ui_network(server, secret=secret)
        if "packages" in sections:
            payload["sections"]["packages"] = await get_linux_ui_packages(server, secret=secret)

        text = f"Server snapshot for {server.name} ({server.host})\n\n```json\n{_compact_json(payload)}\n```"
        return NodeResult(output={"output": text, "snapshot": payload})


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
