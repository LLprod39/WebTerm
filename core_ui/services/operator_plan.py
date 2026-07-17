"""Plan checklist helpers: approve once, advance steps live."""

from __future__ import annotations

from typing import Any

from core_ui.models import ChatMessage, ChatTurnState


def normalize_plan(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    steps_in = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    steps = []
    for i, step in enumerate(steps_in[:20]):
        if isinstance(step, dict):
            steps.append(
                {
                    "id": int(step.get("id") or i + 1),
                    "text": str(step.get("text") or step.get("description") or "")[:400],
                    "tool": str(step.get("tool") or "")[:80],
                    "status": str(step.get("status") or "pending"),
                }
            )
        else:
            steps.append({"id": i + 1, "text": str(step)[:400], "tool": "", "status": "pending"})
    if not steps:
        return None
    return {
        "title": str(raw.get("title") or "Plan")[:200],
        "status": str(raw.get("status") or "proposed"),
        "steps": steps,
    }


def get_plan_from_message(message: ChatMessage | None) -> dict[str, Any] | None:
    if message is None:
        return None
    meta = message.metadata if isinstance(message.metadata, dict) else {}
    return normalize_plan(meta.get("plan") if isinstance(meta.get("plan"), dict) else None)


def get_plan_from_turn(turn: ChatTurnState) -> dict[str, Any] | None:
    pending = turn.pending_tool_call if isinstance(turn.pending_tool_call, dict) else {}
    plan = normalize_plan(pending.get("plan") if isinstance(pending.get("plan"), dict) else None)
    if plan:
        return plan
    return get_plan_from_message(turn.assistant_message)


def save_plan_to_message(message: ChatMessage, plan: dict[str, Any]) -> dict[str, Any]:
    plan = normalize_plan(plan) or {"title": "Plan", "status": "proposed", "steps": []}
    meta = dict(message.metadata or {})
    meta["plan"] = plan
    message.metadata = meta
    message.save(update_fields=["metadata"])
    return plan


def mark_plan_approved(plan: dict[str, Any]) -> dict[str, Any]:
    plan = normalize_plan(plan) or plan
    plan["status"] = "approved"
    for step in plan.get("steps") or []:
        if step.get("status") in {"pending", "proposed", ""}:
            step["status"] = "pending"
    return plan


def advance_plan_on_action(
    plan: dict[str, Any] | None,
    *,
    action_type: str = "",
    ok: bool = True,
    title: str = "",
) -> dict[str, Any] | None:
    """Mark the next matching pending step as done/failed."""
    plan = normalize_plan(plan)
    if not plan:
        return None
    steps = plan.get("steps") or []
    target = None
    action_l = (action_type or "").lower()
    title_l = (title or "").lower()
    # Prefer tool-name match
    for step in steps:
        if step.get("status") != "pending":
            continue
        tool = str(step.get("tool") or "").lower()
        text = str(step.get("text") or "").lower()
        if tool and (tool in action_l or action_l in tool or tool.replace(".", "_") in action_l.replace(".", "_")):
            target = step
            break
        if title_l and title_l in text:
            target = step
            break
    if target is None:
        for step in steps:
            if step.get("status") == "pending":
                target = step
                break
    if target is None:
        plan["status"] = "completed" if all(s.get("status") in {"done", "completed", "skipped"} for s in steps) else plan.get("status")
        return plan
    target["status"] = "done" if ok else "failed"
    if all(s.get("status") in {"done", "completed", "failed", "skipped"} for s in steps):
        plan["status"] = "completed" if all(s.get("status") in {"done", "completed", "skipped"} for s in steps) else "partial"
    else:
        plan["status"] = "running"
    return plan


def apply_plan_progress(
    *,
    message: ChatMessage | None,
    turn: ChatTurnState | None,
    action_type: str = "",
    ok: bool = True,
    title: str = "",
    approved: bool = False,
) -> dict[str, Any] | None:
    plan = None
    if turn is not None:
        plan = get_plan_from_turn(turn)
    if plan is None and message is not None:
        plan = get_plan_from_message(message)
    if plan is None:
        return None
    if approved:
        plan = mark_plan_approved(plan)
    else:
        plan = advance_plan_on_action(plan, action_type=action_type, ok=ok, title=title)
    if message is not None and plan is not None:
        save_plan_to_message(message, plan)
    if turn is not None and plan is not None:
        pending = dict(turn.pending_tool_call or {})
        pending["plan"] = plan
        turn.pending_tool_call = pending
        # Don't force status change; only persist plan snapshot when still active
        turn.save(update_fields=["pending_tool_call", "updated_at"])
    return plan
