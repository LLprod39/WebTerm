"""Terminal AI agent run orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

from loguru import logger

from core_ui.audit import audit_context
from servers.services import terminal_events, terminal_input

_TermSize = terminal_input.TerminalSize


class TerminalAgentRunOperations:
    async def _run_ai_agent_background(
        self,
        *,
        user_message: str,
        chat_mode: str,
    ) -> None:
        cancelled = False
        try:
            with audit_context(**self._ai_state.audit_context):
                await self._ai_run_agent(
                    user_message=user_message,
                    chat_mode=chat_mode,
                )
        except asyncio.CancelledError:
            cancelled = True
        finally:
            async with self._ai_state.lock:
                self._ai_state.run.clear_task_if_current()
        if cancelled or self._ai_state.session.stop_requested:
            await self._send_ai_event(terminal_events.ai_status("idle"))
            return
        leftovers = [
            str(message).strip()
            for message in self._ai_state.nova_conversation.pending_user_messages
            if str(message).strip()
        ]
        if leftovers and self._transport_state.ssh_conn is not None:
            self._ai_state.nova_conversation.pending_user_messages[:] = leftovers[1:]
            self._ai_state.nova_conversation.running = True
            async with self._ai_state.lock:
                if not self._ai_state.run.has_active_task():
                    self._ai_state.run.start_task(
                        self._run_ai_agent_background(
                            user_message=leftovers[0],
                            chat_mode=chat_mode,
                        )
                    )
            return
        await self._send_ai_event(terminal_events.ai_status("idle"))

    async def _ai_run_agent(
        self,
        *,
        user_message: str,
        chat_mode: str,
    ) -> None:
        """Drive the Terminal Agent ReAct loop for one user turn.

        Builds an :class:`AgentContext` from the current SSH session,
        streams loop events to the client as ``agent_*`` WebSocket
        messages, and persists the final assistant reply to chat
        history on completion.
        """
        from servers.services.terminal_ai.agent import (
            AgentContext,
            default_tool_set,
            run_agent_loop,
        )
        from servers.services.terminal_ai.agent.tools import ServerTarget, UserPromptRequest

        if not self._transport_state.ssh_conn or not self.server:
            self._ai_state.nova_conversation.running = False
            await self._send_ai_event(terminal_events.ai_error("SSH connection required for agent mode"))
            return

        # Primary target = this session's server.
        nova_sudo_policy = str((self._ai_state.settings or {}).get("nova_sudo_policy") or "disabled")
        primary = ServerTarget(
            name="primary",
            server_id=int(self.server.id),
            display_name=str(self.server.name or ""),
            host=str(getattr(self.server, "host", "") or ""),
            ssh_conn=self._transport_state.ssh_conn,
            read_only=False,
            sudo_auth_mode=str(getattr(self.server, "sudo_auth_mode", "none") or "none"),
            is_primary=True,
        )

        extras = await self._ai_build_agent_extras()

        try:
            _, rules_context, _, _ = await self._get_ai_rules_and_forbidden(
                self._user_id,
                self.server.id,
            )
        except Exception:
            rules_context = ""

        memory_context = ""
        memory_enabled = bool((self._ai_state.settings or {}).get("memory_enabled", True))
        if memory_enabled:
            server_ids = [int(self.server.id)] + [int(t.server_id) for t in extras.values() if t.server_id]
            memory_context = await self._ai_build_agent_memory_context(server_ids)

        nova_context = await self._collect_nova_context_bundle()

        from servers.services.terminal_ai.hidden_pty import ensure_hidden_pty
        from servers.services.terminal_ai.nova_conversation import persist_nova_result, should_continue_nova

        conversation = self._ai_state.nova_conversation
        conversation.running = True
        try:
            self._transport_state.nova_pty = await ensure_hidden_pty(
                self._transport_state.nova_pty,
                self._transport_state.ssh_conn,
            )
        except Exception as exc:
            conversation.running = False
            await self._send_ai_event(terminal_events.ai_error(f"Не удалось открыть скрытый PTY Nova: {exc}"))
            return

        hidden_pty = self._transport_state.nova_pty
        nova_cwd = str((hidden_pty.cwd if hidden_pty is not None else "") or "")
        if nova_cwd:
            extra_cwd = f"- cwd скрытого PTY Nova: {nova_cwd}"
            if extra_cwd not in (nova_context.session_context or ""):
                updated_session_context = (
                    f"{nova_context.session_context}\n{extra_cwd}".strip()
                    if nova_context.session_context
                    else extra_cwd
                )
                nova_context = replace(nova_context, session_context=updated_session_context)

        async def _run_primary_shell(cmd: str, timeout: int = 30):
            session = self._transport_state.nova_pty
            if session is None:
                raise RuntimeError("hidden Nova PTY is not attached")
            cwd_before = str(session.cwd or "")
            exit_code, output = await session.run_command(cmd, timeout=float(timeout))
            self._append_nova_recent_activity(
                command=cmd,
                cwd=cwd_before,
                exit_code=int(exit_code),
                source="nova",
                output_tail=str(output or ""),
                cwd_after=str(session.cwd or cwd_before),
            )
            return exit_code, output

        def _hidden_cwd() -> str:
            session = self._transport_state.nova_pty
            return str(session.cwd or "") if session is not None else ""

        # ask_user pump: reuse the existing `ai_question` / `ai_reply`
        # bridge. The client already knows how to respond (same flow as
        # step-mode clarification questions); the agent loop just needs
        # to await the future for q_id.
        async def _prompt_user(request: UserPromptRequest) -> str | None:
            q_id = f"q_agent_{self._new_run_id()}"
            try:
                return await self._ai_state.run.ask_user(
                    q_id=q_id,
                    event={
                        "type": "ai_question",
                        "q_id": q_id,
                        "question": request.question,
                        "source": "agent",
                        "options": [
                            {
                                "label": option.label,
                                "value": option.value,
                                "description": option.description,
                            }
                            for option in request.options
                        ],
                        "allow_multiple": bool(request.allow_multiple),
                        "free_text_allowed": bool(request.free_text_allowed),
                        "placeholder": request.placeholder,
                    },
                    send_event=self._send_ai_event,
                    timeout_seconds=max(5.0, float(request.timeout_seconds)),
                )
            except TimeoutError:
                return None
            except asyncio.CancelledError:
                raise

        def _stop_requested() -> bool:
            return self._ai_state.session.stop_requested or not self._transport_state.ssh_proc

        # Event emitter — redacts secrets + tags run_id, same pipeline
        # the legacy ai_* events use.
        async def _emit(ev: dict[str, Any]) -> None:
            await self._send_ai_event(ev)

        # Lazy SSH-open for extras. The agent calls this on first use
        # of each extra target (via ``ctx.ensure_connection``) so we
        # never open sockets the loop doesn't actually touch.
        # ``extras_meta`` maps target name → server metadata for lookup.
        extras_meta = dict(extras)

        async def _open_target(target_name: str) -> Any | None:
            cached = self._ai_state.extra_connections.get(target_name)
            if cached is not None:
                return cached
            target = extras_meta.get(target_name)
            if target is None:
                return None
            conn = await self._open_agent_target_conn(target.server_id)
            if conn is not None:
                self._ai_state.extra_connections[target_name] = conn
            return conn

        ctx = AgentContext(
            user_message=user_message,
            primary=primary,
            extras=extras,
            user_id=self._user_id,
            emit=_emit,
            prompt_user=_prompt_user,
            open_target=_open_target,
            execution_context_factory=self._terminal_execution_context,
            stop_requested=_stop_requested,
            rules_context=rules_context,
            memory_context=memory_context,
            session_context=nova_context.session_context,
            recent_activity_context=nova_context.recent_activity_context,
            ui_context_payload=nova_context.ui_payload,
            dry_run=bool((self._ai_state.settings or {}).get("dry_run", False)),
            sudo_policy=nova_sudo_policy,
            seed_history=conversation.snapshot_history(),
            seed_todos=conversation.snapshot_todos(),
            pending_user_messages=conversation.pending_user_messages,
            continuation=should_continue_nova(conversation),
            run_primary_shell=_run_primary_shell,
            primary_cwd=_hidden_cwd(),
            primary_cwd_getter=_hidden_cwd,
        )

        result = None
        try:
            result = await run_agent_loop(ctx, default_tool_set())
        except asyncio.CancelledError:
            conversation.running = False
            raise
        except Exception as exc:  # noqa: BLE001 — never crash the consumer
            logger.warning("agent loop failed: %s", exc)
            await self._send_ai_event(terminal_events.ai_error(f"Agent loop failed: {exc}"))
            persist_nova_result(
                conversation,
                todos=conversation.snapshot_todos(),
                history=conversation.snapshot_history(),
                final_text=conversation.last_final_text,
            )
            return

        persist_nova_result(
            conversation,
            todos=list(result.todos or []),
            history=list(result.history or []),
            final_text=(result.final_text or "").strip(),
        )

        # Persist the final assistant reply to chat history so future
        # turns see it.
        final_text = (result.final_text or "").strip()

        # Fallback — when the loop halted before the model could emit
        # ``done`` (budget / timeout / stop), the user otherwise ends
        # up staring at a wall of tool calls with no summary. Surface
        # a short human-readable notice explaining what happened and
        # how many steps were completed so they know the agent *did*
        # work, just didn't finish cleanly.
        if not final_text and result.stopped:
            reason_label = {
                "max_iterations": "достигнут лимит шагов",
                "total_timeout": "истёк общий тайм-аут",
                "llm_timeout": "LLM не ответил вовремя",
                "llm_error": "ошибка LLM",
                "user_stop": "остановлено вами",
                "fatal_tool_error": "критическая ошибка инструмента",
                "cancelled": "выполнение отменено",
            }.get(result.stop_reason or "", result.stop_reason or "остановлен")
            final_text = (
                f"Не удалось завершить задачу: {reason_label}. "
                f"Выполнено шагов: {result.iterations}, "
                f"вызовов инструментов: {result.tool_calls}. "
                "Посмотрите историю инструментов выше или переформулируйте запрос."
            )

        if final_text:
            self._add_to_history("assistant", final_text)
            # Mirror into the legacy ai_response stream so clients that
            # only subscribed to the plan-based flow still see the answer.
            await self._send_ai_event({"type": "ai_response", "assistant_text": final_text})
