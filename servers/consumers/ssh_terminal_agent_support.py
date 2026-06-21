"""Terminal AI agent context, reports, memory, and policy helpers."""
from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from core_ui.audit import audit_context
from servers.consumers.ssh_terminal_constants import (
    _TERMINAL_AI_LLM_SEMAPHORE,
)
from servers.services import terminal_input
from servers.services.terminal_agent_context import open_agent_target_connection
from servers.services.terminal_ai.memory import sanitize_memory_line
from servers.services.terminal_ai.planning import extract_json_object
from servers.services.terminal_ai.policy import compute_confirm_reason, match_patterns
from servers.services.terminal_ai.reporter import (
    build_fallback_report,
    compute_report_status,
)

_TermSize = terminal_input.TerminalSize


class SSHTerminalAgentSupportMixin:
    async def _ai_build_agent_extras(self) -> dict[str, Any]:
        """Return the opt-in extra targets the user authorised for this session.

        Reads ``ai_settings.extra_target_server_ids`` (list of server
        ids the user has access to). Each target opens its own SSH
        connection. Failed connections are skipped with a warning.
        """
        from servers.services.terminal_agent_context import build_agent_extra_targets

        return await build_agent_extra_targets(
            ai_settings=self._ai_settings,
            user_id=self._user_id,
            primary_server_id=int(self.server.id) if self.server else None,
        )

    async def _ai_build_agent_memory_context(self, server_ids: list[int]) -> str:
        """Render a layered-memory prompt block for the agent.

        Loads :class:`ServerMemoryCard` for every authorised target in
        one batched query and renders them via
        :func:`render_server_cards_prompt`. Everything here is
        best-effort — an empty string is returned on any error so the
        agent simply starts without prior knowledge instead of crashing.
        """
        from servers.services.terminal_agent_context import build_agent_memory_context

        return await build_agent_memory_context(server_ids)

    async def _open_agent_target_conn(self, server_id: int) -> Any | None:
        """Open an asyncssh connection to an authorised extra target.

        Reuses the session's master password (loaded from the Django
        session store at terminal-open time) to unlock the target's
        encrypted secret. Returns ``None`` on any failure — the agent
        receives a tool error and can ``ask_user`` for credentials.
        """
        return await open_agent_target_connection(
            user_id=self._user_id,
            server_id=server_id,
            get_master_password=self._get_session_master_password,
            resolve_server_secret=self._resolve_server_secret,
        )

    async def _ai_plan_commands(
        self,
        user_message: str,
        rules_context: str,
        terminal_tail: str,
        history: list[dict] | None = None,
        unavailable_cmds: set[str] | None = None,
        chat_mode: str = "agent",
        execution_mode: str = "step",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Ask internal LLM to decide mode and return JSON:
          mode=answer → just reply, no commands
          mode=ask    → ask a clarifying question
          mode=execute → run commands on the server

        Untrusted inputs (terminal_tail, rules_context, history, user_message)
        are sanitised by
        :func:`servers.services.terminal_ai.prompts.build_planner_prompt`
        before embedding into the prompt (F1-1 / F1-2).
        The response is validated against
        :class:`servers.services.terminal_ai.schemas.TerminalPlanResponse`
        (F1-6).
        """
        from servers.services.terminal_ai import plan_terminal_commands

        logger.debug(
            "Terminal AI plan_commands: server_id=%s run_id=%s",
            getattr(self.server, "id", None),
            getattr(self, "_ai_run_id", ""),
        )

        return await plan_terminal_commands(
            user_message=user_message,
            rules_context=rules_context,
            terminal_tail=terminal_tail,
            history=history,
            unavailable_cmds=unavailable_cmds,
            chat_mode=chat_mode,
            execution_mode=execution_mode,
            dry_run=dry_run,
            semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
        )

    _compute_report_status = staticmethod(compute_report_status)
    _build_fallback_report = staticmethod(build_fallback_report)

    async def _generate_ai_report_text(self, user_message: str, done_items: list[dict[str, Any]]) -> str:
        from servers.services.terminal_ai import generate_ai_report_text

        return await generate_ai_report_text(
            user_message,
            done_items,
            semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
        )

    async def _ai_make_report(self, user_message: str, commands_with_output: list[dict[str, Any]]) -> str:
        """
        По выводу выполненных команд и запросу пользователя формирует краткий отчёт:
        какие проблемы обнаружены или что проблем нет.

        Untrusted output/user_message is sanitised by
        :func:`servers.services.terminal_ai.prompts.build_report_prompt`
        before embedding into the prompt (F1-1 / F1-2).
        """
        from servers.services.terminal_ai import make_ai_report

        return await make_ai_report(
            user_message,
            commands_with_output,
            semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
        )

    _sanitize_memory_line = staticmethod(sanitize_memory_line)

    def _spawn_memory_extraction_task(
        self,
        *,
        user_message: str,
        commands_with_output: list[dict[str, Any]],
        report: str,
        user_id: int,
        server_id: int,
        audit_ctx: dict[str, Any],
    ) -> None:
        """Fire-and-forget: extract + persist server memory (F1-7).

        The extraction+save pair is ~4-5s of LLM latency + DB writes. Running
        them inline in ``_ai_process_queue`` blocks the UI ``idle`` event.
        Instead we spawn a detached task and track it so disconnect/cancel
        can wait on or cancel in-flight background work.
        """
        loop = asyncio.get_event_loop()
        task = loop.create_task(
            self._run_memory_extraction_background(
                user_message=user_message,
                commands_with_output=list(commands_with_output or []),
                report=report or "",
                user_id=user_id,
                server_id=server_id,
                audit_ctx=dict(audit_ctx or {}),
            ),
            name=f"terminal-ai-memory-{getattr(self, '_ai_run_id', '')}",
        )
        self._ai_background_tasks.add(task)
        task.add_done_callback(self._ai_background_tasks.discard)

    async def _run_memory_extraction_background(
        self,
        *,
        user_message: str,
        commands_with_output: list[dict[str, Any]],
        report: str,
        user_id: int,
        server_id: int,
        audit_ctx: dict[str, Any],
    ) -> None:
        """Body of the fire-and-forget memory-extraction task (F1-7)."""
        try:
            with audit_context(**audit_ctx):
                from servers.services.terminal_ai import run_memory_extraction

                await run_memory_extraction(
                    user_message=user_message,
                    commands_with_output=commands_with_output,
                    report=report,
                    user_id=user_id,
                    server_id=server_id,
                    semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Background memory extraction failed: %s", exc)

    async def _ai_extract_server_memory(
        self,
        user_message: str,
        commands_with_output: list[dict[str, Any]],
        report: str = "",
    ) -> dict[str, Any]:
        """
        Build concise, durable server context from current run:
        key facts, important paths/services, and active issues.

        Untrusted output/report/user_message is sanitised by
        :func:`servers.services.terminal_ai.prompts.build_memory_extraction_prompt`
        before embedding into the prompt (F1-1 / F1-2). The response is
        validated against
        :class:`servers.services.terminal_ai.schemas.MemoryExtraction` (F1-6).
        """
        from servers.services.terminal_ai import extract_server_memory

        return await extract_server_memory(
            user_message=user_message,
            commands_with_output=commands_with_output,
            report=report,
            semaphore=_TERMINAL_AI_LLM_SEMAPHORE,
        )

    async def _save_ai_server_profile(
        self,
        user_id: int,
        server_id: int,
        summary: str,
        facts: list[str],
        issues: list[str],
    ) -> dict[str, Any]:
        """Forwarder to :func:`servers.services.terminal_ai.save_server_profile` (F2-3)."""
        from servers.services.terminal_ai import save_server_profile

        return await save_server_profile(
            user_id=user_id,
            server_id=server_id,
            summary=summary,
            facts=facts,
            issues=issues,
        )

    _extract_json_object = staticmethod(extract_json_object)

    def _compute_confirm_reason(
        self,
        cmd: str,
        forbidden_patterns: list[str],
        allowlist_patterns: list[str] | None = None,
        *,
        confirm_dangerous_commands: bool = True,
    ) -> str:
        return compute_confirm_reason(
            cmd,
            forbidden_patterns=forbidden_patterns,
            allowlist_patterns=allowlist_patterns,
            confirm_dangerous_commands=confirm_dangerous_commands,
        )

    _matches_patterns = staticmethod(match_patterns)

