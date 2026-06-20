from __future__ import annotations

from typing import Any, Protocol


class PipelineMemoryProvider(Protocol):
    async def get_pipeline_server_card(self, server_id: int) -> Any: ...

    async def build_pipeline_operational_recipes(
        self,
        query: str,
        *,
        server_ids: list[int] | None = None,
        group_ids: list[int] | None = None,
        limit: int = 4,
    ) -> str: ...


_pipeline_memory_provider: PipelineMemoryProvider | None = None


def register_pipeline_memory_provider(provider: PipelineMemoryProvider | None) -> None:
    global _pipeline_memory_provider
    _pipeline_memory_provider = provider


def _require_pipeline_memory_provider() -> PipelineMemoryProvider:
    if _pipeline_memory_provider is None:
        raise RuntimeError("Pipeline memory provider is not registered")
    return _pipeline_memory_provider


async def get_pipeline_server_card(server_id: int) -> Any:
    return await _require_pipeline_memory_provider().get_pipeline_server_card(server_id)


async def build_pipeline_operational_recipes(
    query: str,
    *,
    server_ids: list[int] | None = None,
    group_ids: list[int] | None = None,
    limit: int = 4,
) -> str:
    return await _require_pipeline_memory_provider().build_pipeline_operational_recipes(
        query,
        server_ids=server_ids,
        group_ids=group_ids,
        limit=limit,
    )
