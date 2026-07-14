"""Terminal AI request and control handlers."""
from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from core_ui.activity import log_user_activity_async
from core_ui.audit import audit_context
from servers.services import terminal_events, terminal_input
from servers.services.terminal_ai.active_command import (
    cancel_exit_futures,
    clear_active_command,
)
from servers.services.terminal_ai.legacy_state import (
    apply_legacy_ai_queue_state,
    sync_legacy_ai_queue_state,
)

_TermSize = terminal_input.TerminalSize


class SSHTerminalAiControlsMixin:
    async def _handle_ai_stop(self):
        active_cmd_id = await self._interrupt_active_command()

        async with self._ai_lock:
            ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
            pending_to_skip = ai_session.request_stop(active_cmd_id)
            apply_legacy_ai_queue_state(self, ai_session)

        if active_cmd_id is not None:
            await self._send_ai_event(
                terminal_events.ai_command_status(item_id=active_cmd_id, status="cancelled", reason="stopped")
            )
        for cmd_id in pending_to_skip:
            await self._send_ai_event(
                terminal_events.ai_command_status(item_id=cmd_id, status="skipped", reason="stopped")
            )

        await self._cancel_ai()
        await self._send_ai_event(terminal_events.ai_status("idle"))

    async def _cancel_ai(self):
        # Can be called from disconnect/cleanup paths
        if not hasattr(self, "_ai_lock"):
            return
        async with self._ai_lock:
            await self._cancel_ai_locked()

    async def _cancel_ai_locked(self):
        self._ai_run.cancel_task(current=asyncio.current_task())

        cancel_exit_futures(self)

        self._ai_run.cancel_reply_futures()

        ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
        ai_session.clear()
        apply_legacy_ai_queue_state(self, ai_session)
        clear_active_command(self)

    @staticmethod
    def _normalize_execution_mode(mode: str) -> str:
        from servers.services.terminal_ai import normalize_execution_mode

        return normalize_execution_mode(mode)

    def _resolve_auto_execution_mode(self, plan_obj: dict[str, Any], commands_raw: Any, user_message: str) -> str:
        """
        Resolve concrete execution mode for an auto request.
        Priority:
          1) planner-provided execution_mode
          2) safety fallback from planned commands / user intent
        """
        from servers.services.terminal_ai import resolve_auto_execution_mode

        return resolve_auto_execution_mode(
            plan_obj=plan_obj,
            commands_raw=commands_raw,
            user_message=user_message,
        )

    async def _handle_ai_request(self, content: Any):
        payload = content if isinstance(content, dict) else {}
        msg = str(payload.get("message") or "").strip()
        requested_chat_mode = self._normalize_ai_chat_mode(payload.get("chat_mode") or payload.get("assistant_mode"))
        ai_settings = self._normalize_ai_settings(payload.get("ai_settings"))
        requested_mode = self._normalize_execution_mode(payload.get("execution_mode") or payload.get("mode") or "")
        if not msg:
            return

        async with self._ai_lock:
            await self._cancel_ai_locked()
            # A3: detect memory_enabled transition True → False so we can
            # wipe both in-memory and persisted chat history in one shot.
            # Capture the *previous* value before overwriting ``_ai_settings``.
            prev_memory_enabled = bool(
                (self._ai_settings or {}).get("memory_enabled", True)
            )
            new_memory_enabled = bool(ai_settings.get("memory_enabled", True))
            memory_disabled_now = prev_memory_enabled and not new_memory_enabled

            self._ai_settings = self._clone_ai_settings(ai_settings)
            self._ai_allowlist_patterns = list(self._ai_settings.get("allowlist_patterns") or [])
            ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
            ai_session.reset_for_new_request(
                user_message=msg,
                chat_mode=requested_chat_mode,
                execution_mode="step" if requested_mode == "auto" else requested_mode,
                run_id=self._new_run_id(),
                marker_token=self._new_marker_token(),
            )
            apply_legacy_ai_queue_state(self, ai_session)
            if not bool(self._ai_settings.get("memory_enabled", True)):
                self._ai_history = []

        # A3: persist the wipe to the DB when the user just flipped
        # memory_enabled from True → False. Doing this *outside* the lock
        # because ``clear_history`` is an async DB call.
        if memory_disabled_now:
            try:
                user_id = int(getattr(self, "_user_id", 0) or 0)
                server_id = int(getattr(self.server, "id", 0) or 0) if getattr(self, "server", None) else 0
                if user_id and server_id:
                    from servers.services.terminal_ai import clear_history as _clear_history

                    await _clear_history(user_id=user_id, server_id=server_id)
            except Exception as exc:  # pragma: no cover — non-fatal
                logger.debug("A3 chat-history wipe skipped: %s", exc)

        logger.debug(
            "Terminal AI request: server_id=%s run_id=%s",
            getattr(self.server, "id", None),
            self._ai_run_id,
        )
        if not self._ssh_proc:
            await self._send_ai_event(terminal_events.ai_error("SSH не подключён. Сначала нажмите Connect."))
            return
        if not self.server or not self._user_id:
            await self._send_ai_event(terminal_events.ai_error("Server not loaded"))
            return

        # 2.11: per-server read-only guard. Check flag synchronously via
        # database_sync_to_async before starting any LLM/exec work.
        if getattr(self.server, "ai_read_only", False):
            await self._send_ai_event(
                terminal_events.ai_error(
                    "Сервер переведён в режим read-only для AI. "
                    "AI-агент может только читать состояние; изменяющие команды заблокированы."
                )
            )
            await self._send_ai_event(terminal_events.ai_status("idle"))
            return

        self._ai_audit_context = {
            "user_id": self._user_id,
            "channel": "ws",
            "path": f"/ws/servers/{self.server.id}/terminal/",
            "entity_type": "server",
            "entity_id": str(self.server.id),
            "entity_name": self.server.name,
        }

        # Save user message to history
        self._add_to_history("user", msg)
        await log_user_activity_async(
            user_id=self._user_id,
            category="assistant",
            action="terminal_ai_request",
            status="success",
            description=msg[:400],
            entity_type="server",
            entity_id=self.server.id if self.server else "",
            entity_name=self.server.name if self.server else "",
            metadata={
                "message_length": len(msg),
                "chat_mode": requested_chat_mode,
                "execution_mode": requested_mode,
                "memory_enabled": bool(self._ai_settings.get("memory_enabled", True)),
                "auto_report": str(self._ai_settings.get("auto_report") or "auto"),
            },
        )
        await self._send_ai_event(
            terminal_events.ai_status(
                "thinking",
                chat_mode=requested_chat_mode,
                execution_mode=requested_mode,
            )
        )

        with audit_context(**self._ai_audit_context):
            # Nova: branch into the ReAct agent loop when requested. It
            # is a full alternative to the plan-then-execute pipeline —
            # no `_ai_plan`, no `_ai_process_queue`, no per-step planner.
            if requested_mode == "agent":
                async with self._ai_lock:
                    self._ai_run.start_task(
                        self._run_ai_agent_background(
                            user_message=msg,
                            chat_mode=requested_chat_mode,
                        )
                    )
                return

            try:
                forbidden_patterns, rules_context, required_checks, _ = await self._get_ai_rules_and_forbidden(
                    self._user_id,
                    self.server.id,
                )
                merged_forbidden = list(forbidden_patterns or [])
                for pattern in list(self._ai_settings.get("blocklist_patterns") or []):
                    if str(pattern or "").strip() and str(pattern).strip().lower() not in {
                        p.lower() for p in merged_forbidden
                    }:
                        merged_forbidden.append(str(pattern).strip())
                plan_obj = await self._ai_plan_commands(
                    user_message=msg,
                    rules_context=rules_context,
                    terminal_tail=(self._terminal_tail or "")[-2000:],
                    history=list(self._ai_history) if bool(self._ai_settings.get("memory_enabled", True)) else [],
                    unavailable_cmds=set(getattr(self, "_unavailable_cmds", set())),
                    chat_mode=requested_chat_mode,
                    execution_mode=requested_mode,
                    # A5: forward dry-run state so the planner prompt can
                    # adapt (no hard behaviour change — the short-circuit
                    # in _ai_process_queue is authoritative).
                    dry_run=bool(self._ai_settings.get("dry_run", False)),
                )
            except Exception as e:
                err_msg = str(e).strip() or "Unknown error"
                if any(
                    hint in err_msg.lower() for hint in ("timeout", "429", "rate", "resource exhausted", "overloaded")
                ):
                    err_msg = "Временная ошибка API (лимит или перегрузка). Попробуйте позже."
                await self._send_ai_event(terminal_events.ai_error(err_msg))
                await self._send_ai_event(terminal_events.ai_status("idle"))
                return

        mode = str(plan_obj.get("mode") or "execute").lower().strip()
        assistant_text = str(plan_obj.get("assistant_text") or "").strip()
        commands_raw = plan_obj.get("commands") or []
        selected_mode = requested_mode
        if requested_mode == "auto":
            selected_mode = self._resolve_auto_execution_mode(plan_obj, commands_raw, msg)
        if selected_mode not in ("step", "fast"):
            selected_mode = "step"

        # Complex goals on Fast: ask/upgrade instead of silent short linear execute.
        if requested_mode in ("fast", "auto", "step", "") and mode == "execute":
            from servers.services.terminal_ai.plan_items import apply_fast_complexity_routing

            fast_policy = str(
                (self._ai_settings or {}).get("fast_complex_policy")
                or (self._ai_settings or {}).get("complex_policy")
                or "ask"
            ).strip().lower()
            routing = apply_fast_complexity_routing(
                user_message=msg,
                requested_mode=requested_mode if requested_mode != "auto" else selected_mode,
                plan_obj=plan_obj,
                commands_raw=commands_raw,
                policy=fast_policy if fast_policy in ("ask", "upgrade", "allow") else "ask",
            )
            if routing.get("action") == "upgrade":
                upgrade_text = str(routing.get("assistant_text") or "").strip()
                if upgrade_text:
                    self._add_to_history("assistant", upgrade_text)
                    await self._send_ai_event(
                        terminal_events.ai_response(
                            mode="answer",
                            assistant_text=upgrade_text,
                            commands=[],
                            chat_mode=requested_chat_mode,
                            execution_mode="agent",
                            requested_execution_mode=requested_mode,
                        )
                    )
                async with self._ai_lock:
                    self._ai_execution_mode = "agent"
                    self._ai_run.start_task(
                        self._run_ai_agent_background(
                            user_message=msg,
                            chat_mode=requested_chat_mode,
                        )
                    )
                return
            if routing.get("action") == "ask":
                ask_text = str(routing.get("assistant_text") or assistant_text or "").strip()
                self._add_to_history("assistant", ask_text or "(уточнение)")
                await self._send_ai_event(
                    terminal_events.ai_response(
                        mode="ask",
                        assistant_text=ask_text,
                        commands=[],
                        chat_mode=requested_chat_mode,
                        execution_mode=selected_mode,
                        requested_execution_mode=requested_mode,
                    )
                )
                await self._send_ai_event(terminal_events.ai_status("idle"))
                return
            # allow: if policy forced step for complex, honor it
            routed_mode = str(routing.get("execution_mode") or selected_mode)
            if routed_mode in ("step", "fast"):
                selected_mode = routed_mode

        async with self._ai_lock:
            self._ai_execution_mode = selected_mode

        # --- answer / ask mode: just reply, no commands needed ---
        if mode in ("answer", "ask"):
            self._add_to_history("assistant", assistant_text or "(ответ)")
            await self._send_ai_event(
                terminal_events.ai_response(
                    mode=mode,
                    assistant_text=assistant_text,
                    commands=[],
                    chat_mode=requested_chat_mode,
                    execution_mode=selected_mode,
                    requested_execution_mode=requested_mode,
                )
            )
            await self._send_ai_event(terminal_events.ai_status("idle"))
            return

        # --- execute mode ---
        commands: list[dict[str, str]] = []
        if isinstance(commands_raw, list):
            for it in commands_raw:
                if not isinstance(it, dict):
                    continue
                cmd = str(it.get("cmd") or "").strip()
                if not cmd:
                    continue
                why = str(it.get("why") or "").strip()
                commands.append({"cmd": cmd, "why": why})
        max_initial_commands = 3 if selected_mode == "step" else 10
        commands = commands[:max_initial_commands]

        plan_items: list[dict[str, Any]] = []
        seen_cmds: set[str] = set()
        next_id = 1
        # Always run preflight checks first (if configured).
        for check_cmd in required_checks or []:
            check = str(check_cmd or "").strip()
            if not check:
                continue
            key = check.lower()
            if key in seen_cmds:
                continue
            seen_cmds.add(key)
            item_id = next_id
            next_id += 1
            plan_items.append(
                self._build_plan_item(
                    item_id=item_id,
                    cmd=check,
                    why="Обязательная preflight-проверка перед выполнением задачи",
                    forbidden_patterns=merged_forbidden,
                    allowlist_patterns=list(self._ai_allowlist_patterns or []),
                    confirm_dangerous_commands=bool(self._ai_settings.get("confirm_dangerous_commands", True)),
                )
            )

        for c in commands:
            cmd = c["cmd"]
            key = cmd.lower()
            if key in seen_cmds:
                continue
            seen_cmds.add(key)
            why = c.get("why") or ""
            item_id = next_id
            next_id += 1
            plan_items.append(
                self._build_plan_item(
                    item_id=item_id,
                    cmd=cmd,
                    why=why,
                    forbidden_patterns=merged_forbidden,
                    allowlist_patterns=list(self._ai_allowlist_patterns or []),
                    confirm_dangerous_commands=bool(self._ai_settings.get("confirm_dangerous_commands", True)),
                    # F2-8: forward LLM-provided exec_mode hint when present.
                    exec_mode=c.get("exec_mode"),
                )
            )

        # Hard limit to keep runs predictable in terminal.
        plan_items = plan_items[:12]

        if requested_chat_mode == "ask" and plan_items:
            ask_prefix = "Режим Ask активен: команды ниже предложены для ручного запуска и не выполнятся без вашего подтверждения."
            assistant_text = f"{ask_prefix}\n\n{assistant_text}" if assistant_text else ask_prefix

        async with self._ai_lock:
            ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
            ai_session.load_plan(plan_items, next_id=next_id, forbidden_patterns=merged_forbidden)
            apply_legacy_ai_queue_state(self, ai_session)

        await self._send_ai_event(
            terminal_events.ai_response(
                mode="execute",
                assistant_text=assistant_text,
                commands=plan_items,
                chat_mode=requested_chat_mode,
                execution_mode=selected_mode,
                requested_execution_mode=requested_mode,
            )
        )

        if not plan_items:
            self._add_to_history("assistant", assistant_text or "Команды не нужны")
            await self._send_ai_event(terminal_events.ai_status("idle"))
            return

        await self._send_ai_event(terminal_events.ai_status("running"))
        with audit_context(**self._ai_audit_context):
            async with self._ai_lock:
                self._ai_run.start_task(self._ai_process_queue())

    async def _handle_ai_confirm(self, content: dict[str, Any]):
        try:
            cmd_id = int(content.get("id"))
        except Exception:
            await self._send_ai_event(terminal_events.ai_error("Некорректный id для подтверждения"))
            return

        should_start = False
        async with self._ai_lock:
            ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
            transition = ai_session.confirm_current(cmd_id)
            apply_legacy_ai_queue_state(self, ai_session)
            if transition.error:
                await self._send_ai_event(terminal_events.ai_error(transition.error))
                return
            if not transition.changed:
                return
            if not self._ai_run.has_active_task():
                should_start = True

        await self._send_ai_event(terminal_events.ai_command_status(item_id=cmd_id, status=transition.status))
        if should_start:
            await self._send_ai_event(terminal_events.ai_status("running"))
            with audit_context(**getattr(self, "_ai_audit_context", {})):
                async with self._ai_lock:
                    self._ai_run.start_task(self._ai_process_queue())

    async def _handle_ai_cancel(self, content: dict[str, Any]):
        try:
            cmd_id = int(content.get("id"))
        except Exception:
            await self._send_ai_event(terminal_events.ai_error("Некорректный id для отмены"))
            return

        should_start = False
        async with self._ai_lock:
            ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
            transition = ai_session.cancel_current(cmd_id)
            apply_legacy_ai_queue_state(self, ai_session)
            if transition.error:
                await self._send_ai_event(terminal_events.ai_error(transition.error))
                return
            if not transition.changed:
                return
            if not self._ai_run.has_active_task():
                should_start = True

        await self._send_ai_event(terminal_events.ai_command_status(item_id=cmd_id, status=transition.status))
        if should_start:
            await self._send_ai_event(terminal_events.ai_status("running"))
            with audit_context(**getattr(self, "_ai_audit_context", {})):
                async with self._ai_lock:
                    self._ai_run.start_task(self._ai_process_queue())

    async def _handle_ai_clear_memory(self):
        async with self._ai_lock:
            self._ai_history = []
            self._ai_last_done_items = []
            self._ai_last_report = ""
        # F2-9: also wipe the persistent DB copy so a page reload does not
        # restore the history the user just cleared.
        try:
            user_id = int(getattr(self, "_user_id", 0) or 0)
            server_id = int(getattr(self.server, "id", 0) or 0) if getattr(self, "server", None) else 0
            if user_id and server_id:
                from servers.services.terminal_ai import clear_history as _clear_history

                await _clear_history(user_id=user_id, server_id=server_id)
        except Exception as exc:  # pragma: no cover — non-fatal
            logger.debug("terminal-ai chat history clear skipped: %s", exc)
        await self._send_ai_event(
            terminal_events.ai_response(
                assistant_text="🧹 Память текущего чата очищена.",
                execution_mode=str(getattr(self, "_ai_execution_mode", "step")),
            )
        )

