"""
Full ReAct agent engine.

Implements the Reason-Act-Observe loop for autonomous server management.
Connects to servers via SSH, executes tools, and streams events to the
WebSocket live monitor via a callback.
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
from servers.agent_tools import AGENT_TOOLS, get_enabled_tools, get_tools_description
from servers.mcp_tool_runtime import build_mcp_tools_description, execute_bound_mcp_tool, load_mcp_tool_bindings
from servers.models import AgentRun, Server, ServerAgent
from studio.skill_policy import apply_skill_policies, compile_skill_policies
from studio.skill_registry import SkillDefinition, build_skill_catalog_description


def sync_to_async(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


_ACTION_NAME_RE = re.compile(r"ACTION:\s*([A-Za-z0-9_]+)\s*", re.DOTALL)
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

SESSION_TIMEOUT_DEFAULT = 600
MAX_ITERATIONS_CAP = 100
CONTROL_POLL_INTERVAL = 0.5


class AgentEngine:
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
        skills: list[SkillDefinition] | None = None,
        skill_errors: list[str] | None = None,
    ):
        self.agent = agent
        self.servers = servers
        self.user = user
        self.event_callback = event_callback

        self.max_iterations = min(agent.max_iterations or 20, MAX_ITERATIONS_CAP)
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

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    async def run(self, run_record: AgentRun | None = None) -> AgentRun:
        self._loop = asyncio.get_running_loop()
        primary_server = self.servers[0] if self.servers else None
        if run_record is None:
            run = await sync_to_async(AgentRun.objects.create)(
                agent=self.agent if self.agent.pk else None,
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
                agent=self.agent if self.agent.pk else None,
                server=primary_server,
                user=self.user,
                status=AgentRun.STATUS_RUNNING,
                ai_analysis="",
                commands_output=[],
                duration_ms=0,
                completed_at=None,
                iterations_log=[],
                tool_calls=[],
                total_iterations=0,
                connected_servers=[],
                runtime_control=reset_runtime_control_state(),
                pending_question="",
                final_report="",
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

        iterations_log: list[dict] = []
        tool_calls_log: list[dict] = []
        history: list[dict[str, str]] = []

        try:
            logger.info(
                "agent_run {} start: agent='{}' servers={} mcp_servers={} skills={} provider={} model={}",
                run.pk,
                self.agent.name,
                [srv.name for srv in self.servers],
                [srv.name for srv in self.mcp_servers],
                [skill.slug for skill in self.skills],
                self.model_preference,
                self.specific_model,
            )
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
            logger.info(
                "agent_run {} mcp bindings loaded: tools={} errors={}",
                run.pk,
                sorted(self.mcp_tools.keys()),
                self.mcp_tool_errors,
            )

            connected = self.session.get_connected_info()
            await sync_to_async(self._update_run)(run, connected_servers=[
                {"server_id": c["server_id"], "server_name": c["server_name"]}
                for c in connected
            ])

            if not self.session.connections and not self.mcp_tools and not self.skills:
                raise RuntimeError("No servers connected, no MCP tools available, and no skills attached.")

            system_prompt = self._build_system_prompt()
            history.append({"role": "system", "content": system_prompt})

            goal = self.agent.goal or self.agent.ai_prompt or "Analyze the servers."
            history.append({"role": "user", "content": f"Goal: {goal}"})

            await self._emit("agent_status", {"status": "thinking", "iteration": 0})

            iteration = 0
            deadline = time.monotonic() + self.session_timeout

            while iteration < self.max_iterations:
                if self._stop_requested:
                    await self._emit("agent_status", {"status": "stopped"})
                    break

                await self._pause_event.wait()

                if time.monotonic() > deadline:
                    await self._emit("agent_status", {"status": "timeout"})
                    break

                iteration += 1
                logger.info("agent_run {} iteration {} start", run.pk, iteration)
                await self._emit("agent_status", {"status": "thinking", "iteration": iteration})

                llm_response = await self._call_llm(history)
                if not llm_response:
                    logger.warning("agent_run {} iteration {} got empty llm response", run.pk, iteration)
                    break

                thought, action_name, action_args = self._parse_response(llm_response)
                logger.info(
                    "agent_run {} iteration {} parsed action: action={} args={} thought={}",
                    run.pk,
                    iteration,
                    action_name,
                    json.dumps(action_args, ensure_ascii=False)[:800],
                    (thought or "")[:300],
                )

                iter_entry = {
                    "iteration": iteration,
                    "thought": thought,
                    "action": action_name,
                    "args": action_args,
                    "observation": "",
                    "timestamp": timezone.now().isoformat(),
                }

                await self._emit("agent_thought", {"iteration": iteration, "thought": thought})

                if action_name is None:
                    logger.info("agent_run {} iteration {} completed with final answer", run.pk, iteration)
                    iter_entry["observation"] = "(final answer)"
                    iterations_log.append(iter_entry)
                    history.append({"role": "assistant", "content": llm_response})
                    break

                await self._emit("agent_action", {
                    "iteration": iteration,
                    "tool": action_name,
                    "args": action_args,
                })

                if action_name == "ask_user":
                    await sync_to_async(self._update_run)(
                        run, status=AgentRun.STATUS_WAITING,
                        pending_question=action_args.get("question", ""),
                    )

                observation = await self._execute_tool(action_name, action_args)
                logger.info(
                    "agent_run {} iteration {} tool result: tool={} chars={}",
                    run.pk,
                    iteration,
                    action_name,
                    len(observation or ""),
                )

                if action_name == "ask_user":
                    await sync_to_async(self._update_run)(
                        run, status=AgentRun.STATUS_RUNNING, pending_question="",
                    )

                tool_calls_log.append({
                    "tool": action_name,
                    "args": action_args,
                    "result": observation[:2000],
                    "duration_ms": 0,
                    "timestamp": timezone.now().isoformat(),
                })

                iter_entry["observation"] = observation[:3000]
                iterations_log.append(iter_entry)

                await self._emit("agent_observation", {
                    "iteration": iteration,
                    "tool": action_name,
                    "observation": observation[:1000],
                })

                history.append({"role": "assistant", "content": llm_response})
                history.append({"role": "user", "content": f"OBSERVATION: {observation[:4000]}"})

            final_status = AgentRun.STATUS_COMPLETED
            if self._stop_requested:
                final_status = AgentRun.STATUS_STOPPED
            elif time.monotonic() > deadline:
                final_status = AgentRun.STATUS_FAILED

            logger.info(
                "agent_run {} generating final report: final_status={} iterations={}",
                run.pk,
                final_status,
                iteration,
            )
            final_report = await self._generate_final_report(history, iterations_log)

            run.status = final_status
            run.iterations_log = iterations_log
            run.tool_calls = tool_calls_log
            run.total_iterations = iteration
            run.final_report = final_report
            run.ai_analysis = final_report
            run.completed_at = timezone.now()
            run.duration_ms = int((time.monotonic() - t0) * 1000)
            await sync_to_async(run.save)()
            logger.info(
                "agent_run {} saved: status={} duration_ms={} report_chars={}",
                run.pk,
                run.status,
                run.duration_ms,
                len(final_report or ""),
            )

            await sync_to_async(self._touch_agent_last_run)()

            await self._emit("agent_status", {"status": final_status})
            await self._emit("agent_report", {"text": final_report, "interim": False})

        except Exception as exc:
            logger.error("Agent engine error: {}", exc)
            run.status = AgentRun.STATUS_FAILED
            run.ai_analysis = f"Agent failed: {exc}"
            run.iterations_log = iterations_log
            run.tool_calls = tool_calls_log
            run.total_iterations = len(iterations_log)
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
    # LLM interaction
    # ------------------------------------------------------------------

    async def _call_llm(self, history: list[dict]) -> str:
        prompt = self._history_to_prompt(history)
        provider = LLMProvider()
        chunks = []
        try:
            with self._audit_scope():
                async for chunk in provider.stream_chat(
                    prompt,
                    model=self.model_preference,
                    specific_model=self.specific_model,
                    purpose="agent",
                ):
                    chunks.append(chunk)
        except Exception as exc:
            logger.error("LLM call failed: {}", exc)
            return ""
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
        logger.info("agent_run {} execute_tool start: tool={} args={}", self.run_record.pk if self.run_record else "?", name, json.dumps(args, ensure_ascii=False)[:800])
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
                result = "\n".join([*policy_messages, result])
            logger.info(
                "agent_run {} execute_tool done: tool={} result_chars={} via=mcp",
                self.run_record.pk if self.run_record else "?",
                name,
                len(result or ""),
            )
            return result
        if name in self.disabled_mcp_tools:
            return f"Tool '{name}' is disabled for this agent."

        tool_meta = AGENT_TOOLS.get(name)
        if tool_meta is None:
            return f"Unknown tool: {name}"
        if name not in self.enabled_tools:
            return f"Tool '{name}' is disabled for this agent."

        fn = tool_meta["fn"]
        try:
            result = await fn(self.session, **args)
            logger.info(
                "agent_run {} execute_tool done: tool={} result_chars={} via=agent_tool",
                self.run_record.pk if self.run_record else "?",
                name,
                len(result.result or ""),
            )
            return result.result
        except Exception as exc:
            logger.exception(
                "agent_run {} execute_tool failed: tool={}",
                self.run_record.pk if self.run_record else "?",
                name,
            )
            return f"Tool error ({name}): {exc}"

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        connected = self.session.get_connected_info()
        servers_desc = "\n".join(f"- {c['server_name']} (id: {c['server_id']})" for c in connected) or "- Нет активных SSH подключений"
        all_servers_desc = (
            "\n".join(f"- {s.name} (id: {s.id}, host: {s.host})" for s in self.servers) or "- SSH серверы не выбраны"
        )

        custom_system = self.agent.system_prompt or ""
        tools_desc = get_tools_description(self.enabled_tools)
        mcp_tools_desc = build_mcp_tools_description(self.mcp_tools)
        skills_desc = build_skill_catalog_description(self.skills)
        if mcp_tools_desc:
            tools_desc = f"{tools_desc}\n\n{mcp_tools_desc}" if tools_desc else mcp_tools_desc

        stop_conditions = ""
        if self.agent.stop_conditions:
            stop_conditions = "\nStop conditions:\n" + "\n".join(
                f"- {c}" for c in self.agent.stop_conditions
            )

        mcp_errors = ""
        if self.mcp_tool_errors:
            mcp_errors = "\n## MCP подключения с ошибками\n" + "\n".join(f"- {item}" for item in self.mcp_tool_errors)

        skill_errors = ""
        if self.skill_errors:
            skill_errors = "\n## Skills с ошибками\n" + "\n".join(f"- {item}" for item in self.skill_errors)

        tool_rules = [
            "- ВСЕГДА сначала выводи THOUGHT с объяснением логики рассуждений",
            "- Затем выводи ACTION с вызовом инструмента в формате JSON",
            "- После каждой команды анализируй вывод и решай, что делать дальше",
            "- Для внешних систем (Keycloak, GitHub, Docker API, cloud, IAM) используй MCP-инструменты, если они доступны",
            "- Имена MCP-инструментов нужно использовать ТОЧНО как перечислено в секции инструментов",
            "- Если подключены skills, сначала ориентируйся по их каталогу и открывай полный skill через read_skill перед сервис-специфичными изменениями",
            "- Некоторые skills дополнительно применяют runtime guardrails к MCP-вызовам: могут подставлять обязательные аргументы и блокировать опасные действия",
            "- НЕ запускай опасные команды (rm -rf, mkfs, shutdown и т.д.) — они будут заблокированы",
            "- Когда цель полностью достигнута, предоставь итоговый анализ БЕЗ строки ACTION",
            f"- Максимум {self.max_iterations} итераций доступно",
        ]
        if "send_ctrl_c" in self.enabled_tools:
            tool_rules.append("- Если команда выполняется слишком долго (>30с), используй send_ctrl_c для прерывания")
        if "read_console" in self.enabled_tools:
            tool_rules.append("- Используй read_console для проверки текущего состояния терминала, если не уверен")
        if "ask_user" in self.enabled_tools:
            tool_rules.append("- Используй ask_user только когда действительно нужен ввод человека для критического решения")
        if "report" in self.enabled_tools:
            tool_rules.append("- Используй report для отправки промежуточного отчёта пользователю при длительных задачах")
        rules_text = "\n".join(tool_rules)

        return f"""Ты — DevOps / Platform AI-агент, работающий через SSH и MCP-инструменты.
У тебя есть доступ к терминалам серверов и внешним системам, подключённым через MCP.
Всегда отвечай, рассуждай и пиши отчёты на русском языке.

{custom_system}

## Подключённые серверы
{servers_desc}

## Все доступные серверы (можно подключиться через open_connection)
{all_servers_desc}

## Attached skills
{skills_desc or "- Skills не подключены"}

## Доступные инструменты
{tools_desc}

## Правила
{rules_text}
{stop_conditions}
{mcp_errors}
{skill_errors}

## Формат вывода
THOUGHT: <твоё рассуждение о том, что делать дальше>
ACTION: tool_name {{"param1": "value1", "param2": "value2"}}

Когда задача завершена (больше нет действий), выведи итоговый анализ БЕЗ строки ACTION."""

    # ------------------------------------------------------------------
    # Final report
    # ------------------------------------------------------------------

    async def _generate_final_report(self, history: list[dict], iterations: list[dict]) -> str:
        summary_parts = []
        for it in iterations:
            if it.get("action"):
                summary_parts.append(f"Step {it['iteration']}: {it['action']}({json.dumps(it.get('args', {}), ensure_ascii=False)[:100]}) → {it['observation'][:200]}")
            else:
                summary_parts.append(f"Step {it['iteration']}: Final answer")

        steps_summary = "\n".join(summary_parts[-20:])

        prompt = f"""Ты — технический аналитик. Создай профессиональный структурированный отчёт в формате Markdown.
Язык: русский. Стиль: деловой, конкретный, без воды.

Данные для отчёта:
- Агент: {self.agent.name}
- Цель: {self.agent.goal or self.agent.ai_prompt or 'Не указана'}
- Итераций выполнено: {len(iterations)}
- Шаги агента: {steps_summary}
- Итоговый ответ агента: {history[-1]['content'][:3000] if history else 'Нет данных'}

Сгенерируй отчёт СТРОГО в следующем формате — не добавляй лишних секций, не меняй структуру:

# [Краткое название того что было сделано]

> [Одно предложение — главный итог работы агента]

## Результат

[2–4 предложения об общем результате и текущем состоянии системы]

## Выполненные действия

- [Действие 1 — конкретно что сделано и что получено]
- [Действие 2]
- [...]

## Ключевые находки

- [Находка 1 — факт с конкретными данными: цифры, названия, пути]
- [Находка 2]
- [...]

## Рекомендации

- [Рекомендация 1 — конкретное действие]
- [Рекомендация 2]

---

**Статус:** ✅ Успех / ⚠️ Частичный успех / ❌ Ошибка"""

        provider = LLMProvider()
        chunks = []
        try:
            logger.info(
                "agent_run {} final report llm start: iterations={}",
                self.run_record.pk if self.run_record else "?",
                len(iterations),
            )
            async for chunk in provider.stream_chat(
                prompt,
                model=self.model_preference,
                specific_model=self.specific_model,
                purpose="agent",
            ):
                chunks.append(chunk)
            report = "".join(chunks)
            logger.info(
                "agent_run {} final report llm done: chars={}",
                self.run_record.pk if self.run_record else "?",
                len(report),
            )
            return report
        except Exception as exc:
            logger.error("Final report generation failed: {}", exc)
            return f"Report generation failed: {exc}\n\nRaw steps:\n{steps_summary}"

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
