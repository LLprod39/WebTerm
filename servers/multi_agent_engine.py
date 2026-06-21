"""Multi-agent orchestration engine for server agents."""

from __future__ import annotations

import asyncio
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
from app.core.model_utils import resolve_provider_and_model
from core_ui.audit import audit_context
from servers.adapters.memory_store import DjangoServerMemoryStore
from servers.agent_runtime import (
    build_runtime_control_state,
    update_runtime_control,
)
from servers.agent_sessions import AgentSessionManager
from servers.agent_tools import get_enabled_tools
from servers.models import AgentRun, Server, ServerAgent
from servers.multi_agent_engine_config import (
    CONTROL_POLL_INTERVAL,
    MAX_TASK_ITERATIONS,
    SESSION_TIMEOUT_DEFAULT,
)
from servers.multi_agent_engine_runner import (
    execute_existing_multi_agent_plan,
    run_multi_agent_engine,
)
from servers.multi_agent_llm import call_multi_agent_llm_history, call_multi_agent_llm_raw
from servers.multi_agent_memory import (
    build_multi_agent_ops_prompt_context,
    persist_multi_agent_ops_summary,
)
from servers.multi_agent_plan_executor import PlanExecutionCallbacks
from servers.multi_agent_planning import (
    handle_multi_agent_failure,
    plan_multi_agent_tasks,
    replan_multi_agent_tasks,
    synthesize_multi_agent_report,
)
from servers.multi_agent_subagents import (
    build_subagent_prompt_context,
    build_task_subagent,
    prepare_plan_tasks,
)
from servers.multi_agent_task_runner import run_multi_agent_task, summarize_multi_agent_task
from servers.multi_agent_tool_execution import MultiAgentToolExecutionContext, execute_multi_agent_tool


def sync_to_async(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)

# ---------------------------------------------------------------------------
# MultiAgentEngine
# ---------------------------------------------------------------------------

class MultiAgentEngine:
    """Two-level multi-agent pipeline."""

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

        self.session_timeout = agent.session_timeout_seconds or SESSION_TIMEOUT_DEFAULT
        self.tools_config = dict(agent.tools_config or {})
        self.allowed_tool_names = {name for name, enabled in self.tools_config.items() if enabled} if self.tools_config else None
        self.enabled_tools = get_enabled_tools(self.tools_config)

        self._stop_requested = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_cleanup_scheduled = False
        self._control_task: asyncio.Task | None = None

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
        self.permission_engine = PermissionEngine(mode=self.role_spec.default_permission_mode, sudo_policy=agent.sudo_policy)
        self.sandbox_manager = SandboxManager()
        self.hook_manager = HookManager()
        self.memory_store = DjangoServerMemoryStore()
        self.tool_registry: ToolRegistry | None = None
        self.ops_prompt_context = ""
        self.server_memory_prompt = ""
        self.operational_recipes_prompt = ""
        if self.skills:
            for tool_name in ("list_skills", "read_skill"):
                if tool_name not in self.enabled_tools:
                    self.enabled_tools.append(tool_name)
            if self.allowed_tool_names is not None:
                self.allowed_tool_names.update({"list_skills", "read_skill"})

    # ------------------------------------------------------------------
    # Public control methods
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
    # Main run
    # ------------------------------------------------------------------

    async def run(self, plan_only: bool = False, run_record: AgentRun | None = None) -> AgentRun:
        return await run_multi_agent_engine(self, plan_only=plan_only, run_record=run_record)

    async def execute_existing_plan(self, run: AgentRun) -> AgentRun:
        return await execute_existing_multi_agent_plan(self, run)

    # ------------------------------------------------------------------
    # Phase 1: Planning
    # ------------------------------------------------------------------

    async def _plan(self, goal: str, orchestrator_log: list) -> list[dict]:
        return await plan_multi_agent_tasks(self, goal, orchestrator_log)

    def _prepare_plan_tasks(self, tasks: list[dict]) -> list[dict]:
        return prepare_plan_tasks(
            tasks,
            agent_type=self.agent.agent_type,
            parent_goal=self.agent.goal or self.agent.ai_prompt,
            tool_registry=self.tool_registry,
            max_task_iterations=MAX_TASK_ITERATIONS,
        )

    def _build_task_subagent(self, task: dict) -> dict:
        return build_task_subagent(
            task,
            agent_type=self.agent.agent_type,
            parent_goal=self.agent.goal or self.agent.ai_prompt,
            fallback_role_spec=self.role_spec,
            parent_permission_engine=self.permission_engine,
            tool_registry=self.tool_registry,
            max_task_iterations=MAX_TASK_ITERATIONS,
        )

    def _build_subagent_prompt_context(self, task_subagent: dict) -> str:
        return build_subagent_prompt_context(
            task_subagent,
            server_memory_prompt=self.server_memory_prompt,
            operational_recipes_prompt=self.operational_recipes_prompt,
            session_timeout=self.session_timeout,
        )

    def _build_plan_execution_callbacks(self, run: AgentRun) -> PlanExecutionCallbacks:
        async def persist_plan_tasks(plan_tasks: list[dict]) -> None:
            await sync_to_async(self._update_run)(run, plan_tasks=plan_tasks)

        async def persist_plan_state(plan_tasks: list[dict], orchestrator_log: list[dict]) -> None:
            await sync_to_async(self._update_run)(run, plan_tasks=plan_tasks, orchestrator_log=orchestrator_log)

        async def set_waiting(question: str, plan_tasks: list[dict]) -> None:
            await sync_to_async(self._update_run)(
                run,
                status=AgentRun.STATUS_WAITING,
                pending_question=question,
                plan_tasks=plan_tasks,
            )

        async def clear_waiting() -> None:
            await sync_to_async(self._update_run)(run, status=AgentRun.STATUS_RUNNING, pending_question="")

        return PlanExecutionCallbacks(
            stop_requested=lambda: self._stop_requested,
            wait_for_resume=self._pause_event.wait,
            emit=self._emit,
            persist_plan_tasks=persist_plan_tasks,
            persist_plan_state=persist_plan_state,
            set_waiting=set_waiting,
            clear_waiting=clear_waiting,
            run_task=self._run_task,
            handle_failure=self._handle_failure,
            replan=self._replan,
            wait_for_user_reply=self._wait_for_user_reply,
        )

    # ------------------------------------------------------------------
    # Phase 2: Task execution (mini ReAct)
    # ------------------------------------------------------------------

    async def _run_task(self, task: dict, context_summary: str, deadline: float) -> tuple[str, list]:
        return await run_multi_agent_task(self, task, context_summary, deadline)

    async def _summarize_task(self, task: dict, iterations: list[dict]) -> str:
        return await summarize_multi_agent_task(self, task, iterations)

    # ------------------------------------------------------------------
    # Phase 2.5: Error handling
    # ------------------------------------------------------------------

    async def _handle_failure(
        self,
        failed_task: dict,
        error: str,
        all_tasks: list[dict],
        orchestrator_log: list,
    ) -> dict:
        return await handle_multi_agent_failure(self, failed_task, error, all_tasks, orchestrator_log)

    async def _replan(self, goal: str, plan_tasks: list[dict], orchestrator_log: list) -> list[dict]:
        return await replan_multi_agent_tasks(self, goal, plan_tasks, orchestrator_log)

    # ------------------------------------------------------------------
    # Phase 3: Final synthesis
    # ------------------------------------------------------------------

    async def _synthesize(self, goal: str, plan_tasks: list[dict], orchestrator_log: list) -> str:
        return await synthesize_multi_agent_report(self, goal, plan_tasks, orchestrator_log)

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    async def _call_llm_raw(self, system_prompt: str, user_msg: str) -> str:
        return await call_multi_agent_llm_raw(self, system_prompt, user_msg)

    async def _call_llm_history(self, history: list[dict]) -> str:
        return await call_multi_agent_llm_history(self, history)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(response: str) -> tuple[str, str | None, dict]:
        return parse_response(response)

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def _execute_tool(
        self,
        name: str,
        args: dict,
        *,
        permission_engine: PermissionEngine | None = None,
        tool_registry: ToolRegistry | None = None,
        allowed_tool_names: list[str] | None = None,
    ) -> str:
        return await execute_multi_agent_tool(
            name,
            args,
            context=MultiAgentToolExecutionContext(
                session=self.session,
                permission_engine=self.permission_engine,
                sandbox_manager=self.sandbox_manager,
                hook_manager=self.hook_manager,
                tool_registry=self.tool_registry,
                enabled_tools=self.enabled_tools,
                mcp_tools=self.mcp_tools,
                disabled_mcp_tools=self.disabled_mcp_tools,
                skill_provider=self._skill_provider,
                skill_policies=self.skill_policies,
                executed_mcp_tools=self._executed_mcp_tools,
                mcp_runtime_provider=self._mcp_runtime_provider,
            ),
            permission_engine=permission_engine,
            tool_registry=tool_registry,
            allowed_tool_names=allowed_tool_names,
        )

    async def _build_ops_prompt_context(self) -> str:
        return await build_multi_agent_ops_prompt_context(self)

    async def _persist_ops_summary(
        self,
        *,
        run: AgentRun,
        final_status: str,
        final_report: str,
        plan_tasks: list[dict],
    ):
        await persist_multi_agent_ops_summary(
            self,
            run=run,
            final_status=final_status,
            final_report=final_report,
            plan_tasks=plan_tasks,
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
    # User reply (ask_user flow)
    # ------------------------------------------------------------------

    async def _wait_for_user_reply(self, timeout: float = 3600) -> str:
        if self.session:
            loop = asyncio.get_event_loop()
            self.session.user_reply_future = loop.create_future()
            await self._sync_runtime_control()
            try:
                return await asyncio.wait_for(self.session.user_reply_future, timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                if self._stop_requested:
                    raise RuntimeError("Stopped by user")
                return "Нет ответа (таймаут)"
        return "Нет сессии"

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
