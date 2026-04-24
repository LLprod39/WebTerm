from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from servers.agent_engine import AgentEngine
from servers.models import ServerAgent
from servers.multi_agent_engine import MultiAgentEngine


@dataclass(frozen=True, slots=True)
class AgentRunSnapshot:
    agent_run_id: int
    status: str
    final_report: str
    ai_analysis: str


async def run_pipeline_react_agent(
    *,
    node_id: str,
    goal: str,
    system_prompt: str,
    instructions: str,
    max_iterations: int,
    tools_config: dict[str, bool],
    servers: list[Any],
    user,
    event_callback,
    model_preference: str,
    specific_model: str | None,
    mcp_servers: list[Any],
    skills: list[Any],
    skill_errors: list[str],
) -> AgentRunSnapshot:
    agent = ServerAgent(
        name=f"pipeline_node_{node_id}",
        mode=ServerAgent.MODE_FULL,
        goal=goal,
        system_prompt=system_prompt,
        ai_prompt=instructions,
        max_iterations=max_iterations,
        tools_config=tools_config,
        allow_multi_server=len(servers) > 1,
    )
    engine = AgentEngine(
        agent=agent,
        servers=servers,
        user=user,
        event_callback=event_callback,
        model_preference=model_preference,
        specific_model=specific_model,
        mcp_servers=mcp_servers,
        skills=skills,
        skill_errors=skill_errors,
    )
    agent_run = await engine.run()
    return AgentRunSnapshot(
        agent_run_id=agent_run.pk,
        status=str(agent_run.status),
        final_report=str(agent_run.final_report or ""),
        ai_analysis=str(agent_run.ai_analysis or ""),
    )


async def run_pipeline_multi_agent(
    *,
    node_id: str,
    goal: str,
    system_prompt: str,
    max_iterations: int,
    tools_config: dict[str, bool],
    servers: list[Any],
    user,
    event_callback,
    model_preference: str,
    specific_model: str | None,
    mcp_servers: list[Any],
    skills: list[Any],
    skill_errors: list[str],
) -> AgentRunSnapshot:
    agent = ServerAgent(
        name=f"pipeline_multi_{node_id}",
        mode=ServerAgent.MODE_MULTI,
        goal=goal,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        tools_config=tools_config,
        allow_multi_server=True,
    )
    engine = MultiAgentEngine(
        agent=agent,
        servers=servers,
        user=user,
        event_callback=event_callback,
        model_preference=model_preference,
        specific_model=specific_model,
        mcp_servers=mcp_servers,
        skills=skills,
        skill_errors=skill_errors,
    )
    agent_run = await engine.run()
    return AgentRunSnapshot(
        agent_run_id=agent_run.pk,
        status=str(agent_run.status),
        final_report=str(agent_run.final_report or ""),
        ai_analysis=str(agent_run.ai_analysis or ""),
    )
