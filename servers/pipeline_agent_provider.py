from __future__ import annotations

from typing import Any

from app.pipeline_agent_provider import AgentRunSnapshot
from servers.services.pipeline_agents import run_pipeline_multi_agent, run_pipeline_react_agent


class DjangoPipelineAgentProvider:
    async def run_react_agent(self, **kwargs: Any) -> AgentRunSnapshot:
        return await run_pipeline_react_agent(**kwargs)

    async def run_multi_agent(self, **kwargs: Any) -> AgentRunSnapshot:
        return await run_pipeline_multi_agent(**kwargs)
