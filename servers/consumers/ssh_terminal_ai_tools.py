"""Terminal AI explain, report, history, and plan helpers."""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from servers.consumers.ssh_terminal_constants import (
    _TERMINAL_AI_LLM_SEMAPHORE,
)
from servers.services import terminal_events, terminal_input
from servers.services.terminal_ai.legacy_state import (
    apply_legacy_ai_queue_state,
    sync_legacy_ai_queue_state,
)
from servers.services.terminal_ai.plan_insertions import (
    TerminalAiPlanReservation,
    reserve_adaptive_step_plan_item,
    reserve_retry_plan_item,
)

_TermSize = terminal_input.TerminalSize


class SSHTerminalAiToolsMixin:
    async def _handle_ai_explain_output(self, content: dict[str, Any]):
        """A6: turn a (command, output, exit_code) triple into a short
        human-readable explanation via the cheap ``terminal_chat`` bucket.

        Frontend sends::

            { type: "ai_explain_output", id: <cmd_id>, cmd, output, exit_code, question? }

        We reply with a single ``ai_explanation`` event keyed by the same
        ``id`` so the UI can render it inline next to the command card.
        """
        payload = content if isinstance(content, dict) else {}
        cmd = str(payload.get("cmd") or payload.get("command") or "").strip()
        output = str(payload.get("output") or "")
        cmd_id = payload.get("id")
        question = str(payload.get("question") or "").strip()
        try:
            exit_code: int | None = int(payload.get("exit_code"))
        except (TypeError, ValueError):
            exit_code = None

        if not cmd and not output:
            await self._send_ai_event(terminal_events.ai_error("Нужна команда и её вывод для объяснения."))
            return

        from servers.services.terminal_ai import explain_command_output

        await self._send_ai_event(terminal_events.ai_status("explaining", id=cmd_id))

        try:
            text = await explain_command_output(
                command=cmd,
                output=output,
                exit_code=exit_code,
                user_question=question,
                semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
            )
            await self._send_ai_event(terminal_events.ai_explanation(item_id=cmd_id, command=cmd, explanation=text))
        except Exception as exc:
            logger.warning("AI output explanation failed: %s", exc)
            await self._send_ai_event(terminal_events.ai_error("Не удалось объяснить вывод команды."))
        finally:
            await self._send_ai_event(terminal_events.ai_status("idle"))

    async def _handle_ai_generate_report(self, content: dict[str, Any]):
        force_regenerate = self._parse_bool((content or {}).get("force"), False)
        async with self._ai_lock:
            if self._ai_run.has_active_task():
                await self._send_ai_event(terminal_events.ai_error("Дождитесь завершения текущего запуска ассистента."))
                return
            done_items = list(self._ai_last_done_items or [])
            user_message = str(self._ai_user_message or "")
            cached_report = "" if force_regenerate else str(self._ai_last_report or "")

        if not done_items:
            await self._send_ai_event(terminal_events.ai_error("Нет завершённых команд для формирования отчёта."))
            return

        try:
            await self._send_ai_event(terminal_events.ai_status("generating_report"))
            report = cached_report or await self._generate_ai_report_text(user_message, done_items)
            status = self._compute_report_status(done_items)
            await self._send_ai_event(terminal_events.ai_report(report=report, status=status))
            async with self._ai_lock:
                self._ai_last_report = report
            if bool(self._ai_settings.get("memory_enabled", True)):
                self._add_to_history("assistant", f"[Ручной отчёт]\n{report[:400]}")
        except Exception as exc:
            await self._send_ai_event(terminal_events.ai_error(str(exc) or "Не удалось сформировать отчёт"))
        finally:
            await self._send_ai_event(terminal_events.ai_status("idle"))

    def _add_to_history(self, role: str, text: str) -> None:
        """Append a message to the conversation history (in-memory + DB, F2-9).

        The in-memory deque is the fast path used by every prompt builder;
        we additionally fire-and-forget a DB write so the conversation
        survives WebSocket reconnects and page reloads.
        """
        if not bool(getattr(self, "_ai_settings", {}).get("memory_enabled", True)):
            return
        entry = {"role": role, "text": (text or "")[:800]}
        if not hasattr(self, "_ai_history"):
            self._ai_history = []
        self._ai_history.append(entry)
        ttl_requests = int(getattr(self, "_ai_settings", {}).get("memory_ttl_requests", 6) or 6)
        max_entries = max(4, min(ttl_requests, 20) * 6)
        if len(self._ai_history) > max_entries:
            self._ai_history = self._ai_history[-max_entries:]

        # F2-9: persist to DB in a tracked background task so UX is not
        # slowed down by the extra INSERT + pruning queries.
        try:
            user_id = int(getattr(self, "_user_id", 0) or 0)
            server_id = int(getattr(self.server, "id", 0) or 0) if getattr(self, "server", None) else 0
            if user_id and server_id and entry["text"]:
                from servers.services.terminal_ai import append_message as _append_history

                task = asyncio.create_task(
                    _append_history(
                        user_id=user_id,
                        server_id=server_id,
                        role=role,
                        text=entry["text"],
                        max_entries=max_entries * 2,
                    )
                )
                self._ai_background_tasks.add(task)
                task.add_done_callback(self._ai_background_tasks.discard)
        except RuntimeError:
            # No running event loop (e.g. synchronous test harness) — skip.
            pass
        except Exception as exc:  # pragma: no cover — non-fatal
            logger.debug("terminal-ai chat history persist skipped: %s", exc)

    def _build_plan_item(
        self,
        item_id: int,
        cmd: str,
        why: str,
        forbidden_patterns: list[str] | None = None,
        allowlist_patterns: list[str] | None = None,
        confirm_dangerous_commands: bool = True,
        exec_mode: str | None = None,
    ) -> dict[str, Any]:
        from servers.services.terminal_ai import build_plan_item

        return build_plan_item(
            item_id=item_id,
            command=cmd,
            why=why,
            chat_mode=getattr(self, "_ai_chat_mode", "agent"),
            forbidden_patterns=forbidden_patterns,
            allowlist_patterns=allowlist_patterns,
            confirm_dangerous_commands=confirm_dangerous_commands,
            exec_mode=exec_mode,
            read_only=bool(getattr(getattr(self, "server", None), "ai_read_only", False)),
        )

    def _legacy_direct_exec_enabled(self) -> bool:
        """Whether legacy Terminal AI may use the non-PTY direct executor."""
        return self._normalize_execution_mode(getattr(self, "_ai_execution_mode", "agent")) != "fast"

    @staticmethod
    def _normalize_command_text(cmd: str) -> str:
        from servers.services.terminal_ai import normalize_command_text

        return normalize_command_text(cmd)

    async def _reserve_ai_retry_item(self, retries: int) -> TerminalAiPlanReservation:
        async with self._ai_lock:
            ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
            reservation = reserve_retry_plan_item(ai_session, self._ai_error_retries, retries=retries)
            apply_legacy_ai_queue_state(self, ai_session)
            return reservation

    async def _reserve_ai_adaptive_item(self, extra_limit: int) -> TerminalAiPlanReservation | None:
        async with self._ai_lock:
            ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
            reservation = reserve_adaptive_step_plan_item(ai_session, extra_limit=extra_limit)
            apply_legacy_ai_queue_state(self, ai_session)
            return reservation

    def _build_reserved_plan_item(
        self,
        reservation: TerminalAiPlanReservation,
        *,
        cmd: str,
        why: str,
        no_recovery: bool = False,
    ) -> dict[str, Any]:
        item = self._build_plan_item(
            item_id=reservation.item_id,
            cmd=cmd,
            why=why,
            forbidden_patterns=reservation.forbidden_patterns,
            allowlist_patterns=list(self._ai_allowlist_patterns or []),
            confirm_dangerous_commands=bool(self._ai_settings.get("confirm_dangerous_commands", True)),
        )
        if no_recovery:
            item["_no_recovery"] = True
        return item

    async def _insert_ai_plan_item(self, item: dict[str, Any], *, at_cursor: bool) -> None:
        async with self._ai_lock:
            ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
            if at_cursor:
                ai_session.insert_at_cursor(item)
            else:
                ai_session.insert_after_current(item)
            apply_legacy_ai_queue_state(self, ai_session)
