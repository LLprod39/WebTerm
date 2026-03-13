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
from studio.skill_policy import apply_skill_policies, compile_skill_policies
from studio.skill_registry import SkillDefinition, build_skill_catalog_description


def sync_to_async(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


_ACTION_NAME_RE = re.compile(r"ACTION:\s*([\w_]+)\s*", re.DOTALL)
_THOUGHT_RE = re.compile(r"THOUGHT:\s*(.+?)(?=ACTION:|$)", re.DOTALL)


def _parse_action(response: str) -> tuple[str | None, dict]:
    """Надёжный парсинг ACTION: tool_name {...}.

    Использует json.JSONDecoder.raw_decode вместо regex {.*?},
    чтобы корректно обрабатывать многострочные JSON-объекты с отступами.
    """
    name_match = _ACTION_NAME_RE.search(response)
    if not name_match:
        return None, {}

    action_name = name_match.group(1).strip()
    json_start = name_match.end()

    # Пропускаем пробелы до '{'
    while json_start < len(response) and response[json_start] in " \t\n\r":
        json_start += 1

    if json_start >= len(response) or response[json_start] != "{":
        return action_name, {}

    try:
        decoder = json.JSONDecoder()
        action_args, _ = decoder.raw_decode(response, json_start)
        if isinstance(action_args, dict):
            return action_name, action_args
    except json.JSONDecodeError:
        pass

    return action_name, {}

MAX_PLAN_TASKS = 15
MAX_TASK_ITERATIONS = 7
SESSION_TIMEOUT_DEFAULT = 900
CONTROL_POLL_INTERVAL = 0.5


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _make_task(task_id: int, name: str, description: str) -> dict:
    return {
        "id": task_id,
        "name": name,
        "description": description,
        "status": "pending",
        "thought": "",
        "iterations": [],
        "result": "",
        "error": "",
        "orchestrator_decision": None,
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
        skills: list[SkillDefinition] | None = None,
        skill_errors: list[str] | None = None,
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
        self.skill_policies, policy_errors = compile_skill_policies(self.skills)
        self.skill_policy_errors = list(policy_errors)
        if self.skill_policy_errors:
            self.skill_errors.extend(self.skill_policy_errors)
        self._executed_mcp_tools: set[str] = set()
        self.model_preference, self.specific_model = resolve_provider_and_model(
            model_preference,
            specific_model,
            default_provider="auto",
        )
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
                try:
                    await self.session.send_signal(server_id, "ctrl_c")
                except Exception:
                    pass
            try:
                await self.session.close_all()
            except Exception:
                pass

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
        skills_desc = build_skill_catalog_description(self.skills)
        skill_errors = ""
        if self.skill_errors:
            skill_errors = "\nSkills с ошибками:\n" + "\n".join(f"- {item}" for item in self.skill_errors)

        system_prompt = f"""Ты — мастер-оркестратор DevOps-агентов. Твоя задача — разбить цель на конкретные задачи для исполнительных агентов.
Каждый агент умеет: выполнять SSH-команды, читать файлы, проверять сервисы, анализировать логи.
Отвечай ТОЛЬКО валидным JSON-массивом. Без пояснений до или после JSON.
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
- Если attached skills содержат runtime guardrails, учитывай их как обязательные ограничения"""

        user_msg = f"""Цель: {goal}

Верни JSON-массив задач в формате:
[
  {{
    "name": "Краткое название задачи",
    "description": "Что именно нужно сделать, какие команды запустить, что проверить"
  }},
  ...
]"""

        orchestrator_log.append({"role": "system", "content": system_prompt, "timestamp": timezone.now().isoformat()})
        orchestrator_log.append({"role": "user", "content": user_msg, "timestamp": timezone.now().isoformat()})

        response = await self._call_llm_raw(system_prompt, user_msg)
        orchestrator_log.append({"role": "assistant", "content": response, "timestamp": timezone.now().isoformat()})

        tasks = self._parse_plan(response)
        return [_make_task(i + 1, t["name"], t["description"]) for i, t in enumerate(tasks)]

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
                    valid.append({"name": str(item["name"])[:200], "description": str(item["description"])[:500]})
            return valid[:MAX_PLAN_TASKS]
        except Exception as exc:
            logger.warning("Failed to parse orchestrator plan: {}. Response: {!r}", exc, response[:500])
            return [{"name": "Выполнить цель", "description": f"Выполни следующую задачу: {self.agent.goal or self.agent.ai_prompt}"}]

    # ------------------------------------------------------------------
    # Phase 2: Task execution (mini ReAct)
    # ------------------------------------------------------------------

    async def _run_task(self, task: dict, context_summary: str, deadline: float) -> tuple[str, list]:
        """Run a single task with a mini ReAct loop. Returns (result_summary, iterations_list)."""
        connected = self.session.get_connected_info()
        servers_desc = "\n".join(f"- {c['server_name']} (id: {c['server_id']})" for c in connected) or "- Нет активных SSH подключений"
        tools_desc = get_tools_description(self.enabled_tools)
        mcp_tools_desc = build_mcp_tools_description(self.mcp_tools)
        skills_desc = build_skill_catalog_description(self.skills)
        if mcp_tools_desc:
            tools_desc = f"{tools_desc}\n\n{mcp_tools_desc}" if tools_desc else mcp_tools_desc
        mcp_errors = ""
        if self.mcp_tool_errors:
            mcp_errors = "\nНедоступные MCP подключения:\n" + "\n".join(f"- {item}" for item in self.mcp_tool_errors)
        skill_errors = ""
        if self.skill_errors:
            skill_errors = "\nНедоступные skills:\n" + "\n".join(f"- {item}" for item in self.skill_errors)

        system_prompt = f"""Ты — DevOps / Platform агент, выполняющий одну конкретную задачу.
Используй доступные SSH и MCP инструменты для выполнения задачи. Отвечай на русском языке.

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

Когда задача выполнена — напиши итоговый вывод БЕЗ строки ACTION.
Максимум {MAX_TASK_ITERATIONS} итераций."""

        context_block = f"\n\nКонтекст предыдущих задач:\n{context_summary}" if context_summary.strip() else ""
        user_msg = f"Задача: {task['name']}\n{task['description']}{context_block}"

        history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]

        iterations: list[dict] = []
        final_answer = ""

        for iteration in range(1, MAX_TASK_ITERATIONS + 1):
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
                # Final answer — no action
                final_answer = thought or llm_response
                iter_entry["observation"] = "(final answer)"
                iterations.append(iter_entry)
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
                observation = await self._execute_tool(action_name, action_args)

            iter_entry["observation"] = observation[:3000]
            iterations.append(iter_entry)

            await self._emit("agent_task_iteration", {
                "task_id": task["id"],
                "iteration": iteration,
                "observation": observation[:500],
            })

            history.append({"role": "assistant", "content": llm_response})
            history.append({"role": "user", "content": f"OBSERVATION: {observation[:4000]}"})

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
            # Synthesize from iterations if no explicit final answer
            final_answer = await self._summarize_task(task, iterations)

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
                purpose="agent",
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
        return [_make_task(i + 1, t["name"], t["description"]) for i, t in enumerate(tasks[:MAX_PLAN_TASKS])]

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
                    purpose="orchestrator",
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
        """Call LLM with explicit system/user messages."""
        prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_msg}"
        provider = LLMProvider()
        chunks = []
        try:
            with self._audit_scope():
                async for chunk in provider.stream_chat(
                    prompt,
                    model=self.model_preference,
                    specific_model=self.specific_model,
                    purpose="orchestrator",
                ):
                    chunks.append(chunk)
        except Exception as exc:
            logger.error("Orchestrator LLM call failed: {}", exc)
            return ""
        return "".join(chunks)

    async def _call_llm_history(self, history: list[dict]) -> str:
        """Call LLM with a history list."""
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
                    purpose="orchestrator",
                ):
                    chunks.append(chunk)
        except Exception as exc:
            logger.error("Task LLM call failed: {}", exc)
            return ""
        return "".join(chunks)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(response: str) -> tuple[str, str | None, dict]:
        thought = ""
        thought_match = _THOUGHT_RE.search(response)
        if thought_match:
            thought = thought_match.group(1).strip()
        else:
            thought = response.split("ACTION:")[0].strip() if "ACTION:" in response else response.strip()

        action_name, action_args = _parse_action(response)
        if action_name is not None:
            return thought, action_name, action_args

        return thought, None, {}

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def _execute_tool(self, name: str, args: dict) -> str:
        if name in self.mcp_tools:
            binding = self.mcp_tools[name]
            prepared_args, policy_messages, policy_error = apply_skill_policies(
                self.skill_policies,
                binding,
                args,
                self._executed_mcp_tools,
            )
            if policy_error:
                return policy_error
            result = await execute_bound_mcp_tool(self.mcp_tools, name, prepared_args)
            if not result.startswith("MCP tool error"):
                self._executed_mcp_tools.add(binding.tool_name)
            if policy_messages:
                return "\n".join([*policy_messages, result])
            return result
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
            return result.result
        except Exception as exc:
            return f"Tool error ({name}): {exc}"

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
        if reply_nonce > reply_ack_nonce and control["reply_text"]:
            if self.provide_user_reply(control["reply_text"]):
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
