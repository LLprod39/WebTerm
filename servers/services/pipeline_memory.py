from __future__ import annotations

from servers.adapters.memory_store import DjangoServerMemoryStore

_STORE = DjangoServerMemoryStore()


async def get_pipeline_server_card(server_id: int):
    return await _STORE.get_server_card(server_id)


async def build_pipeline_operational_recipes(
    query: str,
    *,
    server_ids: list[int] | None = None,
    group_ids: list[int] | None = None,
    limit: int = 4,
) -> str:
    return await _STORE.build_operational_recipes_prompt(
        query,
        server_ids=list(server_ids or []),
        group_ids=list(group_ids or []),
        limit=limit,
    )
