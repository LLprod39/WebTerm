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
from django.db.models import Q
from django.utils import timezone
from loguru import logger

from app.core.llm_context import operator_thinking_mode
from core_ui.models.chat import ChatMessage, ChatTurnState, OperatorTurnDispatch
from core_ui.services.assistant_chat import cancel_action, execute_action, serialize_action
from core_ui.services.operator_loop import OperatorTurnResult
from core_ui.services.operator_session import handle_operator_message, resume_after_action

TERMINAL_DISPATCH_SNAPSHOT_WINDOW = timedelta(minutes=10)
# Cloud / API defaults; local Ollama/LM Studio get a longer wall-clock budget.
OPERATOR_TURN_TIMEOUT_SECONDS = 90
OPERATOR_TURN_TIMEOUT_LOCAL_SECONDS = 300


def resolve_operator_turn_timeout_seconds(
    *,
    provider_binding: dict[str, Any] | None = None,
) -> float:
    """Wall-clock timeout for one Operator turn.

    Precedence: env ``OPERATOR_TURN_TIMEOUT_SECONDS`` → ModelConfig.operator_turn_timeout_seconds
    → local providers (ollama / lmstudio / openai_compatible localhost) 300s → else 90s.
    """
    import os

    try:
        env_raw = int(os.environ.get("OPERATOR_TURN_TIMEOUT_SECONDS") or 0)
        if env_raw >= 30:
            return float(env_raw)
    except (TypeError, ValueError):
        pass
    try:
        from app.core.model_config import model_manager

        model_manager.load_config()
        cfg_raw = int(getattr(model_manager.config, "operator_turn_timeout_seconds", 0) or 0)
        if cfg_raw >= 30:
            return float(cfg_raw)
    except Exception:  # noqa: BLE001
        pass

    provider = ""
    if isinstance(provider_binding, dict):
        provider = str(
            provider_binding.get("provider")
            or provider_binding.get("provider_name")
            or provider_binding.get("kind")
            or ""
        ).strip().lower()
    if not provider:
        try:
            from app.core.model_config import model_manager

            model_manager.load_config()
            provider = str(getattr(model_manager.config, "chat_provider", "") or "").strip().lower()
        except Exception:  # noqa: BLE001
            provider = ""
    if provider in {"ollama", "lmstudio", "lm_studio"} or provider.startswith("ollama"):
        return float(OPERATOR_TURN_TIMEOUT_LOCAL_SECONDS)
    if provider in {"openai_compatible", "openai-compatible"}:
        return float(OPERATOR_TURN_TIMEOUT_LOCAL_SECONDS)
    return float(OPERATOR_TURN_TIMEOUT_SECONDS)


def _summarize_failed_turn_progress(llm_messages: list[dict[str, Any]] | None) -> str:
    """Compact tool trail so the next user turn can continue from history."""
    tools: list[str] = []
    for msg in llm_messages or []:
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                raw_name = str(block.get("name") or "")
                name = raw_name if "." in raw_name else raw_name.replace("_", ".", 1)
                args = block.get("input") if isinstance(block.get("input"), dict) else {}
                hint = ""
                for key in ("q", "name", "server_id", "playbook_id", "command"):
                    if args.get(key) not in (None, ""):
                        hint = f" ({key}={args.get(key)})"
                        break
                tools.append(f"{name}{hint}"[:120])
            elif block.get("type") == "tool_result":
                preview = str(block.get("content") or "")[:160].replace("\n", " ")
                if tools:
                    tools[-1] = f"{tools[-1]} → {preview}"[:200]
    if not tools:
        return ""
    lines = "\n".join(f"- {item}" for item in tools[-12:])
    return (
        "Ход прерван до завершения. Уже сделано (продолжи с этого места, не начинай заново):\n"
        f"{lines}"
    )


async def _persist_turn_timeout_progress(
    *,
    chat_id: int,
    user_id: int,
    timeout_seconds: float,
) -> str:
    """Mark the running turn failed, keep tool progress in the assistant bubble."""
    timeout_message = (
        f"Оператор не успел завершить ответ модели (таймаут {int(timeout_seconds)}с). "
        "Можно продолжить тем же запросом — прогресс сохранён в истории — "
        "или проверьте AI-провайдера в Настройках → AI."
    )

    def _apply() -> str:
        turns = list(
            ChatTurnState.objects.filter(
                session_id=chat_id,
                session__user_id=user_id,
                status__in={ChatTurnState.STATUS_RUNNING, ChatTurnState.STATUS_RESUMING},
            )
            .select_related("assistant_message")
            .order_by("-id")[:3]
        )
        note = timeout_message
        for turn in turns:
            progress = _summarize_failed_turn_progress(
                turn.llm_messages if isinstance(turn.llm_messages, list) else []
            )
            body = timeout_message if not progress else f"{timeout_message}\n\n{progress}"
            note = body
            turn.status = ChatTurnState.STATUS_FAILED
            turn.error = "turn_timeout"
            turn.save(update_fields=["status", "error", "updated_at"])
            assistant = turn.assistant_message
            if assistant is not None:
                existing = str(assistant.content or "").strip()
                assistant.content = body if not existing else f"{existing.rstrip()}\n\n{body}"
                meta = dict(assistant.metadata or {})
                meta["turn_timeout"] = True
                meta["turn_id"] = turn.pk
                assistant.metadata = meta
                assistant.save(update_fields=["content", "metadata"])
        return note

    return await sync_to_async(_apply)()


def operator_group_name(chat_id: int) -> str:
    return f"operator_chat_{int(chat_id)}"


async def is_chat_busy(chat_id: int) -> bool:
    from core_ui.services.operator_dispatch import operator_dispatch_busy

    return await sync_to_async(operator_dispatch_busy)(int(chat_id))


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
            issues.append(f"Channel layer ({cname}) недоступен: {str(exc)[:120]}. События чата не дойдут до браузера.")

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
                issues.append(f"LLM (Ollama) недоступен: {detail}. Ходы будут висеть на «думает».")
        else:
            checks["llm"] = "ok (cloud provider)"
    except Exception as exc:  # noqa: BLE001
        checks["llm"] = "unknown"
        issues.append(f"Не удалось проверить LLM: {str(exc)[:120]}")

    return {"ok": not issues, "checks": checks, "issues": issues}


async def get_active_turn_snapshot(chat_id: int, user_id: int) -> dict[str, Any] | None:
    """Return an active turn or a recent pre-persistence terminal acknowledgement."""

    def _load() -> dict[str, Any] | None:
        from core_ui.services.operator_dispatch import release_expired_operator_dispatches
        from core_ui.services.operator_plan import get_plan_from_message, reconcile_plan_state

        stale_before = timezone.now() - timedelta(seconds=90)
        stale_qs = ChatTurnState.objects.filter(
            session_id=chat_id,
            session__user_id=user_id,
            status__in={ChatTurnState.STATUS_RUNNING, ChatTurnState.STATUS_RESUMING},
            updated_at__lt=stale_before,
        ).select_related("assistant_message")
        stale_turns = list(stale_qs)
        for stale in stale_turns:
            stale.status = ChatTurnState.STATUS_FAILED
            stale.error = "worker_heartbeat_lost"
            stale.save(update_fields=["status", "error", "updated_at"])
            reconcile_plan_state(stale.assistant_message, stale, reason="worker_heartbeat_lost")
        release_expired_operator_dispatches(session_id=chat_id)
        now = timezone.now()
        dispatch = (
            OperatorTurnDispatch.objects.filter(session_id=chat_id, session__user_id=user_id)
            .filter(
                Q(status=OperatorTurnDispatch.STATUS_QUEUED)
                | Q(status=OperatorTurnDispatch.STATUS_CLAIMED, lease_expires_at__gt=now)
            )
            .order_by("-id")
            .first()
        )
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
        if turn is None and dispatch is None:
            terminal_dispatch = (
                OperatorTurnDispatch.objects.filter(
                    session_id=chat_id,
                    session__user_id=user_id,
                    kind=OperatorTurnDispatch.KIND_MESSAGE,
                    status__in={
                        OperatorTurnDispatch.STATUS_COMPLETED,
                        OperatorTurnDispatch.STATUS_FAILED,
                        OperatorTurnDispatch.STATUS_CANCELED,
                    },
                    completed_at__gte=timezone.now() - TERMINAL_DISPATCH_SNAPSHOT_WINDOW,
                )
                .order_by("-completed_at", "-id")
                .first()
            )
            if terminal_dispatch is not None:
                terminal_user_text = str(
                    (terminal_dispatch.payload or {}).get("message") or "",
                ).strip()
                has_durable_user_message = bool(
                    terminal_user_text
                    and ChatMessage.objects.filter(
                        session_id=chat_id,
                        role=ChatMessage.ROLE_USER,
                        content=terminal_user_text,
                        created_at__gte=terminal_dispatch.queued_at,
                    ).exists()
                )
                if terminal_user_text and not has_durable_user_message:
                    # A completed message dispatch cannot be a successful turn
                    # when it never persisted its user row. The worker already
                    # emitted an error before swallowing the preflight failure;
                    # reconnects need the same terminal meaning.
                    terminal_status = (
                        "cancelled" if terminal_dispatch.status == OperatorTurnDispatch.STATUS_CANCELED else "failed"
                    )
                    return {
                        "type": "turn_snapshot",
                        "chat_id": chat_id,
                        "turn_id": None,
                        "status": terminal_status,
                        "iteration": 0,
                        "busy": False,
                        "assistant_message_id": None,
                        "assistant_text": "",
                        "user_message_id": None,
                        "user_text": terminal_user_text,
                        "pending_action": None,
                        "in_process": False,
                    }
        if turn is None and dispatch is None:
            return None
        if turn is None:
            return {
                "type": "turn_snapshot",
                "chat_id": chat_id,
                "turn_id": None,
                "status": dispatch.status,
                "iteration": 0,
                "busy": True,
                "assistant_message_id": None,
                "assistant_text": "",
                "user_message_id": None,
                "user_text": str((dispatch.payload or {}).get("message") or ""),
                "pending_action": None,
                "in_process": dispatch.status == OperatorTurnDispatch.STATUS_CLAIMED,
            }
        assistant = turn.assistant_message
        user_msg = turn.user_message
        action_payload = None
        if turn.pending_action_id and turn.pending_action:
            action_payload = serialize_action(turn.pending_action)
        plan_payload = get_plan_from_message(assistant)
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
            or dispatch is not None,
            "assistant_message_id": assistant.pk if assistant else None,
            "assistant_text": (assistant.content or "") if assistant else "",
            "user_message_id": user_msg.pk if user_msg else None,
            "user_text": (user_msg.content or "") if user_msg else "",
            "pending_action": action_payload,
            "plan": plan_payload,
            "in_process": bool(dispatch and dispatch.status == OperatorTurnDispatch.STATUS_CLAIMED),
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
    from core_ui.services.operator_dispatch import cancel_operator_dispatches

    canceled_dispatches = await sync_to_async(cancel_operator_dispatches)(chat_id)

    def _close_open_turns() -> list[int]:
        from core_ui.services.operator_plan import reconcile_plan_state

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
            reconcile_plan_state(msg, turn, reason="stopped_by_user")
            closed.append(turn.pk)
        return closed

    closed_ids = await sync_to_async(_close_open_turns)()
    if not (canceled_dispatches or closed_ids):
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
    "почему",
    "разбер",
    "диагност",
    "инцидент",
    "проанализир",
    "анализ",
    "сравни",
    "сравнен",
    "план ",
    "спланир",
    "стратег",
    "оптимизир",
    "рекоменд",
    "объясни",
    "root cause",
    "почему-то",
    "расследуй",
    "troubleshoot",
    "investigate",
    "analyze",
    "compare",
    "plan ",
    "why ",
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
    provider_binding: dict[str, Any] | None = None,
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
            handle_operator_message(
                session,
                user,
                message,
                on_event=on_event,
                provider_binding=provider_binding,
            ),
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
        turn_timeout = resolve_operator_turn_timeout_seconds(provider_binding=provider_binding)
        result = await asyncio.wait_for(work_task, timeout=turn_timeout)
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
    except TimeoutError:
        turn_timeout = resolve_operator_turn_timeout_seconds(provider_binding=provider_binding)
        if work_task is not None and not work_task.done():
            work_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await work_task
        timeout_message = await _persist_turn_timeout_progress(
            chat_id=chat_id,
            user_id=user.id,
            timeout_seconds=turn_timeout,
        )
        await broadcast_operator_event(
            chat_id,
            {
                "type": "error",
                "message": timeout_message,
            },
        )
        await broadcast_operator_event(
            chat_id,
            {
                "type": "token",
                "text": f"\n\n{timeout_message}",
                "synthetic": True,
                "chat_id": chat_id,
            },
        )
        await broadcast_operator_event(
            chat_id,
            {"type": "turn_done", "status": "failed", "chat_id": chat_id},
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

            def _validate_mark_then_execute():
                from core_ui.services.operator_plan import (
                    mark_executing_after_typed_confirm_ok,
                    revert_plan_executing_to_awaiting_confirm,
                )

                # Typed-confirm must succeed BEFORE flipping the plan step to running.
                action_local, typed_error = mark_executing_after_typed_confirm_ok(
                    action, typed_confirm=typed_confirm
                )
                if typed_error:
                    return action_local
                action_local = execute_action(
                    action_local, confirmed=True, typed_confirm=typed_confirm
                )
                # Safety net: if execute still bounced to confirm (race), undo running.
                if (
                    action_local.status == action_local.STATUS_REQUIRES_CONFIRMATION
                    and action_local.error
                ):
                    turn = (
                        ChatTurnState.objects.filter(
                            pending_action=action_local,
                            status=ChatTurnState.STATUS_AWAITING_CONFIRM,
                        )
                        .select_related("assistant_message")
                        .first()
                    )
                    if turn is not None and turn.assistant_message is not None:
                        revert_plan_executing_to_awaiting_confirm(
                            message=turn.assistant_message,
                            action_type=action_local.action_type,
                            title=action_local.title or "",
                            turn=turn,
                        )
                return action_local

            action = await sync_to_async(_validate_mark_then_execute)()
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


async def start_message_turn(
    *,
    chat_id: int,
    session,
    user,
    message: str,
    thinking: Any = None,
    provider_binding: dict[str, Any] | None = None,
) -> bool:
    """Schedule a message turn. Returns False if chat already has a running task."""
    chat_id = int(chat_id)
    mode = _normalize_thinking(thinking)
    from core_ui.services.operator_dispatch import enqueue_operator_message

    dispatch = await sync_to_async(enqueue_operator_message)(
        session=session,
        message=message,
        thinking=mode,
        provider_binding=provider_binding,
    )
    return dispatch is not None


async def start_action_turn(
    *,
    chat_id: int,
    action,
    confirm: bool,
    typed_confirm: str | None = None,
    thinking: Any = None,
) -> bool:
    chat_id = int(chat_id)
    mode = _normalize_thinking(thinking)
    from core_ui.services.operator_dispatch import enqueue_operator_action

    dispatch = await sync_to_async(enqueue_operator_action)(
        session=action.session,
        action=action,
        confirm=confirm,
        typed_confirm=typed_confirm,
        thinking=mode,
    )
    return dispatch is not None


async def run_claimed_operator_dispatch(dispatch: OperatorTurnDispatch) -> None:
    """Execute a lease-owned dispatch without relying on backend-local registries."""
    payload = dict(dispatch.payload or {})
    if dispatch.kind == OperatorTurnDispatch.KIND_MESSAGE:
        await _run_message_turn(
            chat_id=dispatch.session_id,
            session=dispatch.session,
            user=dispatch.session.user,
            message=str(payload.get("message") or ""),
            thinking=_normalize_thinking(payload.get("thinking")),
            provider_binding=payload.get("provider_binding"),
        )
        return
    if dispatch.kind == OperatorTurnDispatch.KIND_ACTION and dispatch.action is not None:
        await _run_action_turn(
            chat_id=dispatch.session_id,
            action=dispatch.action,
            confirm=bool(payload.get("confirm")),
            typed_confirm=str(payload.get("typed_confirm") or "").strip() or None,
            thinking=_normalize_thinking(payload.get("thinking")),
        )
        return
    raise ValueError(f"Unsupported operator dispatch kind: {dispatch.kind}")
