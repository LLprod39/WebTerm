"""Terminal AI queue execution behavior."""
from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from loguru import logger

from servers.consumers.ssh_terminal_constants import (
    _TERMINAL_AI_LLM_SEMAPHORE,
)
from servers.memory_heuristics import is_trivial_memory_command
from servers.services import terminal_events, terminal_input
from servers.services.terminal_ai.active_command import (
    register_active_command,
)
from servers.services.terminal_ai.command_outcome import unavailable_command_name
from servers.services.terminal_ai.legacy_state import (
    apply_legacy_ai_queue_state,
    sync_legacy_ai_queue_state,
)
from servers.services.terminal_ai.pty_command import wait_for_pty_command_completion
from servers.services.terminal_ai.queue_completion import handle_queue_completion
from servers.services.terminal_ai.recovery import (
    handle_fast_error_recovery,
    handle_step_post_command,
)
from servers.services.terminal_direct_execution import execute_direct_terminal_command
from servers.services.terminal_parallel_batch import execute_terminal_parallel_batch

_TermSize = terminal_input.TerminalSize


class SSHTerminalAiExecutionMixin:
    async def _ai_process_queue(self):
        """
        Execute queued AI commands sequentially.
        Pauses when a command requires confirmation.
        """
        send_idle = True
        execution_mode = self._normalize_execution_mode(getattr(self, "_ai_execution_mode", "step"))
        step_mode = execution_mode == "step"
        direct_exec_enabled = self._legacy_direct_exec_enabled()
        try:
            while True:
                if not self._ssh_proc:
                    break
                if not self.server or not self._user_id:
                    break

                # 4.2: parallel batch detection ──────────────────────────
                async with self._ai_lock:
                    ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
                    parallel_batch = ai_session.prepare_parallel_batch(
                        direct_exec_enabled=direct_exec_enabled,
                        step_mode=step_mode,
                        has_ssh_connection=bool(self._ssh_conn),
                    )

                if parallel_batch.is_ready:
                    await self._execute_parallel_batch(parallel_batch.items, parallel_batch.indices)
                    async with self._ai_lock:
                        ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
                        ai_session.advance_after_parallel_batch(parallel_batch.indices)
                        apply_legacy_ai_queue_state(self, ai_session)
                    continue
                # ── end parallel batch ─────────────────────────────────────

                async with self._ai_lock:
                    ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
                    queue_step = ai_session.prepare_next_step()
                    apply_legacy_ai_queue_state(self, ai_session)

                if queue_step.action == "empty":
                    break
                if queue_step.action == "advance":
                    continue
                if queue_step.action == "blocked_skipped":
                    await self._send_ai_event(
                        terminal_events.ai_command_status(
                            item_id=queue_step.command_id or 0,
                            status="skipped",
                            reason=queue_step.reason or "forbidden",
                        )
                    )
                    continue
                if queue_step.action == "waiting_confirm":
                    # Pause until user confirms/cancels current command
                    await self._send_ai_event(
                        terminal_events.ai_status(
                            "waiting_confirm",
                            id=queue_step.command_id or 0,
                            reason=queue_step.reason or "dangerous",
                        )
                    )
                    send_idle = False
                    return

                item = queue_step.item or {}
                item_id = int(queue_step.command_id or 0)
                cmd = queue_step.command

                await self._send_ai_event(
                    terminal_events.ai_command_status(item_id=item_id, status="running")
                )

                # F2-8 v2: route safe stateless commands through a non-PTY
                # channel so the interactive shell is not polluted by
                # diagnostic reads (df -h, ps aux, systemctl status…).
                item_exec_mode = str(item.get("exec_mode") or "pty").strip().lower()
                if not direct_exec_enabled and item_exec_mode == "direct":
                    item_exec_mode = "pty"
                # A5: dry-run short-circuit. We do NOT touch the remote
                # host at all — neither via PTY nor via exec_direct. The
                # fake output makes downstream history/report/memory work
                # exactly as on a real run so the user can preview the
                # plan end-to-end.
                dry_run_active = bool((self._ai_settings or {}).get("dry_run", False))

                # 2.4: capture pre-execution snapshot for file-modifying cmds.
                if not dry_run_active and self._ssh_conn:
                    await self._maybe_snapshot_file(cmd, item_id)

                try:
                    if dry_run_active:
                        output_snippet = f"[DRY-RUN] Would execute: {cmd}"
                        exit_code = 0
                        # Emit a direct_output-style event so the UI
                        # renders the preview inline without marker tokens.
                        await self._send_ai_event(
                            terminal_events.ai_direct_output(
                                item_id=item_id,
                                command=cmd,
                                output=output_snippet,
                                exit_code=0,
                                dry_run=True,
                            )
                        )
                    elif item_exec_mode == "direct":
                        exit_code, output_snippet = await self._ai_execute_command_direct(cmd, item_id)
                    else:
                        exit_code, output_snippet = await self._ai_execute_command(cmd, item_id)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning("AI command execution failed (id=%s): %s", item_id, e)
                    # Do not crash the whole queue on one bad command; let recovery logic decide.
                    exit_code = 1
                    output_snippet = f"WEUAI_EXECUTION_ERROR: {type(e).__name__}: {e}"
                await self._log_ai_command_history(
                    user_id=self._user_id,
                    server_id=self.server.id,
                    command=cmd,
                    output_snippet=output_snippet,
                    exit_code=exit_code,
                )

                if unavailable_cmd := unavailable_command_name(cmd, exit_code):
                    self._unavailable_cmds.add(unavailable_cmd)

                # ── Adaptive error recovery ─────────────────────────────────
                # For non-trivial failures (not success, not interrupted, not skipped):
                # call the LLM to decide: retry / skip / ask user / abort.
                #
                # F1-9: in step-mode we skip this dedicated recovery call and let
                # the unified post-step controller (_ai_step_decide_next) handle
                # both success and error cases in a single LLM round-trip
                # (-30–50% LLM cost in step-mode on errors). In fast-mode the
                # block below is the only place where errors are handled.
                recovery_action = await handle_fast_error_recovery(
                    self,
                    item=item,
                    item_id=item_id,
                    command=cmd,
                    exit_code=exit_code,
                    output=output_snippet,
                    step_mode=step_mode,
                )

                if recovery_action == "abort":
                    break
                # ── End adaptive error recovery ─────────────────────────────

                async with self._ai_lock:
                    ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
                    ai_session.mark_current_done(item_id, exit_code, output_snippet or "")
                    apply_legacy_ai_queue_state(self, ai_session)

                is_stream = bool(item.get("streaming", False))
                await self._send_ai_event(
                    terminal_events.ai_command_status(
                        item_id=item_id,
                        status="done",
                        exit_code=exit_code,
                        streaming=is_stream,
                    )
                )

                # Step-by-step mode: re-evaluate after each command, not only on errors.
                if step_mode:
                    should_stop = await handle_step_post_command(
                        self,
                        item_id=item_id,
                        command=cmd,
                        exit_code=exit_code,
                        output=output_snippet or "",
                    )
                    if should_stop:
                        break

            # После выполнения всех команд — сформировать отчёт по выводу (анализ логов, проблем и т.д.)
            if send_idle:
                await handle_queue_completion(self)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("AI processing failed")
            err_msg = str(e).strip() or "Unknown error"
            if any(
                hint in err_msg.lower() for hint in ("timeout", "429", "rate", "resource exhausted", "overloaded")
            ):
                err_msg = "Временная ошибка API (лимит или перегрузка). Попробуйте позже."
            await self._send_ai_event(terminal_events.ai_error(err_msg))
        finally:
            if send_idle:
                await self._send_ai_event(terminal_events.ai_status("idle"))

    async def _ai_execute_command(self, cmd: str, cmd_id: int) -> tuple[int, str]:
        """
        Type and execute a command in the interactive PTY and wait for an internal marker.
        For streaming/interactive commands: auto-interrupts with Ctrl+C after 8 s.
        Returns (exit_code, output_snippet).
        """
        if not self._ssh_proc:
            raise RuntimeError("SSH process not connected")

        clean_cmd = self._normalize_command_text(cmd)
        if not clean_cmd:
            return -1, ""

        is_streaming = self._is_streaming_command(clean_cmd)
        is_install = self._is_install_command(clean_cmd)

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[int] = loop.create_future()
        async with self._ai_lock:
            register_active_command(self, cmd_id, fut)

        with self._suppress_terminal_input_capture():
            await self._ai_type_text(clean_cmd)
            self._ssh_proc.stdin.write("\n")

            # Marker line to capture exit status (filtered from UI output)
            marker_prefix = self._marker_prefix()
            marker_var = f"{marker_prefix}{cmd_id}"
            marker_cmd = f'{marker_var}=$?; echo "{marker_prefix}{cmd_id}:${{{marker_var}}}__"'
            self._ssh_proc.stdin.write(marker_cmd + "\n")

        return await wait_for_pty_command_completion(
            self,
            cmd_id=cmd_id,
            command=clean_cmd,
            future=fut,
            is_streaming=is_streaming,
            is_install=is_install,
            lock=self._ai_lock,
            send_ai_event=self._send_ai_event,
            interrupt_streaming_after=self._interrupt_streaming_after,
            write_interrupt=self._write_interrupt_to_pty,
            detect_install_error=self._detect_install_error,
        )

    # F2-8 v2: non-PTY execution path for safe stateless reads.
    #
    # How it differs from :meth:`_ai_execute_command`:
    #   * uses a fresh channel via ``SSHClientConnection.run(...)`` — nothing
    #     is typed into the interactive PTY, so the user's shell state (cwd,
    #     history, env) is untouched and there are no marker tokens mixed
    #     into the terminal output;
    #   * has its own shorter default timeout (30s) because ``direct`` is
    #     only picked for non-streaming read-only commands;
    #   * emits an ``ai_direct_output`` WS event so the UI can render the
    #     captured stdout inline in the AI panel rather than the terminal.
    DIRECT_EXEC_TIMEOUT_SEC = 30
    DIRECT_EXEC_MAX_OUTPUT = 6000

    async def _ai_execute_command_direct(self, cmd: str, cmd_id: int) -> tuple[int, str]:
        """Execute ``cmd`` via a non-PTY asyncssh channel.

        Returns ``(exit_code, captured_output)``; the caller treats this
        tuple the same way as :meth:`_ai_execute_command` so recovery,
        logging and memory-ingestion flows all keep working.
        """
        return await execute_direct_terminal_command(
            ssh_conn=self._ssh_conn,
            command=cmd,
            item_id=cmd_id,
            send_event=self._send_ai_event,
            normalize_command=self._normalize_command_text,
            timeout_seconds=self.DIRECT_EXEC_TIMEOUT_SEC,
            max_output_chars=self.DIRECT_EXEC_MAX_OUTPUT,
        )

    # ── 2.4: pre-execution file snapshots ──────────────────────────────────

    SNAPSHOT_READ_TIMEOUT_SEC = 10

    async def _maybe_snapshot_file(self, cmd: str, cmd_id: int) -> None:
        """If *cmd* will modify a file, read it via SSH and save a snapshot.

        Best-effort: any failure is logged but never blocks execution.
        """
        from servers.services.terminal_snapshotting import capture_pre_execution_snapshot

        if not self._ssh_conn or not self.server:
            return
        await capture_pre_execution_snapshot(
            command=cmd,
            cmd_id=cmd_id,
            ssh_conn=self._ssh_conn,
            server_id=int(self.server.id),
            user_id=self._user_id,
            timeout_seconds=self.SNAPSHOT_READ_TIMEOUT_SEC,
        )

    # ── 4.2: parallel batch execution ──────────────────────────────────────

    async def _execute_parallel_batch(
        self,
        items: list[dict[str, Any]],
        plan_indices: list[int],
    ) -> None:
        """Run a batch of ``exec_mode=direct`` commands concurrently.

        Each command gets its own non-PTY SSH channel via
        :meth:`_ai_execute_command_direct`.  Snapshots, history logging
        and status events are handled per-command.  No error recovery is
        attempted within the batch — failed items are simply marked done
        with their exit code so downstream reporting can handle them.
        """
        async def mark_plan_index_done(plan_idx: int, exit_code: int, output_snippet: str) -> None:
            async with self._ai_lock:
                ai_session = sync_legacy_ai_queue_state(self, self._TerminalAiSessionCls)
                ai_session.mark_plan_index_done(plan_idx, exit_code, output_snippet)
                apply_legacy_ai_queue_state(self, ai_session)

        await execute_terminal_parallel_batch(
            items=items,
            plan_indices=plan_indices,
            dry_run=bool((self._ai_settings or {}).get("dry_run", False)),
            has_ssh_connection=bool(self._ssh_conn),
            user_id=self._user_id,
            server_id=self.server.id if self.server else 0,
            send_event=self._send_ai_event,
            snapshot_command=self._maybe_snapshot_file,
            execute_direct=self._ai_execute_command_direct,
            log_command_history=self._log_ai_command_history,
            mark_plan_index_done=mark_plan_index_done,
            record_unavailable=self._unavailable_cmds.add,
        )

    async def _interrupt_streaming_after(self, delay: float) -> None:
        """Send Ctrl+C after `delay` seconds to interrupt a streaming command."""
        await asyncio.sleep(delay)
        with contextlib.suppress(Exception):
            self._write_interrupt_to_pty()

    def _write_interrupt_to_pty(self) -> None:
        if self._ssh_proc:
            self._ssh_proc.stdin.write("\x03")

    @staticmethod
    def _is_streaming_command(cmd: str) -> bool:
        return terminal_input.is_streaming_command(cmd)

    @staticmethod
    def _is_install_command(cmd: str) -> bool:
        return terminal_input.is_install_command(cmd)

    @staticmethod
    def _is_trivial_memory_command(cmd: str) -> bool:
        return is_trivial_memory_command(cmd)

    @staticmethod
    def _detect_install_error(output: str) -> bool:
        return terminal_input.detect_install_error(output)

    async def _ai_handle_error(
        self,
        cmd: str,
        exit_code: int,
        output: str,
        remaining_cmds: list[str],
        user_reply: str | None = None,
    ) -> dict[str, Any]:
        """
        Ask LLM to decide what to do after a command failed.
        Returns {"action": "retry"|"skip"|"ask"|"abort", "cmd"?, "why"?, "question"?}

        Untrusted output/user_reply is sanitised by
        :func:`servers.services.terminal_ai.prompts.build_recovery_prompt`
        before embedding into the prompt (F1-1 / F1-2).
        The response is validated against
        :class:`servers.services.terminal_ai.schemas.TerminalPlanResponse`
        (F1-6).
        """
        from servers.services.terminal_ai import decide_recovery

        return await decide_recovery(
            cmd=cmd,
            exit_code=exit_code,
            output=output or "",
            remaining_cmds=remaining_cmds or [],
            user_reply=user_reply,
            semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
        )

    async def _ai_step_decide_next(
        self,
        user_goal: str,
        last_cmd: str,
        exit_code: int,
        output: str,
        remaining_cmds: list[str],
        user_reply: str | None = None,
    ) -> dict[str, Any]:
        """
        Step-by-step controller:
        after each command decides whether to continue current plan, add a new command,
        ask user, finish, or abort.

        Untrusted goal/output/user_reply are sanitised by
        :func:`servers.services.terminal_ai.prompts.build_step_decision_prompt`
        before embedding into the prompt (F1-1 / F1-2).
        """
        from servers.services.terminal_ai import decide_step_next

        return await decide_step_next(
            user_goal=user_goal,
            last_cmd=last_cmd,
            exit_code=exit_code,
            output=output or "",
            remaining_cmds=remaining_cmds or [],
            user_reply=user_reply,
            semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
        )

    async def _ai_type_text(self, text: str):
        if not self._ssh_proc or not text:
            return
        step = 1 if len(text) <= 80 else 4
        delay = 0.01 if step == 1 else 0.006
        for i in range(0, len(text), step):
            self._ssh_proc.stdin.write(text[i : i + step])
            await asyncio.sleep(delay)

    # ── Nova agent entry point ─────────────────────────────────────────────

