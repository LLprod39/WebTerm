from __future__ import annotations

from typing import TYPE_CHECKING, Any

from studio.executor.nodes.ops_helpers import coerce_int as _coerce_int
from studio.executor.ops_runtime import ops_runtime as _ops_runtime

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


def resolve_context_key(ctx: ExecutionContext, config: dict[str, Any], field: str, default_key: str = "") -> Any:
    direct = config.get(field)
    if direct not in (None, ""):
        if isinstance(direct, str):
            return ctx.resolve_template(direct)
        return direct
    key = str(config.get(f"{field}_context_key") or default_key or field).strip()
    return ctx.get_variable(key, "") if key else ""


async def load_owned_server(ctx: ExecutionContext, config: dict[str, Any]):
    server_id = _coerce_int(resolve_context_key(ctx, config, "server_id", "server_id"))
    if not server_id:
        raise ValueError("server_id is required or must be present in pipeline context.")
    server = await _ops_runtime().get_owned_server(ctx.user, server_id)
    if server is None:
        raise ValueError(f"Server not found or inaccessible: {server_id}")
    return server


async def server_secret(server) -> str:
    return await _ops_runtime().server_secret(server)
