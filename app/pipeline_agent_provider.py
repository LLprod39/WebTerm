from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class AgentRunSnapshot:
    agent_run_id: int
    status: str
    final_report: str
    ai_analysis: str


class PipelineAgentProvider(Protocol):
    async def run_react_agent(self, **kwargs: Any) -> AgentRunSnapshot: ...

    async def run_multi_agent(self, **kwargs: Any) -> AgentRunSnapshot: ...


_pipeline_agent_provider: PipelineAgentProvider | None = None


def register_pipeline_agent_provider(provider: PipelineAgentProvider | None) -> None:
    global _pipeline_agent_provider
    _pipeline_agent_provider = provider


def _require_pipeline_agent_provider() -> PipelineAgentProvider:
    if _pipeline_agent_provider is None:
        raise RuntimeError("Pipeline agent provider is not registered")
    return _pipeline_agent_provider


async def run_pipeline_react_agent(**kwargs: Any) -> AgentRunSnapshot:
    return await _require_pipeline_agent_provider().run_react_agent(**kwargs)


async def run_pipeline_multi_agent(**kwargs: Any) -> AgentRunSnapshot:
    return await _require_pipeline_agent_provider().run_multi_agent(**kwargs)
