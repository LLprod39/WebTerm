"""Async long-running operator tools: park turn and resume when runs finish."""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from django.db import transaction
from loguru import logger

from core_ui.models import ChatTurnState

TERMINAL_AGENT_STATUSES = frozenset({"completed", "failed", "stopped"})
TERMINAL_PLAYBOOK_STATUSES = frozenset({"completed", "failed", "partial", "cancelled"})


def is_async_tool_result(payload: dict[str, Any] | None) -> bool:
    data = payload or {}
    if data.get("async") or data.get("async_run"):
        return True
    if data.get("run_id") and data.get("async_kind"):
        return True
    # agent.run payloads typically include run_id + status pending/running
    return bool(data.get("run_id") and str(data.get("status") or "").lower() in {"pending", "running", "queued", "claimed"})


def normalize_async_ref(payload: dict[str, Any] | None, *, action_type: str = "") -> dict[str, Any]:
    data = dict(payload or {})
    kind = str(data.get("async_kind") or "")
    if not kind:
        if "playbook" in action_type or data.get("playbook_run_id"):
            kind = "playbook_run"
        elif data.get("run_id") or "agent" in action_type:
            kind = "agent_run"
    run_id = data.get("run_id") or data.get("playbook_run_id")
    try:
        run_id_int = int(run_id) if run_id is not None else None
    except (TypeError, ValueError):
        run_id_int = None
    return {
        "async": True,
        "async_kind": kind or "agent_run",
        "run_id": run_id_int,
        "status": data.get("status") or "running",
        "target_url": data.get("target_url") or "",
    }


def park_turn_for_async(
    turn: ChatTurnState,
    *,
    tool_call: dict[str, Any],
    async_ref: dict[str, Any],
    messages: list[dict[str, Any]] | None = None,
    note: str = "",
) -> ChatTurnState:
    """Mark turn as waiting for an external run to finish."""
    pending = {
        **(tool_call or {}),
        "async": True,
        "async_kind": async_ref.get("async_kind"),
        "run_id": async_ref.get("run_id"),
    }
    turn.status = ChatTurnState.STATUS_AWAITING_ASYNC
    turn.pending_tool_call = pending
    if messages is not None:
        turn.llm_messages = messages
    if note and turn.assistant_message_id:
        msg = turn.assistant_message
        if msg is not None:
            suffix = f"\n\n_{note}_"
            if suffix not in (msg.content or ""):
                msg.content = (msg.content or "") + suffix
                meta = dict(msg.metadata or {})
                meta["awaiting_async"] = True
                meta["async_run"] = async_ref
                msg.metadata = meta
                msg.save(update_fields=["content", "metadata"])
    turn.save(update_fields=["status", "pending_tool_call", "llm_messages", "updated_at"])
    if turn.pending_action_id:
        action = turn.pending_action
        if action is not None:
            action.async_run_ref = async_ref
            action.save(update_fields=["async_run_ref", "updated_at"])
    return turn


def _find_turns_for_run(*, kind: str, run_id: int) -> list[ChatTurnState]:
    qs = (
        ChatTurnState.objects.filter(status=ChatTurnState.STATUS_AWAITING_ASYNC)
        .select_related("session", "assistant_message", "user_message", "pending_action")
        .order_by("-updated_at")[:20]
    )
    matches: list[ChatTurnState] = []
    for turn in qs:
        pending = turn.pending_tool_call or {}
        if pending.get("async_kind") == kind and int(pending.get("run_id") or 0) == run_id:
            matches.append(turn)
            continue
        action = turn.pending_action
        if action is not None:
            ref = action.async_run_ref or {}
            if ref.get("async_kind") == kind and int(ref.get("run_id") or 0) == run_id:
                matches.append(turn)
    return matches


def _agent_run_result_payload(run) -> dict[str, Any]:
    from servers.agent_run_report import build_agent_run_report_response

    try:
        report = build_agent_run_report_response(run)
    except Exception as exc:  # noqa: BLE001
        report = {"error": f"report unavailable: {exc}"}
    return {
        "ok": run.status == "completed",
        "async_done": True,
        "async_kind": "agent_run",
        "run_id": run.pk,
        "status": run.status,
        "report": report,
        "target_url": f"/agents/run/{run.pk}",
    }


def _playbook_run_result_payload(run) -> dict[str, Any]:
    return {
        "ok": run.status in {"completed", "partial"},
        "async_done": True,
        "async_kind": "playbook_run",
        "run_id": run.pk,
        "status": run.status,
        "summary": run.summary or {},
        "host_results_count": len(run.host_results or []) if isinstance(run.host_results, list) else 0,
        "error_message": getattr(run, "error_message", "") or "",
        "target_url": f"/playbooks/runs/{run.pk}",
    }


def resume_turns_for_agent_run(run) -> int:
    if run is None or run.status not in TERMINAL_AGENT_STATUSES:
        return 0
    turns = _find_turns_for_run(kind="agent_run", run_id=run.pk)
    if not turns:
        return 0
    payload = _agent_run_result_payload(run)
    return _resume_turns(turns, payload=payload, tool_name="agent_run")


def resume_turns_for_playbook_run(run) -> int:
    if run is None or run.status not in TERMINAL_PLAYBOOK_STATUSES:
        return 0
    turns = _find_turns_for_run(kind="playbook_run", run_id=run.pk)
    if not turns:
        return 0
    payload = _playbook_run_result_payload(run)
    return _resume_turns(turns, payload=payload, tool_name="playbook_run")


def _resume_turns(turns: list[ChatTurnState], *, payload: dict[str, Any], tool_name: str) -> int:
    from core_ui.services.operator_session import resume_after_async_result

    count = 0
    for turn in turns:
        try:
            async_to_sync(resume_after_async_result)(
                turn=turn,
                result_payload=payload,
                tool_name=tool_name,
            )
            count += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("operator async resume failed turn=%s: %s", turn.pk, exc)
            turn.status = ChatTurnState.STATUS_FAILED
            turn.error = str(exc)[:1000]
            turn.save(update_fields=["status", "error", "updated_at"])
    return count


def notify_agent_run_terminal(run_id: int) -> None:
    from servers.models import AgentRun

    run = AgentRun.objects.filter(pk=run_id).first()
    if run is None:
        return
    resume_turns_for_agent_run(run)


def notify_playbook_run_terminal(run_id: int) -> None:
    from servers.models import PlaybookRun

    run = PlaybookRun.objects.filter(pk=run_id).first()
    if run is None:
        return
    resume_turns_for_playbook_run(run)


def schedule_async_resume_on_commit(*, kind: str, run_id: int) -> None:
    """Call from model signals after commit."""

    def _run():
        try:
            if kind == "agent_run":
                notify_agent_run_terminal(run_id)
            elif kind == "playbook_run":
                notify_playbook_run_terminal(run_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("async resume on_commit failed %s#%s: %s", kind, run_id, exc)

    transaction.on_commit(_run)
