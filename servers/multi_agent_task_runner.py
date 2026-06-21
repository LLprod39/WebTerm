from __future__ import annotations

import time
from typing import Any

from asgiref.sync import sync_to_async as _s2a

from app.core.llm import LLMProvider
from servers.models import AgentRun
from servers.multi_agent_task_iterations import (
    append_observation_history,
    append_verification_blocked_history,
    build_iteration_thought_event,
    build_task_iteration_entry,
    merge_task_update_into_plan_tasks,
    record_final_answer_iteration,
    record_observed_iteration,
    record_verification_blocked_iteration,
)
from servers.multi_agent_task_prompts import build_multi_agent_task_prompt
from servers.multi_agent_task_setup import prepare_multi_agent_task_runtime


def sync_to_async(func, thread_sensitive=False):
    return _s2a(func, thread_sensitive=thread_sensitive)


async def run_multi_agent_task(engine: Any, task: dict, context_summary: str, deadline: float) -> tuple[str, list]:
    """Run a single task with a mini ReAct loop."""
    task_subagent = engine._build_task_subagent(task)
    task_runtime = await prepare_multi_agent_task_runtime(
        task,
        task_subagent,
        memory_store=engine.memory_store,
        servers=engine.servers,
    )
    task_role_spec = task_runtime.role_spec
    task_permission_engine = task_runtime.permission_engine
    task_tool_registry = task_runtime.tool_registry
    task_tool_names = task_runtime.tool_names
    task_max_iterations = task_runtime.max_iterations

    prompt = build_multi_agent_task_prompt(
        task=task,
        role_spec=task_role_spec,
        subagent_prompt_context=engine._build_subagent_prompt_context(task_subagent),
        agent_input_artifacts=engine.agent.input_artifacts,
        connected_servers=engine.session.get_connected_info(),
        tool_names=task_tool_names,
        mcp_runtime_provider=engine._mcp_runtime_provider,
        mcp_tools=engine.mcp_tools,
        skill_provider=engine._skill_provider,
        skills=engine.skills,
        mcp_tool_errors=engine.mcp_tool_errors,
        skill_errors=engine.skill_errors,
        sudo_policy=task_permission_engine.sudo_policy,
        max_iterations=task_max_iterations,
        context_summary=context_summary,
    )
    history = prompt.history

    iterations: list[dict] = []
    final_answer = ""
    await engine._emit("agent_subagent_start", {
        "task_id": task["id"],
        "role": task_role_spec.slug,
        "title": task_runtime.title,
        "permission_mode": task_permission_engine.mode,
        "tool_names": list(task_tool_names),
        "max_iterations": task_max_iterations,
    })

    for iteration in range(1, task_max_iterations + 1):
        if engine._stop_requested:
            raise RuntimeError("Stopped by user")
        if time.monotonic() > deadline:
            raise RuntimeError("Session timeout")

        await engine._pause_event.wait()

        await engine._emit("agent_status", {"status": "thinking", "task_id": task["id"], "iteration": iteration})

        llm_response = await engine._call_llm_history(history)
        if not llm_response:
            break

        thought, action_name, action_args = engine._parse_response(llm_response)
        task["thought"] = thought

        iter_entry = build_task_iteration_entry(
            iteration=iteration,
            thought=thought,
            action_name=action_name,
            action_args=action_args,
        )

        await engine._emit("agent_task_iteration", build_iteration_thought_event(task["id"], iter_entry))

        if action_name is None:
            verification_summary = task_permission_engine.verification_summary()
            if task_permission_engine.pending_verifications:
                event = record_verification_blocked_iteration(
                    task=task,
                    iterations=iterations,
                    entry=iter_entry,
                    verification_summary=verification_summary,
                )
                await engine._emit("agent_task_iteration", event)
                append_verification_blocked_history(
                    history=history,
                    llm_response=llm_response,
                    verification_summary=verification_summary,
                    hook_manager=engine.hook_manager,
                )
                continue

            final_answer = thought or llm_response
            record_final_answer_iteration(
                task=task,
                iterations=iterations,
                entry=iter_entry,
                verification_summary=verification_summary,
            )
            history.append({"role": "assistant", "content": llm_response})
            break

        if action_name == "ask_user":
            observation = await _ask_user_for_task(engine, action_args)
        else:
            observation = await engine._execute_tool(
                action_name,
                action_args,
                permission_engine=task_permission_engine,
                tool_registry=task_tool_registry,
                allowed_tool_names=task_tool_names,
            )

        await engine._emit(
            "agent_task_iteration",
            record_observed_iteration(
                task=task,
                iterations=iterations,
                entry=iter_entry,
                observation=observation,
            ),
        )
        append_observation_history(
            history=history,
            llm_response=llm_response,
            observation=observation,
            hook_manager=engine.hook_manager,
        )

        if engine.run_record:
            plan_tasks_copy = merge_task_update_into_plan_tasks(engine.run_record.plan_tasks or [], task)
            await sync_to_async(engine._update_run)(engine.run_record, plan_tasks=plan_tasks_copy)

    if not final_answer:
        if task_permission_engine.pending_verifications:
            raise RuntimeError(task_permission_engine.verification_summary())
        final_answer = await engine._summarize_task(task, iterations)

    task["verification_summary"] = task_permission_engine.verification_summary()
    await engine._emit("agent_subagent_done", {
        "task_id": task["id"],
        "role": task_role_spec.slug,
        "verification_summary": task["verification_summary"],
        "pending_verifications": sorted(task_permission_engine.pending_verifications),
    })
    return final_answer, iterations


async def summarize_multi_agent_task(engine: Any, task: dict, iterations: list[dict]) -> str:
    """Ask the LLM to summarize task results when no explicit final answer exists."""
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
    with engine._audit_scope():
        async for chunk in provider.stream_chat(
            prompt,
            model=engine.model_preference,
            specific_model=engine.specific_model,
            purpose="opssummary",
        ):
            chunks.append(chunk)
    return "".join(chunks)


async def _ask_user_for_task(engine: Any, action_args: dict) -> str:
    question = action_args.get("question", "Нужна помощь пользователя")
    if engine.run_record:
        await sync_to_async(engine._update_run)(
            engine.run_record,
            status=AgentRun.STATUS_WAITING,
            pending_question=question,
        )
    await engine._emit("agent_status", {"status": "waiting"})
    answer = await engine._wait_for_user_reply()
    if engine.run_record:
        await sync_to_async(engine._update_run)(
            engine.run_record,
            status=AgentRun.STATUS_RUNNING,
            pending_question="",
        )
    return f"Пользователь ответил: {answer}"
