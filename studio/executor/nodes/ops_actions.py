from __future__ import annotations

from typing import TYPE_CHECKING, Any

from studio.executor.nodes.base import NodeResult
from studio.executor.nodes.ops_helpers import coerce_bool as _coerce_bool
from studio.executor.nodes.ops_helpers import coerce_int as _coerce_int
from studio.executor.nodes.ops_helpers import compact_json as _compact_json

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
    result = await run_service_action(server, secret=secret, service=service, action=action)
    verify = None
    if _coerce_bool(config.get("verify"), default=True):
        verify = await get_service_logs(server, secret=secret, service=service, lines=40)
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
    return NodeResult(
        error=str(result.get("output") or "Service action failed"), output={"output": text, "action_result": output}
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
    result = await run_docker_action(server, secret=secret, container=container, action=action)
    after = await get_docker(server, secret=secret) if _coerce_bool(config.get("verify"), default=True) else None
    logs = None
    if _coerce_bool(config.get("include_logs"), default=True):
        logs = await get_docker_logs(
            server, secret=secret, container=container, lines=_coerce_int(config.get("lines")) or 80
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
    }
    status_text = "completed" if output["success"] else "failed"
    text = f"Docker action {action} {output['container']} on {server.name}: {status_text}\n\n```json\n{_compact_json(output)}\n```"
    if output["success"]:
        return NodeResult(output={"output": text, "action_result": output})
    return NodeResult(
        error=str(result.get("output") or "Docker action failed"), output={"output": text, "action_result": output}
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
    pid = resolve_context_key(ctx, config, "pid", "pid")
    action = str(config.get("action") or "terminate").strip().lower()
    result = await run_process_action(server, secret=secret, pid=pid, action=action)
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
    return NodeResult(
        error=str(result.get("output") or "Process action failed"), output={"output": text, "action_result": output}
    )
