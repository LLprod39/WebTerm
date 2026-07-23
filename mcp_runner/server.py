"""FastAPI surface for the MCP Runner.

Internal service (bind to the docker network only). The backend authenticates
with a shared bearer token and proxies JSON-RPC through POST /rpc; the Runner
keeps one initialized stdio MCP process alive per session key.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from mcp_runner.config import RunnerConfig
from mcp_runner.sessions import RunnerError, SessionManager

logger = logging.getLogger("mcp_runner")

config = RunnerConfig()
manager = SessionManager(config)


class SpawnSpec(BaseModel):
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class RpcRequest(BaseModel):
    session: str
    spec: SpawnSpec
    method: str
    params: dict[str, Any] | None = None
    notify: bool = False
    timeout: float | None = None


async def _require_token(authorization: str | None = Header(default=None)) -> None:
    if not config.token:
        # No token configured => auth disabled (single-tenant/dev). Fail closed in
        # production by always setting MCP_RUNNER_TOKEN.
        return
    expected = f"Bearer {config.token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing runner token")


async def _reaper() -> None:
    while True:
        await asyncio.sleep(config.reap_interval_seconds)
        try:
            reaped = await manager.reap_idle()
            if reaped:
                logger.info("mcp-runner reaped %s idle session(s)", reaped)
        except Exception:  # pragma: no cover - defensive
            logger.exception("mcp-runner reaper error")


@contextlib.asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_reaper())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await manager.shutdown()


app = FastAPI(title="WebTrerm MCP Runner", lifespan=_lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "service": "mcp-runner", **manager.stats()}


@app.post("/rpc", dependencies=[Depends(_require_token)])
async def rpc(request: RpcRequest) -> dict[str, Any]:
    try:
        result = await manager.rpc(
            request.session,
            request.spec.model_dump(),
            request.method,
            request.params,
            notify=request.notify,
            timeout=request.timeout,
        )
    except RunnerError as exc:
        return {"error": {"message": str(exc)}}
    except TimeoutError:
        return {"error": {"message": f"MCP request '{request.method}' timed out"}}
    return {"result": result if result is not None else {}}


@app.get("/sessions", dependencies=[Depends(_require_token)])
async def sessions() -> dict[str, Any]:
    return manager.stats()


@app.delete("/sessions/{session_key}", dependencies=[Depends(_require_token)])
async def close_session(session_key: str) -> dict[str, Any]:
    await manager.reap_idle()
    return {"ok": True}
