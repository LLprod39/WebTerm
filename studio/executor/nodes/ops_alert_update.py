from __future__ import annotations

from typing import TYPE_CHECKING, Any

from studio.executor.nodes.base import NodeResult
from studio.executor.nodes.ops_helpers import coerce_int as _coerce_int

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


async def execute_alert_update(
    ctx: "ExecutionContext",
    config: dict[str, Any],
    *,
    ops_runtime: Any,
    resolve_context_key: Any,
) -> NodeResult:
    action = str(config.get("action") or "resolve").strip().lower()
    alert_id = _coerce_int(resolve_context_key(ctx, config, "alert_id", "alert_id"))
    if not alert_id:
        return NodeResult(error="alert_id is required or must be present in pipeline context")

    alert = await ops_runtime().update_alert(user=ctx.user, alert_id=alert_id, action=action)
    if alert is None:
        return NodeResult(error=f"Alert not found or inaccessible: {alert_id}")
    output = {
        "alert_id": alert["id"],
        "action": action,
        "title": alert["title"],
        "server": alert["server_name"],
        "is_resolved": alert["is_resolved"],
        "resolved_at": alert["resolved_at"],
        "note": ctx.resolve_template(str(config.get("note") or "")),
    }
    return NodeResult(output={"output": f"Alert #{alert['id']} {action}: {alert['title']}", "alert": output})
