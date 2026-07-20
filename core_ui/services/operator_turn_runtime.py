"""Background operator turns that outlive a single WebSocket connection.

Turns run as asyncio tasks on the ASGI event loop. Live events are fan-out via
Channels group ``operator_chat_{chat_id}`` so reconnecting clients resume the stream.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from typing import Any

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from django.utils import timezone
from loguru import logger

from app.core.llm_context import operator_thinking_mode
from core_ui.models import ChatTurnState
from core_ui.services.assistant_chat import cancel_action, execute_action, serialize_action
from core_ui.services.operator_loop import OperatorTurnResult
from core_ui.services.operator_session import handle_operator_message, resume_after_action

_ACTIVE_TASKS: dict[int, asyncio.Task[Any]] = {}
_ACTIVE_META: dict[int, dict[str, Any]] = {}


def operator_group_name(chat_id: int) -> str:
    return f"operator_chat_{int(chat_id)}"


def is_chat_busy(chat_id: int) -> bool:
    task = _ACTIVE_TASKS.get(int(chat_id))
    return bool(task and not task.done())


async def broadcast_operator_event(chat_id: int, event: dict[str, Any]) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    payload = dict(event or {})
    payload.setdefault("chat_id", int(chat_id))
    try:
        await layer.group_send(
            operator_group_name(chat_id),
            {"type": "operator.event", "event": payload},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("operator event broadcast failed chat_id={}: {}", chat_id, exc)


async def operator_health(*, timeout: float = 3.0) -> dict[str, Any]:
    """Best-effort readiness probe for the operator chat pipeline.

    Surfaces the two failure modes that otherwise die silently: the channel layer
    (events never reach the browser) and the LLM backend (turn thinks forever).
    Returns ``{ok, checks: {...}, issues: [str]}``.
    """
    checks: dict[str, str] = {}
    issues: list[str] = []

    layer = get_channel_layer()
    if layer is None:
        checks["channel_layer"] = "missing"
        issues.append("Channel layer не настроен — стрим чата работать не будет.")
    else:
        cname = type(layer).__name__
        try:
            test_chan = await asyncio.wait_for(layer.new_channel(), timeout=timeout)
            await asyncio.wait_for(layer.group_add("operator_health", test_chan), timeout=timeout)
            await layer.group_discard("operator_health", test_chan)
            checks["channel_layer"] = f"ok ({cname})"
        except Exception as exc:  # noqa: BLE001
            checks["channel_layer"] = f"error ({cname})"
            issues.append(
                f"Channel layer ({cname}) недоступен: {str(exc)[:120]}. "
                "События чата не дойдут до браузера."
            )

    try:
        from app.core.llm import get_provider
        from app.core.model_config import model_manager

        provider = get_provider()
        if model_manager.config.ollama_enabled:
            targets = provider._build_ollama_request_targets(  # noqa: SLF001
                model_manager.get_chat_model("ollama") or ""
            )
            reachable = False
            detail = "no runtime configured"
            if targets:
                import aiohttp

                base_url = targets[0]["base_url"]
                headers = dict(targets[0]["headers"])
                try:
                    ct = aiohttp.ClientTimeout(total=timeout)
                    async with (
                        aiohttp.ClientSession(timeout=ct) as session,
                        session.get(f"{base_url}/api/tags", headers=headers) as resp,
                    ):
                        reachable = resp.status == 200
                        detail = base_url if reachable else f"HTTP {resp.status}"
                except Exception as exc:  # noqa: BLE001
                    detail = f"{base_url}: {str(exc)[:80]}"
            checks["llm"] = f"ok ({detail})" if reachable else f"unreachable ({detail})"
            if not reachable:
                issues.append(
                    f"LLM (Ollama) недоступен: {detail}. Ходы будут висеть на «думает»."
                )
        else:
            checks["llm"] = "ok (cloud provider)"
    except Exception as exc:  # noqa: BLE001
        checks["llm"] = "unknown"
        issues.append(f"Не удалось проверить LLM: {str(exc)[:120]}")

    return {"ok": not issues, "checks": checks, "issues": issues}


async def get_active_turn_snapshot(chat_id: int, user_id: int) -> dict[str, Any] | None:
    """Return a reconnect snapshot if a turn is still open for this chat."""

    def _load() -> dict[str, Any] | None:
        stale_before = timezone.now() - timedelta(seconds=90)
        ChatTurnState.objects.filter(
            session_id=chat_id,
            session__user_id=user_id,
            status__in={ChatTurnState.STATUS_RUNNING, ChatTurnState.STATUS_RESUMING},
            updated_at__lt=stale_before,
        ).update(status=ChatTurnState.STATUS_FAILED, error="worker_heartbeat_lost")
        turn = (
            ChatTurnState.objects.filter(
                session_id=chat_id,
                session__user_id=user_id,
                status__in={
                    ChatTurnState.STATUS_RUNNING,
                    ChatTurnState.STATUS_RESUMING,
                    ChatTurnState.STATUS_AWAITING_ASYNC,
                    ChatTurnState.STATUS_AWAITING_CONFIRM,
                },
            )
            .select_related("assistant_message", "user_message", "pending_action")
            .order_by("-id")
            .first()
        )
        if turn is None:
            return None
        assistant = turn.assistant_message
        user_msg = turn.user_message
        action_payload = None
        if turn.pending_action_id and turn.pending_action:
            action_payload = serialize_action(turn.pending_action)
        return {
            "type": "turn_snapshot",
            "chat_id": chat_id,
            "turn_id": turn.pk,
            "status": turn.status,
            "iteration": turn.iteration,
            "busy": turn.status
            in {
                ChatTurnState.STATUS_RUNNING,
                ChatTurnState.STATUS_RESUMING,
                ChatTurnState.STATUS_AWAITING_ASYNC,
            }
            or is_chat_busy(chat_id),
            "assistant_message_id": assistant.pk if assistant else None,
            "assistant_text": (assistant.content or "") if assistant else "",
            "user_message_id": user_msg.pk if user_msg else None,
            "user_text": (user_msg.content or "") if user_msg else "",
            "pending_action": action_payload,
            "in_process": is_chat_busy(chat_id),
        }

    return await sync_to_async(_load)()


STOP_NOTE = "\n\n_⏹ Остановлено пользователем._"


async def stop_active_turn(chat_id: int, user_id: int | None = None) -> bool:
    """Cancel the in-flight turn for a chat and close its DB state.

    Returns True when something was actually stopped. Parked turns
    (awaiting_confirm / awaiting_async) are not touched — those are
    resolved through the confirm/cancel flow instead.
    """
    chat_id = int(chat_id)
    task = _ACTIVE_TASKS.pop(chat_id, None)
    _ACTIVE_META.pop(chat_id, None)
    cancelled_task = False
    if task and not task.done():
        task.cancel()
        cancelled_task = True
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        except Exception:  # noqa: BLE001 — task failure still counts as stopped
            pass

    def _close_open_turns() -> list[int]:
        qs = ChatTurnState.objects.filter(
            session_id=chat_id,
            status__in={ChatTurnState.STATUS_RUNNING, ChatTurnState.STATUS_RESUMING},
        )
        if user_id is not None:
            qs = qs.filter(session__user_id=user_id)
        closed: list[int] = []
        for turn in qs.select_related("assistant_message"):
            turn.status = ChatTurnState.STATUS_DONE
            turn.error = "stopped_by_user"
            turn.save(update_fields=["status", "error", "updated_at"])
            msg = turn.assistant_message
            if msg is not None and STOP_NOTE.strip() not in (msg.content or ""):
                msg.content = (msg.content or "") + STOP_NOTE
                msg.metadata = {**(msg.metadata or {}), "stopped_by_user": True}
                msg.save(update_fields=["content", "metadata"])
            closed.append(turn.pk)
        return closed

    closed_ids = await sync_to_async(_close_open_turns)()
    if not (cancelled_task or closed_ids):
        return False
    await broadcast_operator_event(
        chat_id,
        {
            "type": "turn_done",
            "status": "stopped",
            "turn_id": closed_ids[0] if closed_ids else None,
        },
    )
    logger.info("operator turn stopped chat_id={} turns={}", chat_id, closed_ids)
    return True


# Terms that signal a turn worth deep reasoning. Everything else runs on light
# thinking to cut latency (measured: think=low ≈2.7s vs high ≈4.0s per call).
# NB: think must never be fully "off" here — Ollama's qwen3 tool grammar 500s
# without thinking, so the fast tier is "low", not disabled.
_COMPLEX_THINKING_HINTS = (
    "почему", "разбер", "диагност", "инцидент", "проанализир", "анализ",
    "сравни", "сравнен", "план ", "спланир", "стратег", "оптимизир",
    "рекоменд", "объясни", "root cause", "почему-то", "расследуй",
    "troubleshoot", "investigate", "analyze", "compare", "plan ", "why ",
)


def classify_turn_thinking(message: str) -> str:
    """Pick a thinking tier for an operator turn (no explicit user override).

    Returns "high" for analytical/planning intents (or long prompts), "low"
    otherwise. Kept deliberately cheap — a keyword + length heuristic.
    """
    text = (message or "").strip().lower()
    if len(text) > 220:
        return "high"
    if any(hint in text for hint in _COMPLEX_THINKING_HINTS):
        return "high"
    return "low"


def _normalize_thinking(value: Any) -> str | None:
    # Absent value = no per-turn override — the global (admin) model config decides.
    if value is None:
        return None
    if value is False:
        return "off"
    if value is True:
        return "on"
    text = str(value).strip().lower()
    if text in {"", "auto", "default"}:
        return None
    if text in {"off", "false", "0", "none"}:
        return "off"
    if text in {"on", "true", "1"}:
        return "on"
    if text in {"low", "medium", "high"}:
        return text
    return None


async def _run_message_turn(
    *,
    chat_id: int,
    session,
    user,
    message: str,
    thinking: str | None,
) -> None:
    # No explicit per-turn choice → pick a tier by intent (fast for simple asks).
    effective_thinking = thinking or classify_turn_thinking(message)
    token = operator_thinking_mode.set(effective_thinking)
    work_task: asyncio.Task[OperatorTurnResult] | None = None
    heartbeat_task: asyncio.Task[Any] | None = None
    try:
        async def on_event(event: dict[str, Any]) -> None:
            await broadcast_operator_event(chat_id, event)

        work_task = asyncio.create_task(
            handle_operator_message(session, user, message, on_event=on_event),
            name=f"operator-work-{chat_id}",
        )

        async def _heartbeat() -> None:
            while work_task is not None and not work_task.done():
                await asyncio.sleep(10)
                touched = await sync_to_async(
                    lambda: ChatTurnState.objects.filter(
                        session_id=chat_id,
                        session__user_id=user.id,
                        status__in={ChatTurnState.STATUS_RUNNING, ChatTurnState.STATUS_RESUMING},
                    ).update(updated_at=timezone.now())
                )()
                # A different worker/user stop closed the DB state.
                if touched == 0 and work_task is not None and not work_task.done():
                    work_task.cancel()
                    return

        heartbeat_task = asyncio.create_task(_heartbeat(), name=f"operator-heartbeat-{chat_id}")
        result = await asyncio.wait_for(work_task, timeout=300)
        await broadcast_operator_event(
            chat_id,
            {
                "type": "turn_complete",
                "status": result.status,
                "assistant_message_id": result.assistant_message.pk if result.assistant_message else None,
                "user_message_id": result.user_message.pk if result.user_message else None,
                "actions": [serialize_action(a) for a in result.actions if a],
            },
        )
    except asyncio.TimeoutError:
        await sync_to_async(
            lambda: ChatTurnState.objects.filter(
                session_id=chat_id,
                session__user_id=user.id,
                status__in={ChatTurnState.STATUS_RUNNING, ChatTurnState.STATUS_RESUMING},
            ).update(status=ChatTurnState.STATUS_FAILED, error="turn_timeout")
        )()
        await broadcast_operator_event(
            chat_id,
            {
                "type": "error",
                "message": "Оператор завис на ответе модели (таймаут 300с). Попробуй ещё раз короче.",
            },
        )
    except ValueError as exc:
        await broadcast_operator_event(chat_id, {"type": "error", "message": str(exc)})
    except Exception as exc:  # noqa: BLE001
        logger.exception("operator background message failed chat_id={}: {}", chat_id, exc)
        await broadcast_operator_event(
            chat_id,
            {"type": "error", "message": str(exc) or "Operator turn failed"},
        )
    finally:
        if heartbeat_task is not None and not heartbeat_task.done():
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
        operator_thinking_mode.reset(token)
        _ACTIVE_TASKS.pop(int(chat_id), None)
        _ACTIVE_META.pop(int(chat_id), None)


async def _run_action_turn(
    *,
    chat_id: int,
    action,
    confirm: bool,
    typed_confirm: str | None,
    thinking: str | None,
) -> None:
    token = operator_thinking_mode.set(thinking)
    try:
        async def on_event(event: dict[str, Any]) -> None:
            await broadcast_operator_event(chat_id, event)

        if confirm:
            action = await sync_to_async(execute_action)(
                action, confirmed=True, typed_confirm=typed_confirm
            )
        else:
            action = await sync_to_async(cancel_action)(action)

        await broadcast_operator_event(
            chat_id,
            {"type": "action_update", "action": serialize_action(action)},
        )

        if confirm and action.status == action.STATUS_RUNNING:
            await broadcast_operator_event(
                chat_id,
                {"type": "error", "message": "Action is already running in another worker."},
            )
            return

        if confirm and action.status == action.STATUS_REQUIRES_CONFIRMATION and action.error:
            await broadcast_operator_event(chat_id, {"type": "error", "message": action.error})
            return

        result = await resume_after_action(
            action=action,
            on_event=on_event,
            cancelled=not confirm,
        )
        if result is not None:
            await broadcast_operator_event(
                chat_id,
                {
                    "type": "turn_complete",
                    "status": result.status,
                    "assistant_message_id": result.assistant_message.pk if result.assistant_message else None,
                    "actions": [serialize_action(a) for a in result.actions if a],
                },
            )
        else:
            await broadcast_operator_event(
                chat_id,
                {"type": "turn_complete", "status": "done" if confirm else "cancelled"},
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("operator background action failed chat_id={}: {}", chat_id, exc)
        await broadcast_operator_event(
            chat_id,
            {"type": "error", "message": str(exc) or "Action failed"},
        )
    finally:
        operator_thinking_mode.reset(token)
        _ACTIVE_TASKS.pop(int(chat_id), None)
        _ACTIVE_META.pop(int(chat_id), None)


def start_message_turn(
    *,
    chat_id: int,
    session,
    user,
    message: str,
    thinking: Any = None,
) -> bool:
    """Schedule a message turn. Returns False if chat already has a running task."""
    chat_id = int(chat_id)
    if is_chat_busy(chat_id):
        return False
    mode = _normalize_thinking(thinking)
    task = asyncio.create_task(
        _run_message_turn(
            chat_id=chat_id,
            session=session,
            user=user,
            message=message,
            thinking=mode,
        ),
        name=f"operator-turn-{chat_id}",
    )
    _ACTIVE_TASKS[chat_id] = task
    _ACTIVE_META[chat_id] = {"kind": "message", "thinking": mode}
    return True


def start_action_turn(
    *,
    chat_id: int,
    action,
    confirm: bool,
    typed_confirm: str | None = None,
    thinking: Any = None,
) -> bool:
    chat_id = int(chat_id)
    if is_chat_busy(chat_id):
        return False
    mode = _normalize_thinking(thinking)
    task = asyncio.create_task(
        _run_action_turn(
            chat_id=chat_id,
            action=action,
            confirm=confirm,
            typed_confirm=typed_confirm,
            thinking=mode,
        ),
        name=f"operator-action-{chat_id}",
    )
    _ACTIVE_TASKS[chat_id] = task
    _ACTIVE_META[chat_id] = {"kind": "action", "thinking": mode, "confirm": confirm}
    return True
