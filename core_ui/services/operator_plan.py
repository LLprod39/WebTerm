"""Plan checklist helpers: approve once, advance steps live."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from core_ui.models import ChatMessage, ChatSession, ChatTurnState

PlanOutcome = Literal["done", "failed", "cancelled"]

AUTONOMY_CONFIRM_EACH = "confirm_each"
AUTONOMY_PLAN_ONCE = "plan_once"
AUTONOMY_AUTONOMOUS = "autonomous"
AUTONOMY_MODES = frozenset({AUTONOMY_CONFIRM_EACH, AUTONOMY_PLAN_ONCE, AUTONOMY_AUTONOMOUS})

STEP_TERMINAL = frozenset({"done", "completed", "failed", "cancelled", "skipped"})
STEP_CLOSABLE = frozenset({"pending", "awaiting_confirm", "running"})
PLAN_ACTIVE = frozenset({"proposed", "approved", "running", "paused"})
BUSY_TURN_STATUSES = frozenset(
    {
        ChatTurnState.STATUS_RUNNING,
        ChatTurnState.STATUS_RESUMING,
        ChatTurnState.STATUS_AWAITING_ASYNC,
        ChatTurnState.STATUS_AWAITING_CONFIRM,
    }
)


def normalize_plan(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    steps_in = raw.get("steps") if isinstance(raw.get("steps"), list) else []
    steps = []
    for i, step in enumerate(steps_in[:20]):
        if isinstance(step, dict):
            step_input = step.get("input") if isinstance(step.get("input"), dict) else {}
            steps.append(
                {
                    "id": int(step.get("id") or i + 1),
                    "text": str(step.get("text") or step.get("description") or "")[:400],
                    "tool": str(step.get("tool") or "")[:80],
                    "input": step_input,
                    "status": str(step.get("status") or "pending"),
                }
            )
        else:
            steps.append({"id": i + 1, "text": str(step)[:400], "tool": "", "input": {}, "status": "pending"})
    if not steps:
        return None
    return {
        "title": str(raw.get("title") or "Plan")[:200],
        "status": str(raw.get("status") or "proposed"),
        "steps": steps,
    }


def get_plan_from_message(message: ChatMessage | None) -> dict[str, Any] | None:
    """Source of truth for the live plan is ``message.metadata.plan``."""
    if message is None:
        return None
    meta = message.metadata if isinstance(message.metadata, dict) else {}
    return normalize_plan(meta.get("plan") if isinstance(meta.get("plan"), dict) else None)


def get_plan_from_turn(turn: ChatTurnState) -> dict[str, Any] | None:
    """Prefer message SoT; fall back to pending_tool_call snapshot (propose_plan park)."""
    plan = get_plan_from_message(turn.assistant_message)
    if plan:
        return plan
    pending = turn.pending_tool_call if isinstance(turn.pending_tool_call, dict) else {}
    return normalize_plan(pending.get("plan") if isinstance(pending.get("plan"), dict) else None)


def save_plan_to_message(message: ChatMessage, plan: dict[str, Any]) -> dict[str, Any]:
    plan = normalize_plan(plan) or {"title": "Plan", "status": "proposed", "steps": []}
    meta = dict(message.metadata or {})
    meta["plan"] = plan
    message.metadata = meta
    message.save(update_fields=["metadata"])
    return plan


def get_autonomy_mode(session: ChatSession | None) -> str:
    """Read autonomy mode from pinned_context; default confirm_each."""
    if session is None:
        return AUTONOMY_CONFIRM_EACH
    pinned = session.pinned_context if isinstance(session.pinned_context, dict) else {}
    mode = str(pinned.get("autonomy_mode") or "").strip().lower()
    if mode in AUTONOMY_MODES:
        return mode
    return AUTONOMY_CONFIRM_EACH


def _norm_tool_key(value: str) -> str:
    return str(value or "").strip().lower().replace("_", ".")


def _normalize_command(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _server_ids_from_payload(payload: dict[str, Any] | None) -> list[int]:
    data = payload if isinstance(payload, dict) else {}
    ids: list[int] = []
    raw_ids = data.get("server_ids")
    if isinstance(raw_ids, list):
        for item in raw_ids:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
    if data.get("server_id") is not None:
        try:
            sid = int(data["server_id"])
            if sid not in ids:
                ids.append(sid)
        except (TypeError, ValueError):
            pass
    return sorted(ids)


def _tool_matches(step_tool: str, action_type: str) -> bool:
    tool_key = _norm_tool_key(step_tool)
    action_key = _norm_tool_key(action_type)
    if not tool_key or not action_key:
        return False
    if tool_key == action_key:
        return True
    return tool_key in action_key or action_key in tool_key


def approved_plan_step_matches(
    plan: dict[str, Any] | None,
    *,
    action_type: str,
    input_payload: dict[str, Any],
) -> bool:
    """Return True only when an approved pending step exactly matches a call.

    A plan approval is consent for the payload shown in that plan, not a blank
    cheque for any later model mutation.  Legacy/text-only plans deliberately
    fail closed and fall back to an individual confirmation card.

    Only ``pending`` steps match — stuck ``running`` / ``awaiting_confirm`` must
    not unlock auto-run (fail closed).
    """
    normalized = normalize_plan(plan)
    if not normalized or normalized.get("status") not in {"approved", "running"}:
        return False

    action_key = _norm_tool_key(action_type)
    actual = json.dumps(input_payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    for step in normalized.get("steps") or []:
        if step.get("status") != "pending":
            continue
        tool_key = _norm_tool_key(str(step.get("tool") or ""))
        planned_input = step.get("input") if isinstance(step.get("input"), dict) else {}
        if not tool_key or not planned_input:
            continue
        expected = json.dumps(planned_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if tool_key == action_key and expected == actual:
            return True
    return False


def _is_command_tool(action_type: str) -> bool:
    """True for shell/fanout-style tools that must carry a non-empty planned command."""
    # Markers use dotted form because _norm_tool_key replaces underscores with dots.
    key = _norm_tool_key(action_type)
    return any(marker in key for marker in ("run.command", "run.fanout", "fanout"))


def canonical_plan_step_matches(
    plan: dict[str, Any] | None,
    *,
    action_type: str,
    input_payload: dict[str, Any],
) -> bool:
    """Soft match for plan_once fallback: tool + server_id(s) + normalized command.

    Empty planned input fails closed (caller must confirm). Only pending steps.
    For command tools, planned_cmd must be non-empty — server-only soft match is not enough.
    """
    normalized = normalize_plan(plan)
    if not normalized or normalized.get("status") not in {"approved", "running"}:
        return False

    actual = input_payload if isinstance(input_payload, dict) else {}
    actual_servers = _server_ids_from_payload(actual)
    actual_cmd = _normalize_command(actual.get("command") or actual.get("cmd"))
    action_is_command = _is_command_tool(action_type)

    for step in normalized.get("steps") or []:
        if step.get("status") != "pending":
            continue
        planned_input = step.get("input") if isinstance(step.get("input"), dict) else {}
        if not planned_input:
            continue
        step_tool = str(step.get("tool") or "")
        if not _tool_matches(step_tool, action_type):
            continue
        planned_servers = _server_ids_from_payload(planned_input)
        planned_cmd = _normalize_command(planned_input.get("command") or planned_input.get("cmd"))
        step_is_command = action_is_command or _is_command_tool(step_tool)
        # Command tools: empty planned command must not soft-match (fail closed).
        if step_is_command and not planned_cmd:
            continue
        if planned_servers and planned_servers != actual_servers:
            continue
        if planned_cmd and planned_cmd != actual_cmd:
            continue
        # Soft match requires at least one consent signal beyond tool name.
        if not planned_servers and not planned_cmd:
            # Compare remaining keys with exact JSON for non-command tools
            expected = json.dumps(planned_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            got = json.dumps(actual, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if expected != got:
                continue
        return True
    return False


def find_next_frozen_plan_step(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the next pending step with non-empty frozen tool+input, else None."""
    normalized = normalize_plan(plan)
    if not normalized or normalized.get("status") not in {"approved", "running"}:
        return None
    for step in normalized.get("steps") or []:
        if step.get("status") != "pending":
            continue
        tool = str(step.get("tool") or "").strip()
        planned_input = step.get("input") if isinstance(step.get("input"), dict) else {}
        if tool and planned_input:
            return step
    return None


def plan_once_allows_auto_run(
    plan: dict[str, Any] | None,
    *,
    action_type: str,
    input_payload: dict[str, Any],
) -> tuple[bool, dict[str, Any] | None]:
    """Decide plan_once auto-run. Returns (allowed, frozen_input_or_None).

    Primary: next frozen pending step with matching tool and non-empty input.
    Fallback: canonical soft match. Empty frozen input → (False, None).
    """
    if approved_plan_step_matches(plan, action_type=action_type, input_payload=input_payload):
        return True, None
    frozen = find_next_frozen_plan_step(plan)
    if frozen is not None and _tool_matches(str(frozen.get("tool") or ""), action_type):
        planned = frozen.get("input") if isinstance(frozen.get("input"), dict) else {}
        if planned:
            return True, planned
        return False, None
    if canonical_plan_step_matches(plan, action_type=action_type, input_payload=input_payload):
        return True, None
    return False, None


def plan_has_incomplete_steps(plan: dict[str, Any] | None) -> bool:
    normalized = normalize_plan(plan)
    if not normalized:
        return False
    if normalized.get("status") not in {"approved", "running", "paused"}:
        return False
    return any(str(s.get("status") or "pending") not in STEP_TERMINAL for s in (normalized.get("steps") or []))


def mark_plan_approved(plan: dict[str, Any]) -> dict[str, Any]:
    plan = normalize_plan(plan) or plan
    plan["status"] = "approved"
    for step in plan.get("steps") or []:
        if step.get("status") in {"pending", "proposed", ""}:
            step["status"] = "pending"
    return plan


def _find_closable_step(
    steps: list[dict[str, Any]],
    *,
    action_type: str = "",
    title: str = "",
    statuses: frozenset[str] = STEP_CLOSABLE,
) -> dict[str, Any] | None:
    action_l = (action_type or "").lower()
    title_l = (title or "").lower()
    for step in steps:
        if step.get("status") not in statuses:
            continue
        tool = str(step.get("tool") or "").lower()
        text = str(step.get("text") or "").lower()
        if tool and (
            tool in action_l
            or action_l in tool
            or tool.replace(".", "_") in action_l.replace(".", "_")
        ):
            return step
        if title_l and title_l in text:
            return step
    return None


def mark_plan_step_awaiting_confirm(
    plan: dict[str, Any] | None,
    *,
    action_type: str = "",
    title: str = "",
) -> dict[str, Any] | None:
    """Park-for-confirm: matched pending → awaiting_confirm; plan stays approved/proposed."""
    plan = normalize_plan(plan)
    if not plan:
        return None
    target = _find_closable_step(
        plan.get("steps") or [],
        action_type=action_type,
        title=title,
        statuses=frozenset({"pending"}),
    )
    if target is not None:
        target["status"] = "awaiting_confirm"
        # Do not promote plan to running — confirm card is not execution yet.
    return plan


def mark_plan_step_running(
    plan: dict[str, Any] | None,
    *,
    action_type: str = "",
    title: str = "",
) -> dict[str, Any] | None:
    """Mark the matched step running when execution actually starts."""
    plan = normalize_plan(plan)
    if not plan:
        return None
    target = _find_closable_step(
        plan.get("steps") or [],
        action_type=action_type,
        title=title,
        statuses=frozenset({"pending", "awaiting_confirm"}),
    )
    if target is None:
        return plan
    target["status"] = "running"
    if plan.get("status") in {"approved", "proposed", "paused"}:
        plan["status"] = "running"
    return plan


def advance_plan_on_action(
    plan: dict[str, Any] | None,
    *,
    action_type: str = "",
    ok: bool = True,
    title: str = "",
    outcome: PlanOutcome | None = None,
) -> dict[str, Any] | None:
    """Close a closable step (running / awaiting_confirm / matching pending).

    ``outcome`` is done|failed|cancelled. Cancel marks the step ``cancelled`` and
    the plan ``paused`` — never ``failed`` from a user cancel.
    """
    plan = normalize_plan(plan)
    if not plan:
        return None
    steps = plan.get("steps") or []
    resolved: PlanOutcome
    if outcome in {"done", "failed", "cancelled"}:
        resolved = outcome
    else:
        resolved = "done" if ok else "failed"

    target = _find_closable_step(steps, action_type=action_type, title=title)
    if target is None:
        # Never attribute an unrelated model action to the next plan step.
        return plan

    if resolved == "cancelled":
        target["status"] = "cancelled"
        plan["status"] = "paused"
        return plan

    target["status"] = "done" if resolved == "done" else "failed"
    if all(s.get("status") in STEP_TERMINAL for s in steps):
        plan["status"] = (
            "completed"
            if all(s.get("status") in {"done", "completed", "skipped"} for s in steps)
            else "partial"
        )
    else:
        plan["status"] = "running"
    return plan


def reconcile_plan_state(
    message: ChatMessage | None,
    turn: ChatTurnState | None = None,
    *,
    reason: str = "",
) -> dict[str, Any] | None:
    """Clear stuck running/awaiting_confirm when the turn is idle/terminal.

    - awaiting_confirm → pending (confirm card no longer active)
    - running → pending on stop; failed on heartbeat_lost / worker loss
    - plan → paused when incomplete steps remain after reconcile
    """
    if message is None and turn is not None:
        message = turn.assistant_message
    if message is None:
        return None

    plan = get_plan_from_message(message)
    if plan is None and turn is not None:
        pending = turn.pending_tool_call if isinstance(turn.pending_tool_call, dict) else {}
        plan = normalize_plan(pending.get("plan") if isinstance(pending.get("plan"), dict) else None)
    if not plan:
        return None

    turn_status = getattr(turn, "status", None) if turn is not None else None
    turn_busy = turn_status in BUSY_TURN_STATUSES if turn_status else False
    # Explicit stop/heartbeat always reconcile even if turn object still looks busy
    # (caller already flipped status or is about to).
    force = reason in {
        "stopped_by_user",
        "stop",
        "heartbeat_lost",
        "worker_heartbeat_lost",
        "turn_timeout",
        "legacy_stuck",
    }

    # Legacy park bug: step was marked running before confirm while turn is
    # still awaiting_confirm. Downgrade running → awaiting_confirm without pause.
    if turn_status == ChatTurnState.STATUS_AWAITING_CONFIRM and not force:
        changed_legacy = False
        for step in plan.get("steps") or []:
            if step.get("status") == "running":
                step["status"] = "awaiting_confirm"
                changed_legacy = True
        if changed_legacy:
            if plan.get("status") == "running":
                # Confirm card is not execution — keep approved/proposed if possible.
                plan["status"] = "approved"
            save_plan_to_message(message, plan)
        return plan

    if turn_busy and not force:
        # Running/resuming may legitimately have a running step.
        if turn_status in {
            ChatTurnState.STATUS_RUNNING,
            ChatTurnState.STATUS_RESUMING,
            ChatTurnState.STATUS_AWAITING_ASYNC,
        }:
            return plan

    reason_l = (reason or "").lower()
    fail_running = any(
        token in reason_l
        for token in ("heartbeat", "timeout", "worker_heartbeat_lost", "turn_timeout")
    )
    changed = False
    for step in plan.get("steps") or []:
        status = str(step.get("status") or "")
        if status == "awaiting_confirm":
            step["status"] = "pending"
            changed = True
        elif status == "running":
            step["status"] = "failed" if fail_running else "pending"
            changed = True

    if not changed:
        return plan

    if plan_has_incomplete_steps(plan) or any(
        s.get("status") in {"pending", "awaiting_confirm"} for s in (plan.get("steps") or [])
    ):
        if plan.get("status") not in {"completed", "partial", "cancelled"}:
            plan["status"] = "paused"
    elif all(s.get("status") in STEP_TERMINAL for s in (plan.get("steps") or [])):
        plan["status"] = (
            "completed"
            if all(s.get("status") in {"done", "completed", "skipped"} for s in (plan.get("steps") or []))
            else "partial"
        )

    save_plan_to_message(message, plan)
    if turn is not None:
        pending = dict(turn.pending_tool_call or {})
        if pending.get("plan") is not None or "plan" in pending:
            pending["plan"] = plan
            turn.pending_tool_call = pending
            turn.save(update_fields=["pending_tool_call", "updated_at"])
    return plan


def apply_plan_progress(
    *,
    message: ChatMessage | None,
    turn: ChatTurnState | None,
    action_type: str = "",
    ok: bool = True,
    title: str = "",
    approved: bool = False,
    outcome: PlanOutcome | None = None,
) -> dict[str, Any] | None:
    plan = None
    # SoT is message.metadata.plan
    if message is not None:
        plan = get_plan_from_message(message)
    if plan is None and turn is not None:
        plan = get_plan_from_turn(turn)
    if plan is None:
        return None
    if approved:
        plan = mark_plan_approved(plan)
    else:
        plan = advance_plan_on_action(
            plan,
            action_type=action_type,
            ok=ok,
            title=title,
            outcome=outcome,
        )
    if message is not None and plan is not None:
        save_plan_to_message(message, plan)
    if turn is not None and plan is not None:
        pending = dict(turn.pending_tool_call or {})
        pending["plan"] = plan
        turn.pending_tool_call = pending
        turn.save(update_fields=["pending_tool_call", "updated_at"])
    return plan


def mark_plan_executing_for_action(
    *,
    message: ChatMessage | None,
    action_type: str = "",
    title: str = "",
    turn: ChatTurnState | None = None,
) -> dict[str, Any] | None:
    """Flip matched step to running at real execute start; persist to message SoT."""
    plan = get_plan_from_message(message) if message is not None else None
    if plan is None and turn is not None:
        plan = get_plan_from_turn(turn)
    if plan is None:
        return None
    updated = mark_plan_step_running(plan, action_type=action_type, title=title)
    if updated is None:
        return None
    if message is not None:
        save_plan_to_message(message, updated)
    if turn is not None:
        pending = dict(turn.pending_tool_call or {})
        pending["plan"] = updated
        turn.pending_tool_call = pending
        turn.save(update_fields=["pending_tool_call", "updated_at"])
    return updated


def revert_plan_executing_to_awaiting_confirm(
    *,
    message: ChatMessage | None,
    action_type: str = "",
    title: str = "",
    turn: ChatTurnState | None = None,
) -> dict[str, Any] | None:
    """Undo premature ``running`` after a failed typed-confirm (back to awaiting_confirm)."""
    plan = get_plan_from_message(message) if message is not None else None
    if plan is None and turn is not None:
        plan = get_plan_from_turn(turn)
    if plan is None:
        return None
    target = _find_closable_step(
        plan.get("steps") or [],
        action_type=action_type,
        title=title,
        statuses=frozenset({"running"}),
    )
    if target is None:
        return plan
    target["status"] = "awaiting_confirm"
    # Keep plan approved/running/paused as-is; confirm card is still pending.
    if message is not None:
        save_plan_to_message(message, plan)
    if turn is not None:
        pending = dict(turn.pending_tool_call or {})
        pending["plan"] = plan
        turn.pending_tool_call = pending
        turn.save(update_fields=["pending_tool_call", "updated_at"])
    return plan


def mark_executing_after_typed_confirm_ok(
    action: Any,
    *,
    typed_confirm: str | None = None,
) -> tuple[Any, str | None]:
    """Validate typed confirm first; only then mark the plan step ``running``.

    Returns ``(action, typed_error_or_None)``. On typed failure the action is left
    in ``requires_confirmation`` with ``error`` set and the plan is untouched.
    """
    from core_ui.models import AssistantAction
    from core_ui.services.operator_security import validate_typed_confirm

    typed_error = validate_typed_confirm(action, typed_confirm)
    if typed_error:
        action.status = AssistantAction.STATUS_REQUIRES_CONFIRMATION
        action.error = typed_error
        action.save(update_fields=["status", "error", "updated_at"])
        return action, typed_error

    turn = (
        ChatTurnState.objects.filter(
            pending_action=action,
            status=ChatTurnState.STATUS_AWAITING_CONFIRM,
        )
        .select_related("assistant_message")
        .first()
    )
    if turn is not None and turn.assistant_message is not None:
        mark_plan_executing_for_action(
            message=turn.assistant_message,
            action_type=action.action_type,
            title=action.title or "",
            turn=turn,
        )
    return action, None
