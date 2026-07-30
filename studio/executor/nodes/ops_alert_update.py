from __future__ import annotations

from typing import TYPE_CHECKING, Any

from studio.executor.change_preview import build_change_preview
from studio.executor.nodes.base import NodeResult
from studio.executor.nodes.ops_helpers import coerce_bool as _coerce_bool
from studio.executor.nodes.ops_helpers import coerce_int as _coerce_int

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


async def execute_alert_update(
    ctx: ExecutionContext,
    config: dict[str, Any],
    *,
    ops_runtime: Any,
    resolve_context_key: Any,
) -> NodeResult:
    action = str(config.get("action") or "resolve").strip().lower()
    alert_id = _coerce_int(resolve_context_key(ctx, config, "alert_id", "alert_id"))
    if not alert_id:
        return NodeResult(error="alert_id is required or must be present in pipeline context")

    dry_run = _coerce_bool(config.get("dry_run"), default=False)
    alert = await ops_runtime().update_alert(user=ctx.user, alert_id=alert_id, action=action, dry_run=dry_run)
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
        "dry_run": dry_run,
    }
    change_preview = build_change_preview(
        operation=f"alert.{action}",
        target={"alert_id": alert["id"], "server": alert["server_name"]},
        before=alert.get("before") or {},
        after={"is_resolved": alert["is_resolved"], "resolved_at": alert["resolved_at"]},
        dry_run=dry_run,
    )
    status_text = "preview" if dry_run else "completed"
    text = f"Alert #{alert['id']} {action} {status_text}: {alert['title']}\n\n```diff\n{change_preview['diff']}\n```"
    return NodeResult(output={"output": text, "alert": output, "change_preview": change_preview})
