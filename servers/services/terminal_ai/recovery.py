"""Pure helpers for Terminal AI command recovery decisions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from loguru import logger

from servers.services import terminal_events
from servers.services.terminal_ai.legacy_state import (
    apply_legacy_ai_queue_state,
    sync_legacy_ai_queue_state,
)

MAX_RECOVERY_RETRIES = 2


@dataclass(frozen=True)
class RetryCandidate:
    command: str
    why: str


def should_attempt_error_recovery(
    *,
    exit_code: int | None,
    item: dict[str, Any],
    step_mode: bool,
    retries: int,
    max_retries: int = MAX_RECOVERY_RETRIES,
) -> bool:
    """Return whether fast-mode should ask the recovery controller about a failure."""
    if step_mode:
        return False
    if bool(item.get("_no_recovery")):
        return False
    if exit_code in (0, 130, None):
        return False
    return int(retries) < int(max_retries)


def recovery_action(decision: dict[str, Any], *, default: str = "skip") -> str:
    """Normalize a recovery/step controller action."""
    action = str((decision or {}).get("action") or default).lower().strip()
    return action or default


def retry_candidate_from_decision(
    decision: dict[str, Any],
    *,
    original_command: str,
    retries: int,
    default_why: str,
    max_retries: int = MAX_RECOVERY_RETRIES,
) -> RetryCandidate | None:
    """Project a validated retry command from a controller decision."""
    if int(retries) >= int(max_retries):
        return None
    new_command = str((decision or {}).get("cmd") or "").strip()
    if not new_command or new_command == str(original_command or "").strip():
        return None
    why = str((decision or {}).get("why") or default_why)
    return RetryCandidate(command=new_command, why=why)


def recovery_question(decision: dict[str, Any], *, default: str) -> str:
    return str((decision or {}).get("question") or default)


def recovery_abort_message(decision: dict[str, Any], *, default: str) -> str:
    return str((decision or {}).get("why") or default)


async def insert_retry_candidate(
    owner: Any,
    candidate: RetryCandidate,
    *,
    original_command: str,
    retries: int,
    at_cursor: bool,
    event_why: str | None = None,
) -> None:
    """Insert a retry item through the consumer-compatible owner hooks."""
    reservation = await owner._reserve_ai_retry_item(retries)
    item = owner._build_reserved_plan_item(
        reservation,
        cmd=candidate.command,
        why=candidate.why,
        no_recovery=True,
    )
    await owner._insert_ai_plan_item(item, at_cursor=at_cursor)
    await owner._send_ai_event(
        terminal_events.ai_recovery(
            original_cmd=original_command,
            new_cmd=candidate.command,
            new_id=reservation.item_id,
            why=candidate.why if event_why is None else event_why,
            requires_confirm=bool(item.get("requires_confirm")),
            reason=str(item.get("reason") or ""),
            streaming=bool(item.get("streaming")),
        )
    )


async def handle_fast_error_recovery(
    owner: Any,
    *,
    item: dict[str, Any],
    item_id: int,
    command: str,
    exit_code: int | None,
    output: str,
    step_mode: bool,
) -> str | None:
    """Run fast-mode recovery after a failed command and return the chosen action."""
    retries = owner._ai_state.error_retries.get(int(item_id), 0)
    if not should_attempt_error_recovery(
        exit_code=exit_code,
        item=item,
        step_mode=step_mode,
        retries=retries,
    ):
        return None

    await owner._send_ai_event(
        terminal_events.ai_status(
            "analyzing_error",
            cmd=command,
            exit_code=exit_code,
        )
    )
    try:
        async with owner._ai_state.lock:
            ai_session = sync_legacy_ai_queue_state(owner, owner._TerminalAiSessionCls)
            remaining_cmds = ai_session.remaining_commands_after_current()
        decision = await owner._ai_handle_error(command, exit_code, output, remaining_cmds)
        action = recovery_action(decision)

        if action == "retry":
            candidate = retry_candidate_from_decision(
                decision,
                original_command=command,
                retries=retries,
                default_why="Retry after error",
            )
            if candidate:
                await insert_retry_candidate(
                    owner,
                    candidate,
                    original_command=command,
                    retries=retries,
                    at_cursor=False,
                )
        elif action == "ask":
            action = await _handle_recovery_question(
                owner,
                item_id=item_id,
                command=command,
                exit_code=exit_code,
                output=output,
                remaining_cmds=remaining_cmds,
                retries=retries,
                decision=decision,
            )
        elif action == "abort":
            await owner._send_ai_event(
                terminal_events.ai_error(
                    recovery_abort_message(
                        decision,
                        default="Выполнение прервано из-за критической ошибки",
                    )
                )
            )
        return action
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Error recovery LLM failed: {}", exc)
        return "skip"


async def _handle_recovery_question(
    owner: Any,
    *,
    item_id: int,
    command: str,
    exit_code: int | None,
    output: str,
    remaining_cmds: list[str],
    retries: int,
    decision: dict[str, Any],
) -> str:
    action = "ask"
    question = recovery_question(decision, default="Как лучше продолжить?")
    async with owner._ai_state.lock:
        q_id = owner._ai_state.session.allocate_question_id(f"q_{item_id}")
    try:
        user_reply = await owner._ai_state.run.ask_user(
            q_id=q_id,
            event=terminal_events.ai_question(
                q_id=q_id,
                question=question,
                command=command,
                exit_code=exit_code,
            ),
            send_event=owner._send_ai_event,
            timeout_seconds=300,
        )
        owner._add_to_history("user", f"[Ответ агенту]: {user_reply}")
        decision2 = await owner._ai_handle_error(
            command,
            exit_code,
            output,
            remaining_cmds,
            user_reply=user_reply,
        )
        if recovery_action(decision2) == "retry":
            candidate = retry_candidate_from_decision(
                decision2,
                original_command=command,
                retries=retries,
                default_why="",
            )
            if candidate:
                await insert_retry_candidate(
                    owner,
                    candidate,
                    original_command=command,
                    retries=retries,
                    at_cursor=False,
                )
                action = "retry"
        elif recovery_action(decision2) == "abort":
            action = "abort"
            await owner._send_ai_event(
                terminal_events.ai_error(recovery_abort_message(decision2, default="Выполнение прервано"))
            )
        return action
    except TimeoutError:
        logger.info("ai_question timeout, skipping command")
        return "skip"


async def handle_step_post_command(
    owner: Any,
    *,
    item_id: int,
    command: str,
    exit_code: int | None,
    output: str,
    extra_limit: int = 20,
) -> bool:
    """Run the step-mode post-command controller. Returns True when the queue should stop."""
    try:
        async with owner._ai_state.lock:
            ai_session = sync_legacy_ai_queue_state(owner, owner._TerminalAiSessionCls)
            remaining_cmds = ai_session.remaining_commands_from_cursor()
        decision = await owner._ai_step_decide_next(
            user_goal=owner._ai_state.session.user_message,
            last_cmd=command,
            exit_code=int(exit_code if exit_code is not None else -1),
            output=output or "",
            remaining_cmds=remaining_cmds,
        )
        action = recovery_action(decision, default="continue")

        if action == "ask":
            decision, action = await _handle_step_question(
                owner,
                item_id=item_id,
                command=command,
                exit_code=exit_code,
                output=output,
                remaining_cmds=remaining_cmds,
                decision=decision,
            )

        if action == "retry":
            await _handle_step_retry(owner, item_id=item_id, command=command, decision=decision)
        elif action == "next":
            await _handle_step_next(owner, decision=decision, extra_limit=extra_limit)
        elif action == "done":
            await _handle_step_done(owner, decision=decision)
            return True
        elif action == "abort":
            await owner._send_ai_event(
                terminal_events.ai_error(
                    str(decision.get("assistant_text") or "Выполнение остановлено из-за критического состояния.")
                )
            )
            return True
        return False
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Step-by-step post-step analysis failed: {}", exc)
        return False


async def _handle_step_question(
    owner: Any,
    *,
    item_id: int,
    command: str,
    exit_code: int | None,
    output: str,
    remaining_cmds: list[str],
    decision: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    question = str(decision.get("question") or "Как продолжить дальше?").strip()
    async with owner._ai_state.lock:
        q_id = owner._ai_state.session.allocate_question_id(f"q_step_{item_id}")
    try:
        user_reply = await owner._ai_state.run.ask_user(
            q_id=q_id,
            event=terminal_events.ai_question(
                q_id=q_id,
                question=question,
                command=command,
                exit_code=exit_code,
            ),
            send_event=owner._send_ai_event,
            timeout_seconds=300,
        )
        owner._add_to_history("user", f"[Ответ на шаг]: {user_reply}")
        decision = await owner._ai_step_decide_next(
            user_goal=owner._ai_state.session.user_message,
            last_cmd=command,
            exit_code=int(exit_code if exit_code is not None else -1),
            output=output or "",
            remaining_cmds=remaining_cmds,
            user_reply=user_reply,
        )
        return decision, recovery_action(decision, default="continue")
    except TimeoutError:
        return decision, "continue"


async def _handle_step_retry(owner: Any, *, item_id: int, command: str, decision: dict[str, Any]) -> None:
    retries = owner._ai_state.error_retries.get(int(item_id), 0)
    candidate = retry_candidate_from_decision(
        decision,
        original_command=command,
        retries=retries,
        default_why="Retry after error (step-mode)",
    )
    if candidate:
        await insert_retry_candidate(
            owner,
            candidate,
            original_command=command,
            retries=retries,
            at_cursor=True,
            event_why=str(decision.get("why") or ""),
        )


async def _handle_step_next(owner: Any, *, decision: dict[str, Any], extra_limit: int) -> None:
    next_cmd = str(decision.get("next_cmd") or "").strip()
    if not next_cmd:
        return
    if owner._ai_state.session.step_extra_count >= int(extra_limit):
        await owner._send_ai_event(
            terminal_events.ai_response(
                mode="answer",
                assistant_text=(
                    "Достигнут защитный лимит дополнительных адаптивных шагов "
                    f"({extra_limit}) в режиме step-by-step. "
                    "Продолжаю выполнение уже запланированных команд. "
                    "Для длинных линейных задач переключите режим на Fast или Auto."
                ),
                commands=[],
                execution_mode="step",
            )
        )
        return

    reservation = await owner._reserve_ai_adaptive_item(extra_limit)
    if reservation is None:
        return
    new_item = owner._build_reserved_plan_item(
        reservation,
        cmd=next_cmd,
        why=str(decision.get("why") or "Следующий адаптивный шаг"),
    )
    await owner._insert_ai_plan_item(new_item, at_cursor=True)
    await owner._send_ai_event(
        terminal_events.ai_response(
            mode="execute",
            assistant_text=str(decision.get("assistant_text") or "Добавляю следующий шаг по результатам проверки."),
            commands=[new_item],
            execution_mode="step",
        )
    )


async def _handle_step_done(owner: Any, *, decision: dict[str, Any]) -> None:
    done_text = str(decision.get("assistant_text") or "Цель достигнута. Останавливаю дальнейшие шаги.").strip()
    owner._add_to_history("assistant", done_text)
    await owner._send_ai_event(
        terminal_events.ai_response(
            mode="answer",
            assistant_text=done_text,
            commands=[],
            execution_mode="step",
        )
    )
    async with owner._ai_state.lock:
        ai_session = sync_legacy_ai_queue_state(owner, owner._TerminalAiSessionCls)
        pending_ids = ai_session.skip_remaining()
        apply_legacy_ai_queue_state(owner, ai_session)
    for pending_id in pending_ids:
        await owner._send_ai_event(
            terminal_events.ai_command_status(
                item_id=pending_id,
                status="skipped",
                reason="goal_achieved",
            )
        )
