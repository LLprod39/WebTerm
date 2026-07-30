from __future__ import annotations

from typing import TYPE_CHECKING, Any

from studio.executor.change_preview import build_change_preview
from studio.executor.nodes.base import NodeResult
from studio.executor.nodes.ops_helpers import coerce_bool as _coerce_bool
from studio.executor.nodes.ops_helpers import coerce_int as _coerce_int

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


async def execute_service_action(
    ctx: ExecutionContext,
    config: dict[str, Any],
    *,
    load_owned_server: Any,
    server_secret: Any,
    resolve_context_key: Any,
    get_service_logs: Any,
    run_service_action: Any,
) -> NodeResult:
    server = await load_owned_server(ctx, config)
    secret = await server_secret(server)
    service = ctx.resolve_template(str(resolve_context_key(ctx, config, "service", "service_name") or ""))
    action = str(config.get("action") or "restart").strip().lower()
    if not service.strip():
        return NodeResult(error="service is required or must be present in pipeline context")

    preflight = await get_service_logs(server, secret=secret, service=service, lines=40)
    dry_run = _coerce_bool(config.get("dry_run"), default=False)
    if dry_run:
        result = {"service": service, "success": True, "dangerous": False, "status_excerpt": ""}
        verify = None
    else:
        result = await run_service_action(server, secret=secret, service=service, action=action)
        verify = None
        if _coerce_bool(config.get("verify"), default=True):
            verify = await get_service_logs(server, secret=secret, service=service, lines=40)
    desired_state = {
        "service": service,
        "requested_action": action,
        "desired_state": {"start": "active", "stop": "inactive", "restart": "active", "reload": "active"}[action],
    }
    change_preview = build_change_preview(
        operation=f"service.{action}",
        target={"server_id": server.id, "service": service},
        before=preflight,
        after=verify or desired_state,
        dry_run=dry_run,
    )
    output = {
        "server": server.name,
        "service": result.get("service") or service,
        "action": action,
        "success": bool(result.get("success")),
        "dangerous": bool(result.get("dangerous")),
        "preflight_source": preflight.get("source"),
        "status_excerpt": result.get("status_excerpt") or result.get("output") or "",
        "verification_source": (verify or {}).get("source"),
        "dry_run": dry_run,
    }
    status_text = "preview" if dry_run else "completed" if output["success"] else "failed"
    text = (
        f"Service action {action} {output['service']} on {server.name}: {status_text}"
        f"\n\n```diff\n{change_preview['diff']}\n```"
    )
    if output["success"]:
        return NodeResult(output={"output": text, "action_result": output, "change_preview": change_preview})
    return NodeResult(
        error=str(result.get("output") or "Service action failed"),
        output={"output": text, "action_result": output, "change_preview": change_preview},
    )


async def execute_docker_action(
    ctx: ExecutionContext,
    config: dict[str, Any],
    *,
    load_owned_server: Any,
    server_secret: Any,
    get_docker: Any,
    get_docker_logs: Any,
    run_docker_action: Any,
) -> NodeResult:
    server = await load_owned_server(ctx, config)
    secret = await server_secret(server)
    container = ctx.resolve_template(str(config.get("container") or ctx.get_variable("container_name", "")))
    action = str(config.get("action") or "restart").strip().lower()
    if not container.strip():
        return NodeResult(error="container is required")

    before = await get_docker(server, secret=secret)
    dry_run = _coerce_bool(config.get("dry_run"), default=False)
    if dry_run:
        result = {"container": container, "success": True, "dangerous": False}
        after = None
        logs = None
    else:
        result = await run_docker_action(server, secret=secret, container=container, action=action)
        after = await get_docker(server, secret=secret) if _coerce_bool(config.get("verify"), default=True) else None
        logs = None
        if _coerce_bool(config.get("include_logs"), default=True):
            logs = await get_docker_logs(
                server, secret=secret, container=container, lines=_coerce_int(config.get("lines")) or 80
            )
    desired_state = {
        "container": container,
        "requested_action": action,
        "desired_state": {"start": "running", "stop": "stopped", "restart": "running"}[action],
    }
    change_preview = build_change_preview(
        operation=f"docker.{action}",
        target={"server_id": server.id, "container": container},
        before=before,
        after=after or desired_state,
        dry_run=dry_run,
    )
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
        "dry_run": dry_run,
    }
    status_text = "preview" if dry_run else "completed" if output["success"] else "failed"
    text = (
        f"Docker action {action} {output['container']} on {server.name}: {status_text}"
        f"\n\n```diff\n{change_preview['diff']}\n```"
    )
    if output["success"]:
        return NodeResult(output={"output": text, "action_result": output, "change_preview": change_preview})
    return NodeResult(
        error=str(result.get("output") or "Docker action failed"),
        output={"output": text, "action_result": output, "change_preview": change_preview},
    )


async def execute_process_action(
    ctx: ExecutionContext,
    config: dict[str, Any],
    *,
    load_owned_server: Any,
    server_secret: Any,
    resolve_context_key: Any,
    run_process_action: Any,
) -> NodeResult:
    server = await load_owned_server(ctx, config)
    secret = await server_secret(server)
    pid = _coerce_int(resolve_context_key(ctx, config, "pid", "pid"))
    action = str(config.get("action") or "terminate").strip().lower()
    if pid is None or pid <= 1:
        return NodeResult(error="pid must be an integer greater than 1")
    dry_run = _coerce_bool(config.get("dry_run"), default=False)
    if dry_run:
        result = {"pid": pid, "success": True, "dangerous": action == "kill_force", "still_running": True}
    else:
        result = await run_process_action(server, secret=secret, pid=pid, action=action)
    before = {"pid": pid, "state": "running"}
    after = {
        "pid": pid,
        "requested_action": action,
        "state": "would_signal" if dry_run else "running" if result.get("still_running") else "stopped",
    }
    change_preview = build_change_preview(
        operation=f"process.{action}",
        target={"server_id": server.id, "pid": pid},
        before=before,
        after=after,
        dry_run=dry_run,
    )
    output = {
        "server": server.name,
        "pid": result.get("pid"),
        "action": action,
        "success": bool(result.get("success")),
        "dangerous": bool(result.get("dangerous")),
        "still_running": bool(result.get("still_running")),
        "process_excerpt": result.get("process_excerpt") or "",
        "dry_run": dry_run,
    }
    status_text = "preview" if dry_run else "completed" if output["success"] else "failed"
    text = (
        f"Process action {action} PID {output['pid']} on {server.name}: {status_text}"
        f"\n\n```diff\n{change_preview['diff']}\n```"
    )
    if output["success"]:
        return NodeResult(output={"output": text, "action_result": output, "change_preview": change_preview})
    return NodeResult(
        error=str(result.get("output") or "Process action failed"),
        output={"output": text, "action_result": output, "change_preview": change_preview},
    )
