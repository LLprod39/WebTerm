from __future__ import annotations

from typing import Any

from servers.services.pipeline_memory import build_pipeline_operational_recipes, get_pipeline_server_card


class DjangoPipelineMemoryProvider:
    async def get_pipeline_server_card(self, server_id: int) -> Any:
        return await get_pipeline_server_card(server_id)

    async def build_pipeline_operational_recipes(
        self,
        query: str,
        *,
        server_ids: list[int] | None = None,
        group_ids: list[int] | None = None,
        limit: int = 4,
    ) -> str:
        return await build_pipeline_operational_recipes(
            query,
            server_ids=server_ids,
            group_ids=group_ids,
            limit=limit,
        )
