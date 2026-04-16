"""
Multi-Agent Pipeline Engine.

Implements a two-level orchestration model:
  1. Orchestrator LLM — decomposes the goal into discrete tasks and manages flow
  2. Task Agent LLM  — executes a single task with its own mini ReAct loop

Flow:
  goal → Orchestrator → [task1, task2, ..., taskN]
       → TaskAgent(task1) → result → Orchestrator
       → TaskAgent(task2) → result → Orchestrator  [or failure → decision]
       → ...
       → Synthesize → final_report
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Callable, Coroutine
from contextlib import suppress

from asgiref.sync import sync_to_async as _s2a
from django.utils import timezone
from loguru import logger

from app.agent_kernel.domain.roles import ROLE_SPECS, get_role_spec
from app.agent_kernel.hooks.manager import HookManager
from app.agent_kernel.memory.compaction import build_run_summary_payload
from app.agent_kernel.memory.server_cards import render_server_cards_prompt
from app.agent_kernel.memory.store import DjangoServerMemoryStore
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.runtime.context import build_ops_prompt_context
from app.agent_kernel.runtime.subagents import build_task_subagent_spec
from app.agent_kernel.sandbox.manager import SandboxManager
from app.agent_kernel.tools.registry import ToolRegistry
from app.core.llm import LLMProvider
from app.core.model_utils import resolve_provider_and_model
from core_ui.audit import audit_context
from servers.agent_runtime import (
    build_runtime_control_state,
    is_runtime_stop_requested,
    register_engine,
    reset_runtime_control_state,
    unregister_engine,
    update_runtime_control,
)
from servers.agent_sessions import AgentSessionManager
from servers.agent_tools import get_enabled_tools, get_tools_description
from servers.mcp_tool_runtime import build_mcp_tools_description, execute_bound_mcp_tool, load_mcp_tool_bindings
from servers.models import AgentRun, Server, ServerAgent
from app.agent_kernel import skill_provider_registry
from app.agent_kernel.domain.specs import SkillProvider


def sync_to_async(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


from app.agent_kernel.runtime.parsing import parse_action as _parse_action  # noqa: F401
from app.agent_kernel.runtime.parsing import parse_response

MAX_PLAN_TASKS = 15
MAX_TASK_ITERATIONS = 7
SESSION_TIMEOUT_DEFAULT = 900
CONTROL_POLL_INTERVAL = 0.5


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _make_task(
    task_id: int,
    name: str,
    description: str,
    *,
    role: str = "custom",
    permission_mode: str = "SAFE",
    max_iterations: int = MAX_TASK_ITERATIONS,
    tool_names: list[str] | None = None,
) -> dict:
    return {
        "id": task_id,
        "name": name,
        "description": description,
        "role": role,
        "permission_mode": permission_mode,
        "max_iterations": max_iterations,
        "tool_names": list(tool_names or []),
        "status": "pending",
        "thought": "",
        "iterations": [],
        "result": "",
        "error": "",
        "orchestrator_decision": None,
        "verification_summary": "",
        "subagent": {},
        "started_at": None,
        "completed_at": None,
    }


# ---------------------------------------------------------------------------
# MultiAgentEngine
# ---------------------------------------------------------------------------

class MultiAgentEngine:
    """
    Two-level multi-agent pipeline.

    Usage::

        engine = MultiAgentEngine(agent, servers, user, event_callback=ws_send)
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
        self.permission_engine = PermissionEngine(mode=self.role_spec.default_permission_mode)
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
        """Run the full pipeline or planning-only phase.

        If plan_only=True: plans tasks, sets status=plan_review, and returns
        without executing. Call execute_existing_plan() to continue.
        """
        self._loop = asyncio.get_running_loop()
        primary_server = self.servers[0] if self.servers else None
        if run_record is None:
            run = await sync_to_async(AgentRun.objects.create)(
                agent=self.agent,
                server=primary_server,
                user=self.user,
                status=AgentRun.STATUS_RUNNING,
                runtime_control=reset_runtime_control_state(),
            )
        else:
            current_status = await sync_to_async(
                lambda: AgentRun.objects.filter(pk=run_record.pk).values("status", "runtime_control").first()
            )()
            run = run_record
            if not current_status:
                self.run_record = run
                return run
            if current_status["status"] == AgentRun.STATUS_STOPPED or is_runtime_stop_requested(current_status["runtime_control"]):
                self.run_record = run
                return run
            await sync_to_async(self._update_run)(
                run,
                agent=self.agent,
                server=primary_server,
                user=self.user,
                status=AgentRun.STATUS_RUNNING,
                ai_analysis="",
                commands_output=[],
                duration_ms=0,
                completed_at=None,
                total_iterations=0,
                connected_servers=[],
                runtime_control=reset_runtime_control_state(),
                pending_question="",
                final_report="",
                plan_tasks=[],
                orchestrator_log=[],
                started_at=timezone.now(),
            )
        self.run_record = run
        register_engine(run.id, getattr(self.agent, "id", None), self)
        self._control_task = asyncio.create_task(self._watch_runtime_control())
        await self._sync_runtime_control()
        t0 = time.monotonic()

        self.session = AgentSessionManager(
            allowed_servers=self.servers,
            max_connections=self.agent.max_connections or 5,
            command_timeout=30,
            event_callback=self.event_callback,
            available_skills=[skill.to_detail_dict() for skill in self.skills],
        )

        plan_tasks: list[dict] = []
        orchestrator_log: list[dict] = []

        try:
            if self.skill_policy_errors:
                raise RuntimeError(
                    "Invalid skill policy configuration: "
                    + "; ".join(self.skill_policy_errors)
                )
            await self._emit("agent_status", {"status": "connecting"})

            if self.servers:
                if self.agent.allow_multi_server:
                    for srv in self.servers:
                        try:
                            await self.session.open(srv)
                        except Exception as exc:
                            logger.warning("Failed to connect to {}: {}", srv.name, exc)
                else:
                    await self.session.open(primary_server)

            loaded_mcp_tools, self.mcp_tool_errors = await load_mcp_tool_bindings(self.mcp_servers)
            if self.allowed_tool_names is None:
                self.mcp_tools = loaded_mcp_tools
                self.disabled_mcp_tools = set()
            else:
                self.mcp_tools = {
                    name: binding for name, binding in loaded_mcp_tools.items() if name in self.allowed_tool_names
                }
                self.disabled_mcp_tools = set(loaded_mcp_tools) - set(self.mcp_tools)
            self.tool_registry = ToolRegistry.from_sources(self.enabled_tools, self.mcp_tools)
            self.ops_prompt_context = await self._build_ops_prompt_context()

            connected = self.session.get_connected_info()
            await sync_to_async(self._update_run)(run, connected_servers=[
                {"server_id": c["server_id"], "server_name": c["server_name"]}
                for c in connected
            ])

            if not self.session.connections and not self.mcp_tools and not self.skills:
                raise RuntimeError("No servers connected, no MCP tools available, and no skills attached.")

            goal = self.agent.goal or self.agent.ai_prompt or "Analyse the servers."

            # ----------------------------------------------------------------
            # Phase 1: Orchestrator creates the plan
            # ----------------------------------------------------------------
            await self._emit("agent_status", {"status": "planning"})
            await self._emit("agent_pipeline_phase", {"phase": "planning", "message": "Orchestrator is creating a task plan…"})

            plan_tasks = await self._plan(goal, orchestrator_log)

            await sync_to_async(self._update_run)(run, plan_tasks=plan_tasks, orchestrator_log=orchestrator_log)
            await self._emit("agent_plan", {"tasks": plan_tasks})

            if plan_only:
                # Stop here — wait for human approval
                run.status = AgentRun.STATUS_PLAN_REVIEW
                run.plan_tasks = plan_tasks
                run.orchestrator_log = orchestrator_log
                run.duration_ms = int((time.monotonic() - t0) * 1000)
                await sync_to_async(run.save)()
                await self._emit("agent_status", {"status": "plan_review"})
                await self._emit("agent_pipeline_phase", {
                    "phase": "plan_review",
                    "message": "План готов. Ожидаем подтверждения пользователя…",
                })
                return run

            # ----------------------------------------------------------------
            # Phase 2: Execute tasks sequentially (with optional replan on failure)
            # ----------------------------------------------------------------
            context_summary = ""
            deadline = time.monotonic() + self.session_timeout

            while True:
                loop_break = False
                for task in plan_tasks:
                    if self._stop_requested:
                        task["status"] = "skipped"
                        task["error"] = "Stopped by user"
                        continue

                    await self._pause_event.wait()

                    if time.monotonic() > deadline:
                        task["status"] = "skipped"
                        task["error"] = "Session timeout"
                        continue

                    task["status"] = "running"
                    task["started_at"] = timezone.now().isoformat()
                    await sync_to_async(self._update_run)(run, plan_tasks=plan_tasks)
                    await self._emit("agent_task_start", {"task_id": task["id"], "name": task["name"], "description": task["description"]})

                    try:
                        result, iterations = await self._run_task(task, context_summary, deadline)
                        task["status"] = "done"
                        task["result"] = result
                        task["iterations"] = iterations
                        task["completed_at"] = timezone.now().isoformat()
                        context_summary += f"\n\n### Задача {task['id']}: {task['name']}\nРезультат: {result[:1000]}"
                        await self._emit("agent_task_done", {"task_id": task["id"], "result": result[:500]})

                    except Exception as exc:
                        if self._stop_requested:
                            task["status"] = "skipped"
                            task["error"] = "Stopped by user"
                            task["completed_at"] = timezone.now().isoformat()
                            await sync_to_async(self._update_run)(
                                run,
                                plan_tasks=plan_tasks,
                                orchestrator_log=orchestrator_log,
                            )
                            loop_break = True
                            break

                        task["status"] = "failed"
                        task["error"] = str(exc)
                        task["completed_at"] = timezone.now().isoformat()
                        await self._emit("agent_task_failed", {"task_id": task["id"], "error": str(exc)})

                        decision = await self._handle_failure(task, str(exc), plan_tasks, orchestrator_log)
                        task["orchestrator_decision"] = decision

                        if decision["action"] == "abort":
                            await self._emit("agent_pipeline_phase", {"phase": "aborted", "message": decision.get("reason", "")})
                            loop_break = True
                            break
                        elif decision["action"] == "replan":
                            done_tasks = [t for t in plan_tasks if t["status"] == "done"]
                            new_tasks = await self._replan(goal, plan_tasks, orchestrator_log)
                            for j, nt in enumerate(new_tasks):
                                nt["id"] = len(done_tasks) + j + 1
                            plan_tasks[:] = done_tasks + new_tasks
                            await sync_to_async(self._update_run)(run, plan_tasks=plan_tasks, orchestrator_log=orchestrator_log)
                            await self._emit("agent_plan", {"tasks": plan_tasks})
                            await self._emit("agent_pipeline_phase", {"phase": "executing", "message": "План пересобран. Продолжаю выполнение…"})
                            break  # выходим из for, while продолжается — цикл for пойдёт заново с новым планом
                        elif decision["action"] == "ask_user":
                            question = decision.get("message", "Что делать с ошибкой задачи?")
                            await sync_to_async(self._update_run)(
                                run,
                                status=AgentRun.STATUS_WAITING,
                                pending_question=question,
                                plan_tasks=plan_tasks,
                            )
                            await self._emit("agent_status", {"status": "waiting"})
                            answer = await self._wait_for_user_reply()
                            await sync_to_async(self._update_run)(
                                run, status=AgentRun.STATUS_RUNNING, pending_question="",
                            )
                            context_summary += f"\n\n### Ответ пользователя по задаче {task['id']}\n{answer}"
                            task["result"] = f"Пользователь ответил: {answer}"
                        elif decision["action"] == "retry":
                            retry_deadline = deadline
                            if "Session timeout" in str(exc) or "session timeout" in str(exc).lower():
                                retry_deadline = time.monotonic() + 300
                            try:
                                task["status"] = "running"
                                result, iterations = await self._run_task(task, context_summary, retry_deadline)
                                task["status"] = "done"
                                task["result"] = result
                                task["iterations"] = iterations
                                task["completed_at"] = timezone.now().isoformat()
                                context_summary += f"\n\n### Задача {task['id']}: {task['name']} (повтор)\nРезультат: {result[:1000]}"
                                await self._emit("agent_task_done", {"task_id": task["id"], "result": result[:500]})
                            except Exception as exc2:
                                task["status"] = "failed"
                                task["error"] = f"Retry failed: {exc2}"

                    await sync_to_async(self._update_run)(run, plan_tasks=plan_tasks, orchestrator_log=orchestrator_log)

                if loop_break:
                    break
                if not any(t.get("status") == "pending" for t in plan_tasks):
                    break

            # ----------------------------------------------------------------
            # Phase 3: Synthesize final report
            # ----------------------------------------------------------------
            await self._emit("agent_pipeline_phase", {"phase": "synthesizing", "message": "Generating final report…"})
            final_report = await self._synthesize(goal, plan_tasks, orchestrator_log)
            final_report = await self.hook_manager.run_finished(
                final_report,
                self.permission_engine.verification_summary(),
            )

            final_status = AgentRun.STATUS_COMPLETED
            if self._stop_requested:
                final_status = AgentRun.STATUS_STOPPED
            elif any(t["status"] == "failed" for t in plan_tasks):
                final_status = AgentRun.STATUS_COMPLETED  # partial success still completes

            run.status = final_status
            run.plan_tasks = plan_tasks
            run.orchestrator_log = orchestrator_log
            run.total_iterations = sum(len(t.get("iterations", [])) for t in plan_tasks)
            run.final_report = final_report
            run.ai_analysis = final_report
            run.completed_at = timezone.now()
            run.duration_ms = int((time.monotonic() - t0) * 1000)
            await sync_to_async(run.save)()
            await self._persist_ops_summary(
                run=run,
                final_status=final_status,
                final_report=final_report,
                plan_tasks=plan_tasks,
            )

            await sync_to_async(self._touch_agent_last_run)()
            await self._emit("agent_status", {"status": final_status})
            await self._emit("agent_report", {"text": final_report, "interim": False})

        except Exception as exc:
            logger.exception("MultiAgentEngine error: {}", exc)
            run.status = AgentRun.STATUS_FAILED
            run.ai_analysis = f"Pipeline failed: {exc}"
            run.plan_tasks = plan_tasks
            run.orchestrator_log = orchestrator_log
            run.completed_at = timezone.now()
            run.duration_ms = int((time.monotonic() - t0) * 1000)
            await sync_to_async(run.save)()
            await self._persist_ops_summary(
                run=run,
                final_status=run.status,
                final_report=run.ai_analysis,
                plan_tasks=plan_tasks,
            )
            await self._emit("agent_status", {"status": "failed", "error": str(exc)})
        finally:
            unregister_engine(run.id, self)
            if self._control_task:
                self._control_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._control_task
                self._control_task = None
            self._loop = None
            if self.session:
                await self.session.close_all()

        return run

    async def execute_existing_plan(self, run: AgentRun) -> AgentRun:
        """Execute Phase 2 + 3 for an existing plan_review run.

        Called after the user approves the plan. Re-opens SSH connections and
        runs task execution starting from the saved plan_tasks.
        """
        self._loop = asyncio.get_running_loop()
        current_status = await sync_to_async(
            lambda: AgentRun.objects.filter(pk=run.pk).values("status", "runtime_control").first()
        )()
        if not current_status:
            self.run_record = run
            return run
        if current_status["status"] == AgentRun.STATUS_STOPPED or is_runtime_stop_requested(current_status["runtime_control"]):
            self.run_record = run
            return run
        self.run_record = run
        register_engine(run.id, getattr(self.agent, "id", None), self)
        self._control_task = asyncio.create_task(self._watch_runtime_control())
        await self._sync_runtime_control()
        plan_tasks: list[dict] = list(run.plan_tasks or [])
        orchestrator_log: list[dict] = list(run.orchestrator_log or [])
        primary_server = self.servers[0]
        t0 = time.monotonic()

        self.session = AgentSessionManager(
            allowed_servers=self.servers,
            max_connections=self.agent.max_connections or 5,
            command_timeout=30,
            event_callback=self.event_callback,
        )

        try:
            await self._emit("agent_status", {"status": "connecting"})

            if self.agent.allow_multi_server:
                for srv in self.servers:
                    try:
                        await self.session.open(srv)
                    except Exception as exc:
                        logger.warning("Failed to connect to {}: {}", srv.name, exc)
            else:
                await self.session.open(primary_server)

            if not self.session.connections:
                raise RuntimeError("No servers connected.")

            self.tool_registry = ToolRegistry.from_sources(self.enabled_tools, self.mcp_tools)
            self.ops_prompt_context = await self._build_ops_prompt_context()
            # Mark as running
            await sync_to_async(self._update_run)(run, status=AgentRun.STATUS_RUNNING)
            await self._emit("agent_status", {"status": "running"})
            await self._emit("agent_pipeline_phase", {"phase": "executing", "message": "Выполняю задачи пайплайна…"})

            goal = self.agent.goal or self.agent.ai_prompt or "Analyse the servers."

            # ----------------------------------------------------------------
            # Phase 2: Execute tasks sequentially (with optional replan on failure)
            # ----------------------------------------------------------------
            context_summary = ""
            deadline = time.monotonic() + self.session_timeout
            loop_break = False

            while True:
                for task in plan_tasks:
                    if task.get("status") in ("done", "skipped"):
                        continue
                    if self._stop_requested:
                        task["status"] = "skipped"
                        task["error"] = "Stopped by user"
                        continue

                    await self._pause_event.wait()

                    if time.monotonic() > deadline:
                        task["status"] = "skipped"
                        task["error"] = "Session timeout"
                        continue

                    task["status"] = "running"
                    task["started_at"] = timezone.now().isoformat()
                    await sync_to_async(self._update_run)(run, plan_tasks=plan_tasks)
                    await self._emit("agent_task_start", {"task_id": task["id"], "name": task["name"], "description": task["description"]})

                    try:
                        result, iterations = await self._run_task(task, context_summary, deadline)
                        task["status"] = "done"
                        task["result"] = result
                        task["iterations"] = iterations
                        task["completed_at"] = timezone.now().isoformat()
                        context_summary += f"\n\n### Задача {task['id']}: {task['name']}\nРезультат: {result[:1000]}"
                        await self._emit("agent_task_done", {"task_id": task["id"], "result": result[:500]})

                    except Exception as exc:
                        if self._stop_requested:
                            task["status"] = "skipped"
                            task["error"] = "Stopped by user"
                            task["completed_at"] = timezone.now().isoformat()
                            await sync_to_async(self._update_run)(
                                run,
                                plan_tasks=plan_tasks,
                                orchestrator_log=orchestrator_log,
                            )
                            loop_break = True
                            break

                        task["status"] = "failed"
                        task["error"] = str(exc)
                        task["completed_at"] = timezone.now().isoformat()
                        await self._emit("agent_task_failed", {"task_id": task["id"], "error": str(exc)})

                        decision = await self._handle_failure(task, str(exc), plan_tasks, orchestrator_log)
                        task["orchestrator_decision"] = decision

                        if decision["action"] == "abort":
                            await self._emit("agent_pipeline_phase", {"phase": "aborted", "message": decision.get("reason", "")})
                            loop_break = True
                            break
                        elif decision["action"] == "replan":
                            done_tasks = [t for t in plan_tasks if t["status"] == "done"]
                            new_tasks = await self._replan(goal, plan_tasks, orchestrator_log)
                            for j, nt in enumerate(new_tasks):
                                nt["id"] = len(done_tasks) + j + 1
                            plan_tasks[:] = done_tasks + new_tasks
                            await sync_to_async(self._update_run)(run, plan_tasks=plan_tasks, orchestrator_log=orchestrator_log)
                            await self._emit("agent_plan", {"tasks": plan_tasks})
                            await self._emit("agent_pipeline_phase", {"phase": "executing", "message": "План пересобран. Продолжаю выполнение…"})
                            break
                        elif decision["action"] == "ask_user":
                            question = decision.get("message", "Что делать с ошибкой задачи?")
                            await sync_to_async(self._update_run)(
                                run,
                                status=AgentRun.STATUS_WAITING,
                                pending_question=question,
                                plan_tasks=plan_tasks,
                            )
                            await self._emit("agent_status", {"status": "waiting"})
                            answer = await self._wait_for_user_reply()
                            await sync_to_async(self._update_run)(
                                run, status=AgentRun.STATUS_RUNNING, pending_question="",
                            )
                            context_summary += f"\n\n### Ответ пользователя по задаче {task['id']}\n{answer}"
                            task["result"] = f"Пользователь ответил: {answer}"
                        elif decision["action"] == "retry":
                            retry_deadline = deadline
                            if "Session timeout" in str(exc) or "session timeout" in str(exc).lower():
                                retry_deadline = time.monotonic() + 300
                            try:
                                task["status"] = "running"
                                result, iterations = await self._run_task(task, context_summary, retry_deadline)
                                task["status"] = "done"
                                task["result"] = result
                                task["iterations"] = iterations
                                task["completed_at"] = timezone.now().isoformat()
                                context_summary += f"\n\n### Задача {task['id']}: {task['name']} (повтор)\nРезультат: {result[:1000]}"
                                await self._emit("agent_task_done", {"task_id": task["id"], "result": result[:500]})
                            except Exception as exc2:
                                task["status"] = "failed"
                                task["error"] = f"Retry failed: {exc2}"

                    await sync_to_async(self._update_run)(run, plan_tasks=plan_tasks, orchestrator_log=orchestrator_log)

                if loop_break:
                    break
                if not any(t.get("status") == "pending" for t in plan_tasks):
                    break

            # ----------------------------------------------------------------
            # Phase 3: Synthesize final report
            # ----------------------------------------------------------------
            await self._emit("agent_pipeline_phase", {"phase": "synthesizing", "message": "Generating final report…"})
            final_report = await self._synthesize(goal, plan_tasks, orchestrator_log)
            final_report = await self.hook_manager.run_finished(
                final_report,
                self.permission_engine.verification_summary(),
            )

            final_status = AgentRun.STATUS_COMPLETED
            if self._stop_requested:
                final_status = AgentRun.STATUS_STOPPED
            elif any(t["status"] == "failed" for t in plan_tasks):
                final_status = AgentRun.STATUS_COMPLETED

            run.status = final_status
            run.plan_tasks = plan_tasks
            run.orchestrator_log = orchestrator_log
            run.total_iterations = sum(len(t.get("iterations", [])) for t in plan_tasks)
            run.final_report = final_report
            run.ai_analysis = final_report
            run.completed_at = timezone.now()
            run.duration_ms = int((run.duration_ms or 0) + (time.monotonic() - t0) * 1000)
            await sync_to_async(run.save)()
            await self._persist_ops_summary(
                run=run,
                final_status=final_status,
                final_report=final_report,
                plan_tasks=plan_tasks,
            )

            await sync_to_async(self._touch_agent_last_run)()
            await self._emit("agent_status", {"status": final_status})
            await self._emit("agent_report", {"text": final_report, "interim": False})

        except Exception as exc:
            logger.exception("MultiAgentEngine execute_existing_plan error: {}", exc)
            run.status = AgentRun.STATUS_FAILED
            run.ai_analysis = f"Pipeline failed: {exc}"
            run.plan_tasks = plan_tasks
            run.orchestrator_log = orchestrator_log
            run.completed_at = timezone.now()
            run.duration_ms = int((run.duration_ms or 0) + (time.monotonic() - t0) * 1000)
            await sync_to_async(run.save)()
            await self._persist_ops_summary(
                run=run,
                final_status=run.status,
                final_report=run.ai_analysis,
                plan_tasks=plan_tasks,
            )
            await self._emit("agent_status", {"status": "failed", "error": str(exc)})
        finally:
            unregister_engine(run.id, self)
            if self._control_task:
                self._control_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._control_task
                self._control_task = None
            self._loop = None
            if self.session:
                await self.session.close_all()

        return run

    # ------------------------------------------------------------------
    # Phase 1: Planning
    # ------------------------------------------------------------------

    async def _plan(self, goal: str, orchestrator_log: list) -> list[dict]:
        """Call orchestrator LLM to decompose goal into tasks."""
        connected = self.session.get_connected_info()
        servers_desc = "\n".join(f"- {c['server_name']} (id: {c['server_id']})" for c in connected)
        custom_system = self.agent.system_prompt or ""
        skills_desc = self._skill_provider.build_skill_catalog_description(self.skills) if self._skill_provider else ""
        role_options = "\n".join(
            f"- {slug}: {spec.title}; фокус: {', '.join(spec.focus_areas)}"
            for slug, spec in ROLE_SPECS.items()
            if slug != "custom"
        )
        skill_errors = ""
        if self.skill_errors:
            skill_errors = "\nSkills с ошибками:\n" + "\n".join(f"- {item}" for item in self.skill_errors)

        system_prompt = f"""Ты — мастер-оркестратор DevOps-агентов. Твоя задача — разбить цель на конкретные задачи для исполнительных агентов.
Каждый агент умеет: выполнять SSH-команды, читать файлы, проверять сервисы, анализировать логи.
Отвечай ТОЛЬКО валидным JSON-массивом. Без пояснений до или после JSON.
{self.ops_prompt_context}
{custom_system}

Подключённые серверы:
{servers_desc}

Attached skills:
{skills_desc or "- Skills не подключены"}
{skill_errors}

Правила декомпозиции:
- Максимум {MAX_PLAN_TASKS} задач
- Каждая задача должна быть самодостаточной и конкретной
- Используй русский язык для имён и описаний
- Порядок задач важен — они выполняются последовательно
- Каждая задача должна быть выполнима за 5-7 SSH-команд максимум
- Если attached skills содержат runtime guardrails, учитывай их как обязательные ограничения

Доступные subagent roles:
{role_options}"""

        user_msg = f"""Цель: {goal}

Верни JSON-массив задач в формате:
[
  {{
    "name": "Краткое название задачи",
    "description": "Что именно нужно сделать, какие команды запустить, что проверить",
    "role": "incident_commander|deploy_operator|infra_scout|log_investigator|security_patrol|post_change_verifier|watcher_daemon|custom"
  }},
  ...
]"""

        orchestrator_log.append({"role": "system", "content": system_prompt, "timestamp": timezone.now().isoformat()})
        orchestrator_log.append({"role": "user", "content": user_msg, "timestamp": timezone.now().isoformat()})

        response = await self._call_llm_raw(system_prompt, user_msg)
        orchestrator_log.append({"role": "assistant", "content": response, "timestamp": timezone.now().isoformat()})

        tasks = self._parse_plan(response)
        return self._prepare_plan_tasks(tasks)

    def _prepare_plan_tasks(self, tasks: list[dict]) -> list[dict]:
        prepared_tasks: list[dict] = []
        if self.tool_registry is None:
            return [_make_task(i + 1, t["name"], t["description"]) for i, t in enumerate(tasks)]

        for index, item in enumerate(tasks, start=1):
            subagent = build_task_subagent_spec(
                task_name=item["name"],
                task_description=item["description"],
                parent_agent_type=self.agent.agent_type,
                parent_goal=self.agent.goal or self.agent.ai_prompt,
                tool_registry=self.tool_registry,
                requested_role=item.get("role"),
                requested_tool_names=item.get("tool_names"),
                requested_max_iterations=item.get("max_iterations"),
            )
            task = _make_task(
                index,
                item["name"],
                item["description"],
                role=subagent.role,
                permission_mode=subagent.permission_mode,
                max_iterations=subagent.max_iterations,
                tool_names=list(subagent.tool_names),
            )
            task["subagent"] = {
                "role": subagent.role,
                "title": subagent.title,
                "permission_mode": subagent.permission_mode,
                "tool_names": list(subagent.tool_names),
                "allowed_categories": list(subagent.allowed_categories),
                "max_iterations": subagent.max_iterations,
                "metadata": dict(subagent.metadata),
            }
            prepared_tasks.append(task)
        return prepared_tasks

    def _parse_plan(self, response: str) -> list[dict]:
        """Extract JSON task list from orchestrator response."""
        try:
            # Strip code fences if present
            text = re.sub(r"```(?:json)?\s*", "", response).strip().rstrip("`").strip()
            # Find first [ ... ]
            start = text.find("[")
            end = text.rfind("]")
            if start == -1 or end == -1:
                raise ValueError("No JSON array found")
            raw = text[start : end + 1]
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                # LLM sometimes emits invalid escape sequences (e.g. \u not followed by 4 hex
                # digits, or bare \s, \e, etc.).  Replace them with a literal backslash so the
                # JSON becomes valid, then retry.
                fixed = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r"\\\\", raw)
                data = json.loads(fixed)
            valid = []
            for item in data:
                if isinstance(item, dict) and "name" in item and "description" in item:
                    valid.append({
                        "name": str(item["name"])[:200],
                        "description": str(item["description"])[:500],
                        "role": str(item.get("role") or "").strip(),
                    })
            return valid[:MAX_PLAN_TASKS]
        except Exception as exc:
            logger.warning("Failed to parse orchestrator plan: {}. Response: {!r}", exc, response[:500])
            return [{"name": "Выполнить цель", "description": f"Выполни следующую задачу: {self.agent.goal or self.agent.ai_prompt}", "role": ""}]

    def _build_task_subagent(self, task: dict) -> dict:
        if self.tool_registry is None:
            return {
                "role_spec": self.role_spec,
                "permission_engine": PermissionEngine(mode=self.role_spec.default_permission_mode),
                "tool_registry": ToolRegistry({}),
                "tool_names": [],
                "max_iterations": MAX_TASK_ITERATIONS,
                "title": self.role_spec.title,
                "task": task,
            }

        spec = build_task_subagent_spec(
            task_name=task.get("name", ""),
            task_description=task.get("description", ""),
            parent_agent_type=self.agent.agent_type,
            parent_goal=self.agent.goal or self.agent.ai_prompt,
            tool_registry=self.tool_registry,
            requested_role=task.get("role"),
            requested_tool_names=task.get("tool_names"),
            requested_max_iterations=task.get("max_iterations"),
        )
        role_spec = ROLE_SPECS.get(spec.role, self.role_spec)
        local_registry = self.tool_registry.subset(allowed_names=spec.tool_names)
        return {
            "role_spec": role_spec,
            "permission_engine": PermissionEngine(mode=spec.permission_mode),
            "tool_registry": local_registry,
            "tool_names": list(spec.tool_names),
            "max_iterations": spec.max_iterations,
            "title": spec.title,
            "task": task,
        }

    def _build_subagent_prompt_context(self, task_subagent: dict) -> str:
        local_registry = task_subagent["tool_registry"]
        task = task_subagent.get("task") or {}
        return build_ops_prompt_context(
            role_spec=task_subagent["role_spec"],
            permission_mode=task_subagent["permission_engine"].mode,
            server_memory_prompt=self.server_memory_prompt or "- Память по серверам не загружена",
            operational_recipes_prompt=task.get("operational_recipes_prompt") or self.operational_recipes_prompt,
            tool_registry_prompt=local_registry.build_prompt_slice(limit=8),
            max_iterations=task_subagent["max_iterations"],
            session_timeout=self.session_timeout,
        )

    # ------------------------------------------------------------------
    # Phase 2: Task execution (mini ReAct)
    # ------------------------------------------------------------------

    async def _run_task(self, task: dict, context_summary: str, deadline: float) -> tuple[str, list]:
        """Run a single task with a mini ReAct loop. Returns (result_summary, iterations_list)."""
        task_subagent = self._build_task_subagent(task)
        task_role_spec = task_subagent["role_spec"]
        task_permission_engine: PermissionEngine = task_subagent["permission_engine"]
        task_tool_registry: ToolRegistry = task_subagent["tool_registry"]
        task_tool_names = task_subagent["tool_names"]
        task_max_iterations = task_subagent["max_iterations"]
        task["role"] = task_role_spec.slug
        task["permission_mode"] = task_permission_engine.mode
        task["max_iterations"] = task_max_iterations
        task["tool_names"] = list(task_tool_names)
        if not task.get("operational_recipes_prompt"):
            recipes_query = "\n".join(
                part for part in [task.get("name") or "", task.get("description") or "", *task_role_spec.focus_areas] if part
            )
            group_ids = list(dict.fromkeys([server.group_id for server in self.servers[:3] if getattr(server, "group_id", None)]))
            task["operational_recipes_prompt"] = await self.memory_store.build_operational_recipes_prompt(
                recipes_query,
                server_ids=[server.id for server in self.servers[:3]],
                group_ids=group_ids,
                limit=4,
            )
        task["subagent"] = {
            **(task.get("subagent") or {}),
            "role": task_role_spec.slug,
            "title": task_subagent["title"],
            "permission_mode": task_permission_engine.mode,
            "tool_names": list(task_tool_names),
            "max_iterations": task_max_iterations,
        }

        connected = self.session.get_connected_info()
        servers_desc = "\n".join(f"- {c['server_name']} (id: {c['server_id']})" for c in connected) or "- Нет активных SSH подключений"
        tools_desc = get_tools_description(task_tool_names)
        local_mcp_tools = {name: binding for name, binding in self.mcp_tools.items() if name in task_tool_names}
        mcp_tools_desc = build_mcp_tools_description(local_mcp_tools)
        skills_desc = self._skill_provider.build_skill_catalog_description(self.skills) if self._skill_provider else ""
        if mcp_tools_desc:
            tools_desc = f"{tools_desc}\n\n{mcp_tools_desc}" if tools_desc else mcp_tools_desc
        mcp_errors = ""
        if self.mcp_tool_errors:
            mcp_errors = "\nНедоступные MCP подключения:\n" + "\n".join(f"- {item}" for item in self.mcp_tool_errors)
        skill_errors = ""
        if self.skill_errors:
            skill_errors = "\nНедоступные skills:\n" + "\n".join(f"- {item}" for item in self.skill_errors)

        system_prompt = f"""Ты — subagent роли {task_role_spec.title}, выполняющий одну конкретную задачу внутри orchestrated DevOps pipeline.
Работай только в пределах своей роли, permission mode и выданного tool slice. Отвечай на русском языке.

{self._build_subagent_prompt_context(task_subagent)}

Подключённые серверы:
{servers_desc}

Attached skills:
{skills_desc or "- Skills не подключены"}

Доступные инструменты:
{tools_desc}
{mcp_errors}
{skill_errors}

Формат вывода на каждом шаге:
THOUGHT: <рассуждение>
ACTION: tool_name {{"param1": "val1"}}

Если attached skills релевантны задаче, сначала открой нужный skill через read_skill перед сервис-специфичными изменениями.
Если attached skills содержат runtime guardrails, соблюдай их как обязательные ограничения.
Нельзя вызывать инструменты вне выданного tool slice.

Когда задача выполнена — напиши итоговый вывод БЕЗ строки ACTION.
Если перед этим были изменения, но verification markers не закрыты, ты ОБЯЗАН продолжить выполнение и провести post-change verification.
Максимум {task_max_iterations} итераций."""

        context_block = f"\n\nКонтекст предыдущих задач:\n{context_summary}" if context_summary.strip() else ""
        user_msg = f"Задача: {task['name']}\n{task['description']}{context_block}"

        history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        iterations: list[dict] = []
        final_answer = ""
        await self._emit("agent_subagent_start", {
            "task_id": task["id"],
            "role": task_role_spec.slug,
            "title": task_subagent["title"],
            "permission_mode": task_permission_engine.mode,
            "tool_names": list(task_tool_names),
            "max_iterations": task_max_iterations,
        })

        for iteration in range(1, task_max_iterations + 1):
            if self._stop_requested:
                raise RuntimeError("Stopped by user")
            if time.monotonic() > deadline:
                raise RuntimeError("Session timeout")

            await self._pause_event.wait()

            await self._emit("agent_status", {"status": "thinking", "task_id": task["id"], "iteration": iteration})

            llm_response = await self._call_llm_history(history)
            if not llm_response:
                break

            thought, action_name, action_args = self._parse_response(llm_response)
            task["thought"] = thought  # update current thought for live display

            iter_entry = {
                "iteration": iteration,
                "thought": thought,
                "action": action_name,
                "args": action_args,
                "observation": "",
                "timestamp": timezone.now().isoformat(),
            }

            await self._emit("agent_task_iteration", {
                "task_id": task["id"],
                "iteration": iteration,
                "thought": thought,
                "action": action_name,
                "args": action_args,
            })

            if action_name is None:
                verification_summary = task_permission_engine.verification_summary()
                if task_permission_engine.pending_verifications:
                    iter_entry["observation"] = verification_summary
                    iterations.append(iter_entry)
                    task["verification_summary"] = verification_summary
                    await self._emit("agent_task_iteration", {
                        "task_id": task["id"],
                        "iteration": iteration,
                        "observation": verification_summary[:500],
                    })
                    history.append({"role": "assistant", "content": llm_response})
                    history.append({
                        "role": "user",
                        "content": self.hook_manager.build_observation_message(
                            verification_summary
                            + " Ты не можешь завершить задачу, пока не выполнишь обязательную post-change verification.",
                            limit=4000,
                        ),
                    })
                    continue

                final_answer = thought or llm_response
                iter_entry["observation"] = "(final answer)"
                iterations.append(iter_entry)
                task["verification_summary"] = verification_summary
                history.append({"role": "assistant", "content": llm_response})
                break

            if action_name == "ask_user":
                question = action_args.get("question", "Нужна помощь пользователя")
                if self.run_record:
                    await sync_to_async(self._update_run)(
                        self.run_record,
                        status=AgentRun.STATUS_WAITING,
                        pending_question=question,
                    )
                await self._emit("agent_status", {"status": "waiting"})
                answer = await self._wait_for_user_reply()
                if self.run_record:
                    await sync_to_async(self._update_run)(
                        self.run_record, status=AgentRun.STATUS_RUNNING, pending_question="",
                    )
                observation = f"Пользователь ответил: {answer}"
            else:
                observation = await self._execute_tool(
                    action_name,
                    action_args,
                    permission_engine=task_permission_engine,
                    tool_registry=task_tool_registry,
                    allowed_tool_names=task_tool_names,
                )

            iter_entry["observation"] = observation[:3000]
            iterations.append(iter_entry)

            await self._emit("agent_task_iteration", {
                "task_id": task["id"],
                "iteration": iteration,
                "observation": observation[:500],
            })

            history.append({"role": "assistant", "content": llm_response})
            history.append(
                {
                    "role": "user",
                    "content": self.hook_manager.build_observation_message(observation, limit=4000),
                }
            )

            # Save live iterations to DB
            task["iterations"] = iterations
            if self.run_record:
                plan_tasks_copy = list(self.run_record.plan_tasks or [])
                for pt in plan_tasks_copy:
                    if pt["id"] == task["id"]:
                        pt.update(task)
                        break
                await sync_to_async(self._update_run)(self.run_record, plan_tasks=plan_tasks_copy)

        if not final_answer:
            if task_permission_engine.pending_verifications:
                raise RuntimeError(task_permission_engine.verification_summary())
            # Synthesize from iterations if no explicit final answer
            final_answer = await self._summarize_task(task, iterations)

        task["verification_summary"] = task_permission_engine.verification_summary()
        await self._emit("agent_subagent_done", {
            "task_id": task["id"],
            "role": task_role_spec.slug,
            "verification_summary": task["verification_summary"],
            "pending_verifications": sorted(task_permission_engine.pending_verifications),
        })
        return final_answer, iterations

    async def _summarize_task(self, task: dict, iterations: list[dict]) -> str:
        """Ask LLM to summarize task results if no explicit final answer was given."""
        obs_summary = "\n".join(
            f"Шаг {it['iteration']} ({it.get('action', 'N/A')}): {it.get('observation', '')[:300]}"
            for it in iterations
        )
        prompt = f"""Кратко суммируй результат выполнения задачи.
Задача: {task['name']}
Описание: {task['description']}

Выполненные шаги:
{obs_summary}

Дай краткий вывод (2-4 предложения) о том, что было сделано и каков результат."""
        provider = LLMProvider()
        chunks = []
        with self._audit_scope():
            async for chunk in provider.stream_chat(
                prompt,
                model=self.model_preference,
                specific_model=self.specific_model,
                purpose="opssummary",
            ):
                chunks.append(chunk)
        return "".join(chunks)

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
        """Ask orchestrator LLM what to do after a task failure."""
        done_tasks = [t for t in all_tasks if t["status"] == "done"]
        pending_tasks = [t for t in all_tasks if t["status"] == "pending"]

        system_prompt = """Ты — оркестратор агентного пайплайна. Одна из задач завершилась с ошибкой.
Реши, что делать дальше. Ответь ТОЛЬКО валидным JSON-объектом без пояснений."""

        timeout_hint = ""
        if "Session timeout" in error or "session timeout" in error.lower():
            timeout_hint = (
                "\n\nВажно: при ошибке «Session timeout» лимит времени сессии исчерпан. "
                "Лучше выбрать \"replan\" — перепланировать оставшуюся работу (меньше/проще задач), чтобы уложиться во время и довести цель до конца."
            )

        user_msg = f"""Задача, которая упала: {failed_task['name']}
Описание: {failed_task['description']}
Ошибка: {error}

Уже выполнено задач: {len(done_tasks)}
Осталось задач: {len(pending_tasks)}
{timeout_hint}

Доступные действия:
- "replan"   — перепланировать: составить НОВЫЙ план оставшихся задач с учётом сделанного и ошибок (меньше задач, проще формулировки), чтобы достичь цели
- "retry"    — повторить эту задачу ещё раз
- "skip"     — пропустить и продолжить со следующей задачей
- "ask_user" — спросить пользователя (нужно поле "message" с вопросом)
- "abort"    — прервать весь пайплайн (нужно поле "reason")

Верни JSON:
{{"action": "replan"|"retry"|"skip"|"ask_user"|"abort", "reason": "...", "message": "..."}}"""

        orchestrator_log.append({"role": "user", "content": user_msg, "timestamp": timezone.now().isoformat()})
        response = await self._call_llm_raw(system_prompt, user_msg)
        orchestrator_log.append({"role": "assistant", "content": response, "timestamp": timezone.now().isoformat()})

        return self._parse_decision(response)

    def _parse_decision(self, response: str) -> dict:
        try:
            text = re.sub(r"```(?:json)?\s*", "", response).strip().rstrip("`").strip()
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(text[start:end + 1])
                if "action" in data and data["action"] in ("replan", "retry", "skip", "ask_user", "abort"):
                    return data
        except Exception as exc:
            logger.warning("Failed to parse orchestrator decision: {}", exc)
        return {"action": "skip", "reason": "Could not parse orchestrator decision"}

    async def _replan(self, goal: str, plan_tasks: list[dict], orchestrator_log: list) -> list[dict]:
        """Ask orchestrator to produce a new plan for remaining work (full picture: done, failed, pending)."""
        done_tasks = [t for t in plan_tasks if t["status"] == "done"]
        failed_or_skipped = [t for t in plan_tasks if t["status"] in ("failed", "skipped")]
        pending_tasks = [t for t in plan_tasks if t["status"] == "pending"]

        done_block = "\n".join(
            f"- {t['name']}: { (t.get('result') or '')[:300]}"
            for t in done_tasks
        ) or "(нет)"
        failed_block = "\n".join(
            f"- {t['name']}: ошибка — {t.get('error', '')[:200]}"
            for t in failed_or_skipped
        ) or "(нет)"
        pending_block = "\n".join(
            f"- {t['name']}: {t.get('description', '')[:200]}"
            for t in pending_tasks
        ) or "(нет)"

        system_prompt = """Ты — оркестратор. Нужно перепланировать оставшуюся работу с учётом полной картины.
Учитывай уже выполненное, провалы и ограничения (например нехватка времени). Составь НОВЫЙ короткий план задач, чтобы достичь исходной цели.
Отвечай ТОЛЬКО валидным JSON-массивом задач. Без пояснений до или после JSON."""

        user_msg = f"""Цель пайплайна: {goal}

Уже выполнено (результаты):
{done_block}

Провалено или пропущено (ошибки):
{failed_block}

Не начато по старому плану:
{pending_block}

Составь НОВЫЙ план — только те задачи, которые ОСТАЛОСЬ выполнить для достижения цели. Учитывай сделанное (не дублируй). Для проваленного — упрости или объедини задачи. Сократи число задач (макс. {MAX_PLAN_TASKS}), чтобы уложиться во время. Каждая задача — конкретные команды/шаги.

Формат ответа — JSON-массив:
[
  {{"name": "Краткое название", "description": "Что сделать"}},
  ...
]"""

        orchestrator_log.append({"role": "user", "content": user_msg, "timestamp": timezone.now().isoformat()})
        response = await self._call_llm_raw(system_prompt, user_msg)
        orchestrator_log.append({"role": "assistant", "content": response, "timestamp": timezone.now().isoformat()})

        tasks = self._parse_plan(response)
        return self._prepare_plan_tasks(tasks[:MAX_PLAN_TASKS])

    # ------------------------------------------------------------------
    # Phase 3: Final synthesis
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tasks_table(plan_tasks: list[dict], result_max_len: int = 80) -> str:
        """Формирует Markdown-таблицу «Результаты по задачам» из plan_tasks."""
        def cell(text: str, max_len: int | None = None) -> str:
            s = (text or "").replace("\r", " ").replace("\n", " ").replace("|", ", ").strip()
            if max_len is not None and len(s) > max_len:
                s = s[: max_len - 1].rstrip() + "…"
            return s or "—"

        status_emoji = {"done": "✅", "failed": "❌", "skipped": "⏭️", "running": "⚠️"}
        lines = [
            "| Задача | Статус | Результат |",
            "|--------|--------|-----------|",
        ]
        for task in plan_tasks:
            name = cell(task.get("name", ""), max_len=60)
            emoji = status_emoji.get(task["status"], "❓")
            result_raw = task.get("result", "") or task.get("error", "Нет данных")
            result = cell(result_raw, max_len=result_max_len)
            lines.append(f"| {name} | {emoji} | {result} |")
        return "\n".join(lines)

    @staticmethod
    def _inject_tasks_table_into_report(report: str, tasks_table: str) -> str:
        """Заменяет секцию «Результаты по задачам» в отчёте на готовую таблицу."""
        section_header = "## Результаты по задачам"
        if section_header not in report:
            return report
        start = report.index(section_header)
        # Конец секции — следующий заголовок ## или конец текста
        rest = report[start + len(section_header) :]
        next_h2 = rest.find("\n## ")
        end = start + len(section_header) + next_h2 if next_h2 != -1 else len(report)
        new_section = f"{section_header}\n\n{tasks_table}\n\n"
        return report[:start] + new_section + report[end:].lstrip("\n")

    async def _synthesize(self, goal: str, plan_tasks: list[dict], orchestrator_log: list) -> str:
        """Generate the final consolidated report."""
        task_summaries = []
        for task in plan_tasks:
            status_emoji = {"done": "✅", "failed": "❌", "skipped": "⏭️", "running": "⚠️"}.get(task["status"], "❓")
            result_text = task.get("result", "") or task.get("error", "Нет данных")
            task_summaries.append(f"{status_emoji} **{task['name']}**: {result_text[:400]}")

        tasks_block = "\n\n".join(task_summaries)
        tasks_table = self._build_tasks_table(plan_tasks)

        system_prompt = """Ты — старший технический аналитик. Создай профессиональный деловой отчёт в формате Markdown.
Язык: русский. Стиль: чёткий, структурированный, без воды. Только факты и конкретные данные.

ПРАВИЛА ФОРМАТИРОВАНИЯ:
- В отчёте секция «Результаты по задачам» уже заполнена готовой таблицей — НЕ переписывай и НЕ меняй её.
- Списки — через дефис (-), без лишних отступов.
- Не повторяй одно и то же в разных секциях."""

        user_msg = f"""Создай финальный отчёт по результатам работы агентного пайплайна.

Цель пайплайна: {goal}

Результаты задач (для контекста):
{tasks_block}

Сгенерируй отчёт СТРОГО в следующем формате. Секцию «Результаты по задачам» оформи ТОЧНО так (скопируй таблицу как есть):

# [Название — кратко суть результата]

> [Одно предложение — главный итог пайплайна]

## Итог

[3–4 предложения: общий результат, статус системы, ключевые выводы]

## Результаты по задачам

{tasks_table}

## Ключевые находки

- **[Категория]:** [Факт с конкретными данными — цифры, имена, версии]
- **[Категория]:** [...]

## Проблемы и риски

- [Проблема — что обнаружено и почему важно]
- [Если критических проблем нет — написать: Критических проблем не обнаружено]

## Рекомендации

1. [Конкретное действие — что именно сделать]
2. [Следующий шаг]

---

**Статус пайплайна:** ✅ Успех / ⚠️ Частичный успех / ❌ Ошибка"""

        orchestrator_log.append({"role": "user", "content": user_msg, "timestamp": timezone.now().isoformat()})
        provider = LLMProvider()
        chunks = []
        try:
            with self._audit_scope():
                async for chunk in provider.stream_chat(
                    f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_msg}",
                    model=self.model_preference,
                    specific_model=self.specific_model,
                    purpose="opssummary",
                ):
                    chunks.append(chunk)
                    if chunks and len(chunks) % 20 == 0:
                        await self._emit("agent_report", {"text": "".join(chunks), "interim": True})
            result = "".join(chunks)
            orchestrator_log.append({"role": "assistant", "content": result, "timestamp": timezone.now().isoformat()})
            # Подставляем гарантированно корректную таблицу «Результаты по задачам»
            result = self._inject_tasks_table_into_report(result, tasks_table)
            return result
        except Exception as exc:
            logger.error("Synthesis failed: {}", exc)
            fallback = f"# Отчёт пайплайна\n\n## Результаты по задачам\n\n{tasks_table}\n\n*Ошибка генерации финального отчёта: {exc}*"
            return fallback

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    async def _call_llm_raw(self, system_prompt: str, user_msg: str) -> str:
        """Call LLM with explicit system/user messages. Raises on failure."""
        prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_msg}"
        provider = LLMProvider()
        chunks = []
        try:
            with self._audit_scope():
                async for chunk in provider.stream_chat(
                    prompt,
                    model=self.model_preference,
                    specific_model=self.specific_model,
                    purpose="opsplan",
                ):
                    chunks.append(chunk)
        except Exception as exc:
            logger.error("Orchestrator LLM call failed: {}", exc)
            raise
        return "".join(chunks)

    async def _call_llm_history(self, history: list[dict]) -> str:
        """Call LLM with a history list. Raises on failure."""
        parts = []
        for msg in history:
            role = msg["role"].upper()
            parts.append(f"[{role}]\n{msg['content']}")
        prompt = "\n\n".join(parts)
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
                    chunks.append(chunk)
        except Exception as exc:
            logger.error("Task LLM call failed: {}", exc)
            raise
        return "".join(chunks)

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
        active_registry = tool_registry or self.tool_registry
        active_permission_engine = permission_engine or self.permission_engine
        if allowed_tool_names is not None and name not in allowed_tool_names:
            return f"Tool '{name}' is not available to this subagent."
        spec = active_registry.get(name) if active_registry else None
        if active_registry is not None and spec is None:
            return f"Tool '{name}' is not available in the current tool slice."
        decision = active_permission_engine.evaluate(spec, args) if spec else None
        if decision and not decision.allowed:
            return decision.reason
        if decision and spec:
            sandbox_decision = self.sandbox_manager.validate(spec, args, decision.sandbox_profile)
            if not sandbox_decision.allowed:
                return sandbox_decision.reason
        if name in self.mcp_tools:
            binding = self.mcp_tools[name]
            if self._skill_provider is not None:
                prepared_args, policy_messages, policy_error = self._skill_provider.apply_skill_policies(
                    self.skill_policies, binding, args, self._executed_mcp_tools
                )
            else:
                prepared_args, policy_messages, policy_error = args, [], None
            if policy_error:
                return policy_error
            result = await execute_bound_mcp_tool(self.mcp_tools, name, prepared_args)
            if not result.startswith("MCP tool error"):
                self._executed_mcp_tools.add(binding.tool_name)
                if spec:
                    active_permission_engine.record_success(spec, prepared_args, result)
            if policy_messages:
                result = "\n".join([*policy_messages, result])
            if decision and decision.notes:
                result = "\n".join([*decision.notes, result])
            return await self.hook_manager.post_tool_use(name, result)
        if name in self.disabled_mcp_tools:
            return f"Tool '{name}' is disabled for this agent."

        from servers.agent_tools import AGENT_TOOLS
        tool_meta = AGENT_TOOLS.get(name)
        if tool_meta is None:
            return f"Unknown tool: {name}"
        if name not in self.enabled_tools:
            return f"Tool '{name}' is disabled for this agent."
        fn = tool_meta["fn"]
        try:
            result = await fn(self.session, **args)
            result_text = result.result
            if spec and result.success:
                active_permission_engine.record_success(spec, args, result_text)
            if decision and decision.notes:
                result_text = "\n".join([*decision.notes, result_text])
            return await self.hook_manager.post_tool_use(name, result_text)
        except Exception as exc:
            return await self.hook_manager.post_tool_use(name, f"Tool error ({name}): {exc}")

    async def _build_ops_prompt_context(self) -> str:
        cards = []
        server_ids: list[int] = []
        group_ids: list[int] = []
        for server in self.servers[:3]:
            server_ids.append(server.id)
            if getattr(server, "group_id", None):
                group_ids.append(server.group_id)
            try:
                cards.append(await self.memory_store.get_server_card(server.id))
            except Exception as exc:
                logger.debug("Failed to load memory card for server {}: {}", getattr(server, "id", "?"), exc)
        server_memory_prompt = render_server_cards_prompt(cards, max_cards=3, max_records=6)
        self.server_memory_prompt = server_memory_prompt
        recipes_query = "\n".join(
            part for part in [self.agent.goal or self.agent.ai_prompt or "", *self.role_spec.focus_areas] if part
        )
        self.operational_recipes_prompt = await self.memory_store.build_operational_recipes_prompt(
            recipes_query,
            server_ids=server_ids,
            group_ids=list(dict.fromkeys(group_ids)),
            limit=5,
        )
        tool_registry_prompt = self.tool_registry.build_prompt_slice(limit=10) if self.tool_registry else ""
        return build_ops_prompt_context(
            role_spec=self.role_spec,
            permission_mode=self.permission_engine.mode,
            server_memory_prompt=server_memory_prompt,
            operational_recipes_prompt=self.operational_recipes_prompt,
            tool_registry_prompt=tool_registry_prompt,
            max_iterations=MAX_TASK_ITERATIONS,
            session_timeout=self.session_timeout,
        )

    async def _persist_ops_summary(
        self,
        *,
        run: AgentRun,
        final_status: str,
        final_report: str,
        plan_tasks: list[dict],
    ):
        if not getattr(run, "pk", None):
            return
        flat_iterations = []
        for task in plan_tasks:
            for item in task.get("iterations", [])[-2:]:
                flat_iterations.append(item)
        tool_calls = [
            {"tool": item.get("action"), "result": item.get("observation", "")}
            for item in flat_iterations
            if item.get("action")
        ]
        payload = build_run_summary_payload(
            run=run,
            role_slug=self.role_spec.slug,
            final_status=final_status,
            final_report=final_report,
            iterations=flat_iterations,
            tool_calls=tool_calls,
            verification_summary=self.permission_engine.verification_summary(),
        )
        await self.memory_store.append_run_summary(run.pk, payload)

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
