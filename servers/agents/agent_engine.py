"""
Full ReAct agent engine.

F-08a.10: ops memory prompt helpers live in ``agent_engine_ops``.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Coroutine
from contextlib import suppress

from asgiref.sync import sync_to_async as _s2a
from django.utils import timezone
from loguru import logger

from app.agent_kernel import mcp_runtime_registry, skill_provider_registry
from app.agent_kernel.domain.roles import get_role_spec
from app.agent_kernel.domain.specs import MCPRuntimeProvider, SkillProvider
from app.agent_kernel.hooks.manager import HookManager
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.runtime.parsing import parse_action as _parse_action  # noqa: F401
from app.agent_kernel.runtime.parsing import parse_response
from app.agent_kernel.sandbox.manager import SandboxManager
from app.agent_kernel.tools.registry import ToolRegistry
from app.core.llm import LLMProvider, is_thinking_chunk
from app.core.model_utils import resolve_provider_and_model
from core_ui.audit import audit_context
from servers.adapters.memory_store import DjangoServerMemoryStore
from servers.agents.agent_budgets import (
    FULL_DEFAULT_COMMAND_TIMEOUT_SEC,
    FULL_DEFAULT_MAX_ITERATIONS,
    FULL_DEFAULT_SESSION_TIMEOUT_SEC,
    FULL_MAX_ITERATIONS_CAP,
    clamp_command_timeout,
    clamp_full_iterations,
)
from servers.agents.agent_engine_ops import AgentEngineOpsMixin
from servers.agents.agent_engine_prompts import build_system_prompt, generate_final_report
from servers.agents.agent_engine_runner import run_agent_engine
from servers.agents.agent_engine_tools import execute_agent_tool, validate_agent_tool_args
from servers.agents.agent_runtime import (
    build_runtime_control_state,
    update_runtime_control,
)
from servers.agents.agent_sessions import AgentSessionManager
from servers.agents.agent_tools import get_enabled_tools
from servers.models import AgentRun, Server, ServerAgent


def sync_to_async(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


SESSION_TIMEOUT_DEFAULT = FULL_DEFAULT_SESSION_TIMEOUT_SEC
MAX_ITERATIONS_CAP = FULL_MAX_ITERATIONS_CAP
DEFAULT_COMMAND_TIMEOUT = FULL_DEFAULT_COMMAND_TIMEOUT_SEC
CONTROL_POLL_INTERVAL = 0.5

_MISSING_ACTION_INTENT_RE = re.compile(
    r"\b("
    r"выполню|запущу|проверю|вызову|использую|соберу|прочитаю|получу|"
    r"execute|run|check|call|use|collect|read|query"
    r")\b",
    re.IGNORECASE,
)
_FINAL_COMPLETION_RE = re.compile(
    r"\b("
    r"задача\s+завершена|цель\s+достигнута|готово|итог|вывод|"
    r"task\s+complete|goal\s+complete|final\s+answer|done"
    r")\b",
    re.IGNORECASE,
)


class AgentEngine(AgentEngineOpsMixin):
    """
    Runs a full ReAct agent against one or more servers.

    Usage::

        engine = AgentEngine(agent, servers, user, event_callback=ws_send)
        run = await engine.run()
    """

    def __init__(
        self,
        agent: ServerAgent,
        servers: list[Server],
        user,
        event_callback: Callable[..., Coroutine] | None = None,
        model_preference: str = "auto",
        specific_model: str | None = None,
        mcp_servers: list | None = None,
        skills: list | None = None,
        skill_errors: list[str] | None = None,
        skill_provider: SkillProvider | None = None,
        mcp_runtime_provider: MCPRuntimeProvider | None = None,
    ):
        self.agent = agent
        self.servers = servers
        self.user = user
        self.event_callback = event_callback

        self.max_iterations = clamp_full_iterations(agent.max_iterations or FULL_DEFAULT_MAX_ITERATIONS)
        self.session_timeout = agent.session_timeout_seconds or SESSION_TIMEOUT_DEFAULT
        self.tools_config = dict(agent.tools_config or {})
        self.command_timeout = clamp_command_timeout(
            self.tools_config.get("command_timeout")
            or self.tools_config.get("command_timeout_seconds")
            or DEFAULT_COMMAND_TIMEOUT
        )
        self.allowed_tool_names = (
            {name for name, enabled in self.tools_config.items() if enabled} if self.tools_config else None
        )
        self.enabled_tools = get_enabled_tools(self.tools_config)

        self._stop_requested = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_cleanup_scheduled = False
        self._control_task: asyncio.Task | None = None
        self._mid_run_replan_injected = False
        self._missing_action_reprompts = 0

        self.session: AgentSessionManager | None = None
        self.run_record: AgentRun | None = None
        self.mcp_servers = list(mcp_servers or [])
        self.mcp_tools = {}
        self.disabled_mcp_tools: set[str] = set()
        self.mcp_tool_errors: list[str] = []
        self._mcp_runtime_provider: MCPRuntimeProvider | None = mcp_runtime_provider or mcp_runtime_registry.get()
        self.skills = list(skills or [])
        self.skill_errors = list(skill_errors or [])
        self._skill_provider: SkillProvider | None = skill_provider or skill_provider_registry.get()
        if self._skill_provider is not None:
            self.skill_policies, policy_errors = self._skill_provider.compile_skill_policies(self.skills)
        else:
            self.skill_policies, policy_errors = ([], [])
        self.skill_policy_errors = list(policy_errors)
        if self.skill_policy_errors:
            self.skill_errors.extend(self.skill_policy_errors)
        self._executed_mcp_tools: set[str] = set()
        self.model_preference, self.specific_model = resolve_provider_and_model(
            model_preference,
            specific_model,
            default_provider="auto",
        )
        self.role_spec = get_role_spec(agent.agent_type, agent.goal or agent.ai_prompt)
        self.permission_engine = PermissionEngine(
            mode=self.role_spec.default_permission_mode, sudo_policy=agent.sudo_policy
        )
        self.sandbox_manager = SandboxManager()
        self.hook_manager = HookManager()
        self.memory_store = DjangoServerMemoryStore()
        self.tool_registry: ToolRegistry | None = None
        self.ops_prompt_context = ""
        if self.skills:
            for tool_name in ("list_skills", "read_skill"):
                if tool_name not in self.enabled_tools:
                    self.enabled_tools.append(tool_name)
            if self.allowed_tool_names is not None:
                self.allowed_tool_names.update({"list_skills", "read_skill"})

        # Materials tools are always available when the agent has input_artifacts,
        # so the model can list/read scripts and run operator-provided scripts.
        from servers.agents.agent_inputs import MATERIALS_TOOL_NAMES, normalize_input_artifacts

        self.input_materials = normalize_input_artifacts(getattr(agent, "input_artifacts", None) or [])
        if self.input_materials:
            for tool_name in MATERIALS_TOOL_NAMES:
                if tool_name not in self.enabled_tools:
                    self.enabled_tools.append(tool_name)
            if self.allowed_tool_names is not None:
                self.allowed_tool_names.update(MATERIALS_TOOL_NAMES)

    # ------------------------------------------------------------------
    # Public control methods (called from WebSocket consumer)
    # ------------------------------------------------------------------

    def request_stop(self):
        if self._stop_requested and self._stop_cleanup_scheduled:
            return
        self._stop_requested = True
        self._pause_event.set()
        if self.session and self.session.user_reply_future and not self.session.user_reply_future.done():
            self.session.user_reply_future.cancel()
        self._schedule_session_shutdown()

    def request_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()

    def request_resume(self):
        if not self._pause_event.is_set():
            self._pause_event.set()

    def provide_user_reply(self, answer: str) -> bool:
        if self.session and self.session.user_reply_future and not self.session.user_reply_future.done():
            self.session.user_reply_future.set_result(answer)
            return True
        return False

    def _schedule_session_shutdown(self):
        if self._stop_cleanup_scheduled:
            return
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        self._stop_cleanup_scheduled = True

        async def shutdown_sessions():
            if not self.session:
                return
            server_ids = list(self.session.connections)
            for server_id in server_ids:
                with suppress(Exception):
                    await self.session.send_signal(server_id, "ctrl_c")
            with suppress(Exception):
                await self.session.close_all()

        try:
            loop.call_soon_threadsafe(lambda: asyncio.create_task(shutdown_sessions()))
        except RuntimeError:
            self._stop_cleanup_scheduled = False

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    async def run(self, run_record: AgentRun | None = None) -> AgentRun:
        return await run_agent_engine(self, run_record)

    def _audit_scope(self):
        return audit_context(
            user_id=getattr(self.user, "id", None),
            username_snapshot=str(getattr(self.user, "username", "") or ""),
            channel="agent",
            path=f"/servers/api/agents/{self.agent.id}/run/",
            entity_type="agent_run",
            entity_id=str(getattr(self.run_record, "id", "") or ""),
            entity_name=self.agent.name,
        )

    # ------------------------------------------------------------------
    # Runtime control
    # ------------------------------------------------------------------

    async def _watch_runtime_control(self):
        while True:
            await self._sync_runtime_control()
            await asyncio.sleep(CONTROL_POLL_INTERVAL)

    async def _sync_runtime_control(self):
        if not self.run_record:
            return

        payload = await sync_to_async(
            lambda: AgentRun.objects.filter(pk=self.run_record.pk).values("runtime_control").first(),
            thread_sensitive=True,
        )()
        if not payload:
            return

        control = build_runtime_control_state(payload.get("runtime_control"))
        if control["stop_requested"]:
            self.request_stop()
        if control["pause_requested"]:
            self.request_pause()
        else:
            self.request_resume()

        reply_nonce = int(control["reply_nonce"])
        reply_ack_nonce = int(control["reply_ack_nonce"])
        if reply_nonce > reply_ack_nonce and control["reply_text"] and self.provide_user_reply(control["reply_text"]):
            await sync_to_async(self._ack_runtime_reply, thread_sensitive=True)(reply_nonce)

    def _ack_runtime_reply(self, reply_nonce: int):
        if not self.run_record:
            return
        run = AgentRun.objects.filter(pk=self.run_record.pk).first()
        if not run:
            return
        update_runtime_control(run, reply_ack_nonce=reply_nonce)

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    async def _call_llm(self, history: list[dict]) -> str:
        """Call LLM with conversation history. Raises on failure."""
        prompt = self._history_to_prompt(history)
        provider = LLMProvider()
        chunks = []
        try:
            with self._audit_scope():
                async for chunk in provider.stream_chat(
                    prompt,
                    model=self.model_preference,
                    specific_model=self.specific_model,
                    purpose="ops",
                ):
                    if not is_thinking_chunk(chunk):
                        chunks.append(chunk)
        except Exception as exc:
            logger.error("LLM call failed: {}", exc)
            raise
        return "".join(chunks)

    @staticmethod
    def _history_to_prompt(history: list[dict]) -> str:
        parts = []
        for msg in history:
            role = msg["role"].upper()
            parts.append(f"[{role}]\n{msg['content']}")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(response: str) -> tuple[str, str | None, dict]:
        """Extract THOUGHT and ACTION from LLM response."""
        return parse_response(response)

    def _should_reprompt_missing_action(self, response: str, tool_calls_log: list[dict]) -> bool:
        """Prevent empty "planned but did not act" runs.

        Some chat models describe the next tool they intend to call but omit the
        required ACTION line. Treating that as a final answer produces a bogus
        completed run with zero evidence. Allow up to 2 reprompts early in the
        run (before many tools have run), when tools are available and the text
        still expresses action intent rather than completion.
        """
        if len(tool_calls_log) > 2:
            return False
        if getattr(self, "_missing_action_reprompts", 0) >= 2:
            return False
        if not (self.enabled_tools or self.mcp_tools):
            return False

        text = (response or "").strip()
        if not text:
            return False
        if "ACTION:" in text.upper():
            return False
        if _FINAL_COMPLETION_RE.search(text):
            return False
        return bool(_MISSING_ACTION_INTENT_RE.search(text))

    def _missing_action_correction(self) -> str:
        available = ", ".join([*self.enabled_tools, *self.mcp_tools.keys()]) or "нет доступных инструментов"
        return (
            "FORMAT ERROR: ты описал следующий шаг, но не вызвал инструмент. "
            "Продолжай работу и верни ответ строго в формате:\n"
            "THOUGHT: <коротко зачем нужен следующий шаг>\n"
            'ACTION: tool_name {"param1": "value"}\n'
            f"Доступные инструменты: {available}. "
            "Не заверши задачу, пока не соберёшь факты через инструменты."
        )

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def _execute_tool(self, name: str, args: dict) -> str:
        return await execute_agent_tool(self, name, args)

    @staticmethod
    def _validate_tool_args(name: str, args: dict, spec) -> str:
        return validate_agent_tool_args(name, args, spec)

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        return build_system_prompt(self)

    # ------------------------------------------------------------------
    # Final report
    # ------------------------------------------------------------------

    async def _generate_final_report(self, history: list[dict], iterations: list[dict]) -> str:
        return await generate_final_report(self, history, iterations)

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _update_run(run: AgentRun, **kwargs):
        for k, v in kwargs.items():
            setattr(run, k, v)
        run.save(update_fields=list(kwargs.keys()))

    def _touch_agent_last_run(self):
        if not self.agent.pk:
            return
        self.agent.last_run_at = timezone.now()
        self.agent.save(update_fields=["last_run_at"])

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    async def _emit(self, event_type: str, data: dict):
        if self.event_callback:
            try:
                await self.event_callback(event_type, data)
            except Exception as exc:
                logger.debug("Event callback error: {}", exc)
