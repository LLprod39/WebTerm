"""Terminal AI request and control handlers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
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


@dataclass(frozen=True)
class _AiRequestInput:
    message: str
    chat_mode: str
    requested_mode: str
    settings: dict[str, Any]


class TerminalAiControlOperations:
    async def _handle_ai_stop(self):
        active_cmd_id = await self._interrupt_active_command()

        async with self._ai_state.lock:
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
        async with self._ai_state.lock:
            await self._cancel_ai_locked()

    async def _cancel_ai_locked(self):
        self._ai_state.run.cancel_task(current=asyncio.current_task())

        cancel_exit_futures(self._ai_state.active_command)

        self._ai_state.run.cancel_reply_futures()

        ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
        ai_session.clear()
        apply_legacy_ai_queue_state(self, ai_session)
        clear_active_command(self._ai_state.active_command)

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
        request = self._parse_ai_request(content)
        if request is None:
            return
        memory_disabled_now = await self._initialize_ai_request(request)
        if memory_disabled_now:
            await self._wipe_persisted_ai_history()

        logger.debug(
            "Terminal AI request: server_id=%s run_id=%s",
            getattr(self.server, "id", None),
            self._ai_state.session.run_id,
        )
        if not await self._ensure_ai_request_ready():
            return
        await self._record_ai_request(request)
        if await self._start_agent_request(request):
            return

        planned = await self._plan_ai_request(request)
        if planned is None:
            return
        plan_obj, merged_forbidden, required_checks = planned
        mode = str(plan_obj.get("mode") or "execute").lower().strip()
        assistant_text = str(plan_obj.get("assistant_text") or "").strip()
        commands_raw = plan_obj.get("commands") or []
        selected_mode = self._selected_execution_mode(request, plan_obj, commands_raw)
        handled, selected_mode = await self._route_complex_plan(
            request,
            plan_obj,
            commands_raw,
            selected_mode,
            assistant_text,
            mode,
        )
        if handled:
            return

        async with self._ai_state.lock:
            self._ai_state.session.execution_mode = selected_mode
        if mode in ("answer", "ask"):
            await self._send_answer_plan(request, mode, assistant_text, selected_mode)
            return

        plan_items, next_id = self._build_request_plan_items(
            commands_raw,
            required_checks,
            merged_forbidden,
            selected_mode,
        )
        await self._activate_request_plan(
            request,
            assistant_text,
            selected_mode,
            merged_forbidden,
            plan_items,
            next_id,
        )

    def _parse_ai_request(self, content: Any) -> _AiRequestInput | None:
        payload = content if isinstance(content, dict) else {}
        msg = str(payload.get("message") or "").strip()
        if not msg:
            return None
        return _AiRequestInput(
            message=msg,
            chat_mode=self._normalize_ai_chat_mode(payload.get("chat_mode") or payload.get("assistant_mode")),
            settings=self._normalize_ai_settings(payload.get("ai_settings")),
            requested_mode=self._normalize_execution_mode(payload.get("execution_mode") or payload.get("mode") or ""),
        )

    async def _initialize_ai_request(self, request: _AiRequestInput) -> bool:
        async with self._ai_state.lock:
            await self._cancel_ai_locked()
            prev_memory_enabled = bool((self._ai_state.settings or {}).get("memory_enabled", True))
            new_memory_enabled = bool(request.settings.get("memory_enabled", True))
            memory_disabled_now = prev_memory_enabled and not new_memory_enabled
            self._ai_state.settings = self._clone_ai_settings(request.settings)
            self._ai_state.allowlist_patterns = list(self._ai_state.settings.get("allowlist_patterns") or [])
            ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
            ai_session.reset_for_new_request(
                user_message=request.message,
                chat_mode=request.chat_mode,
                execution_mode="step" if request.requested_mode == "auto" else request.requested_mode,
                run_id=self._new_run_id(),
                marker_token=self._new_marker_token(),
            )
            apply_legacy_ai_queue_state(self, ai_session)
            if not bool(self._ai_state.settings.get("memory_enabled", True)):
                self._ai_state.history = []
        return memory_disabled_now

    async def _wipe_persisted_ai_history(self) -> None:
        try:
            user_id = int(getattr(self, "_user_id", 0) or 0)
            server_id = int(getattr(self.server, "id", 0) or 0) if getattr(self, "server", None) else 0
            if user_id and server_id:
                from servers.services.terminal_ai import clear_history as _clear_history

                await _clear_history(user_id=user_id, server_id=server_id)
        except Exception as exc:  # pragma: no cover — non-fatal
            logger.debug("A3 chat-history wipe skipped: %s", exc)

    async def _ensure_ai_request_ready(self) -> bool:
        if not self._transport_state.ssh_proc:
            await self._send_ai_event(terminal_events.ai_error("SSH не подключён. Сначала нажмите Connect."))
            return False
        if not self.server or not self._user_id:
            await self._send_ai_event(terminal_events.ai_error("Server not loaded"))
            return False
        return True

    async def _record_ai_request(self, request: _AiRequestInput) -> None:
        self._ai_state.audit_context = {
            "user_id": self._user_id,
            "channel": "ws",
            "path": f"/ws/servers/{self.server.id}/terminal/",
            "entity_type": "server",
            "entity_id": str(self.server.id),
            "entity_name": self.server.name,
        }
        self._add_to_history("user", request.message)
        await log_user_activity_async(
            user_id=self._user_id,
            category="assistant",
            action="terminal_ai_request",
            status="success",
            description="Terminal AI request accepted",
            entity_type="server",
            entity_id=self.server.id if self.server else "",
            entity_name=self.server.name if self.server else "",
            metadata={
                "message_length": len(request.message),
                "chat_mode": request.chat_mode,
                "execution_mode": request.requested_mode,
                "memory_enabled": bool(self._ai_state.settings.get("memory_enabled", True)),
                "auto_report": str(self._ai_state.settings.get("auto_report") or "auto"),
            },
        )
        await self._send_ai_event(
            terminal_events.ai_status(
                "thinking",
                chat_mode=request.chat_mode,
                execution_mode=request.requested_mode,
            )
        )

    async def _start_agent_request(self, request: _AiRequestInput) -> bool:
        if request.requested_mode != "agent":
            return False
        with audit_context(**self._ai_state.audit_context):
            async with self._ai_state.lock:
                self._ai_state.run.start_task(
                    self._run_ai_agent_background(
                        user_message=request.message,
                        chat_mode=request.chat_mode,
                    )
                )
        return True

    async def _plan_ai_request(
        self,
        request: _AiRequestInput,
    ) -> tuple[dict[str, Any], list[str], list[str]] | None:
        with audit_context(**self._ai_state.audit_context):
            try:
                forbidden_patterns, rules_context, required_checks, _ = await self._get_ai_rules_and_forbidden(
                    self._user_id,
                    self.server.id,
                )
                plan_obj = await self._ai_plan_commands(
                    user_message=request.message,
                    rules_context=rules_context,
                    terminal_tail=(self._transport_state.terminal_tail or "")[-2000:],
                    history=list(self._ai_state.history)
                    if bool(self._ai_state.settings.get("memory_enabled", True))
                    else [],
                    unavailable_cmds=set(getattr(self, "_unavailable_cmds", set())),
                    chat_mode=request.chat_mode,
                    execution_mode=request.requested_mode,
                    dry_run=bool(self._ai_state.settings.get("dry_run", False)),
                )
            except Exception as e:
                err_msg = str(e).strip() or "Unknown error"
                if any(
                    hint in err_msg.lower() for hint in ("timeout", "429", "rate", "resource exhausted", "overloaded")
                ):
                    err_msg = "Временная ошибка API (лимит или перегрузка). Попробуйте позже."
                await self._send_ai_event(terminal_events.ai_error(err_msg))
                await self._send_ai_event(terminal_events.ai_status("idle"))
                return None
        return plan_obj, self._merged_forbidden_patterns(forbidden_patterns), list(required_checks or [])

    def _merged_forbidden_patterns(self, forbidden_patterns: list[str] | None) -> list[str]:
        merged = list(forbidden_patterns or [])
        known = {pattern.lower() for pattern in merged}
        for pattern in self._ai_state.settings.get("blocklist_patterns") or []:
            normalized = str(pattern or "").strip()
            if normalized and normalized.lower() not in known:
                merged.append(normalized)
                known.add(normalized.lower())
        return merged

    def _selected_execution_mode(
        self,
        request: _AiRequestInput,
        plan_obj: dict[str, Any],
        commands_raw: Any,
    ) -> str:
        selected_mode = request.requested_mode
        if request.requested_mode == "auto":
            selected_mode = self._resolve_auto_execution_mode(plan_obj, commands_raw, request.message)
        if selected_mode not in ("step", "fast"):
            selected_mode = "step"
        return selected_mode

    async def _route_complex_plan(
        self,
        request: _AiRequestInput,
        plan_obj: dict[str, Any],
        commands_raw: Any,
        selected_mode: str,
        assistant_text: str,
        mode: str,
    ) -> tuple[bool, str]:
        if request.requested_mode not in ("fast", "auto", "step", "") or mode != "execute":
            return False, selected_mode
        from servers.services.terminal_ai.plan_items import apply_fast_complexity_routing

        fast_policy = (
            str(
                self._ai_state.settings.get("fast_complex_policy")
                or self._ai_state.settings.get("complex_policy")
                or "ask"
            )
            .strip()
            .lower()
        )
        routing = apply_fast_complexity_routing(
            user_message=request.message,
            requested_mode=request.requested_mode if request.requested_mode != "auto" else selected_mode,
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
                        chat_mode=request.chat_mode,
                        execution_mode="agent",
                        requested_execution_mode=request.requested_mode,
                    )
                )
            async with self._ai_state.lock:
                self._ai_state.session.execution_mode = "agent"
                self._ai_state.run.start_task(
                    self._run_ai_agent_background(
                        user_message=request.message,
                        chat_mode=request.chat_mode,
                    )
                )
            return True, "agent"
        if routing.get("action") == "ask":
            ask_text = str(routing.get("assistant_text") or assistant_text or "").strip()
            self._add_to_history("assistant", ask_text or "(уточнение)")
            await self._send_ai_event(
                terminal_events.ai_response(
                    mode="ask",
                    assistant_text=ask_text,
                    commands=[],
                    chat_mode=request.chat_mode,
                    execution_mode=selected_mode,
                    requested_execution_mode=request.requested_mode,
                )
            )
            await self._send_ai_event(terminal_events.ai_status("idle"))
            return True, selected_mode
        routed_mode = str(routing.get("execution_mode") or selected_mode)
        return False, routed_mode if routed_mode in ("step", "fast") else selected_mode

    async def _send_answer_plan(
        self,
        request: _AiRequestInput,
        mode: str,
        assistant_text: str,
        selected_mode: str,
    ) -> None:
        self._add_to_history("assistant", assistant_text or "(ответ)")
        await self._send_ai_event(
            terminal_events.ai_response(
                mode=mode,
                assistant_text=assistant_text,
                commands=[],
                chat_mode=request.chat_mode,
                execution_mode=selected_mode,
                requested_execution_mode=request.requested_mode,
            )
        )
        await self._send_ai_event(terminal_events.ai_status("idle"))

    def _build_request_plan_items(
        self,
        commands_raw: Any,
        required_checks: list[str],
        merged_forbidden: list[str],
        selected_mode: str,
    ) -> tuple[list[dict[str, Any]], int]:
        commands: list[dict[str, Any]] = []
        if isinstance(commands_raw, list):
            for command in commands_raw:
                if not isinstance(command, dict):
                    continue
                cmd = str(command.get("cmd") or "").strip()
                if not cmd:
                    continue
                commands.append(
                    {
                        "cmd": cmd,
                        "why": str(command.get("why") or "").strip(),
                        "exec_mode": command.get("exec_mode"),
                    }
                )
        max_initial_commands = 3 if selected_mode == "step" else 10
        commands = commands[:max_initial_commands]
        candidates = [
            (str(check or "").strip(), "Обязательная preflight-проверка перед выполнением задачи", None)
            for check in required_checks
        ]
        candidates.extend((command["cmd"], command["why"], command.get("exec_mode")) for command in commands)
        plan_items: list[dict[str, Any]] = []
        seen_cmds: set[str] = set()
        next_id = 1
        for cmd, why, exec_mode in candidates:
            key = cmd.lower()
            if not cmd or key in seen_cmds:
                continue
            seen_cmds.add(key)
            plan_items.append(
                self._build_plan_item(
                    item_id=next_id,
                    cmd=cmd,
                    why=why,
                    forbidden_patterns=merged_forbidden,
                    allowlist_patterns=list(self._ai_state.allowlist_patterns or []),
                    confirm_dangerous_commands=bool(self._ai_state.settings.get("confirm_dangerous_commands", True)),
                    exec_mode=exec_mode,
                )
            )
            next_id += 1
        return plan_items[:12], next_id

    async def _activate_request_plan(
        self,
        request: _AiRequestInput,
        assistant_text: str,
        selected_mode: str,
        merged_forbidden: list[str],
        plan_items: list[dict[str, Any]],
        next_id: int,
    ) -> None:
        if request.chat_mode == "ask" and plan_items:
            ask_prefix = "Режим Ask активен: команды ниже предложены для ручного запуска и не выполнятся без вашего подтверждения."
            assistant_text = f"{ask_prefix}\n\n{assistant_text}" if assistant_text else ask_prefix

        async with self._ai_state.lock:
            ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
            ai_session.load_plan(plan_items, next_id=next_id, forbidden_patterns=merged_forbidden)
            apply_legacy_ai_queue_state(self, ai_session)

        await self._send_ai_event(
            terminal_events.ai_response(
                mode="execute",
                assistant_text=assistant_text,
                commands=plan_items,
                chat_mode=request.chat_mode,
                execution_mode=selected_mode,
                requested_execution_mode=request.requested_mode,
            )
        )

        if not plan_items:
            self._add_to_history("assistant", assistant_text or "Команды не нужны")
            await self._send_ai_event(terminal_events.ai_status("idle"))
            return

        await self._send_ai_event(terminal_events.ai_status("running"))
        with audit_context(**self._ai_state.audit_context):
            async with self._ai_state.lock:
                self._ai_state.run.start_task(self._ai_process_queue())

    async def _handle_ai_confirm(self, content: dict[str, Any]):
        try:
            cmd_id = int(content.get("id"))
        except Exception:
            await self._send_ai_event(terminal_events.ai_error("Некорректный id для подтверждения"))
            return

        should_start = False
        async with self._ai_state.lock:
            ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
            transition = ai_session.confirm_current(cmd_id)
            apply_legacy_ai_queue_state(self, ai_session)
            if transition.error:
                await self._send_ai_event(terminal_events.ai_error(transition.error))
                return
            if not transition.changed:
                return
            if not self._ai_state.run.has_active_task():
                should_start = True

        await self._send_ai_event(terminal_events.ai_command_status(item_id=cmd_id, status=transition.status))
        if should_start:
            await self._send_ai_event(terminal_events.ai_status("running"))
            with audit_context(**self._ai_state.audit_context):
                async with self._ai_state.lock:
                    self._ai_state.run.start_task(self._ai_process_queue())

    async def _handle_ai_cancel(self, content: dict[str, Any]):
        try:
            cmd_id = int(content.get("id"))
        except Exception:
            await self._send_ai_event(terminal_events.ai_error("Некорректный id для отмены"))
            return

        should_start = False
        async with self._ai_state.lock:
            ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
            transition = ai_session.cancel_current(cmd_id)
            apply_legacy_ai_queue_state(self, ai_session)
            if transition.error:
                await self._send_ai_event(terminal_events.ai_error(transition.error))
                return
            if not transition.changed:
                return
            if not self._ai_state.run.has_active_task():
                should_start = True

        await self._send_ai_event(terminal_events.ai_command_status(item_id=cmd_id, status=transition.status))
        if should_start:
            await self._send_ai_event(terminal_events.ai_status("running"))
            with audit_context(**self._ai_state.audit_context):
                async with self._ai_state.lock:
                    self._ai_state.run.start_task(self._ai_process_queue())

    async def _handle_ai_clear_memory(self):
        async with self._ai_state.lock:
            self._ai_state.history = []
            self._ai_state.session.last_done_items = []
            self._ai_state.session.last_report = ""
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
                execution_mode=self._ai_state.session.execution_mode,
            )
        )
