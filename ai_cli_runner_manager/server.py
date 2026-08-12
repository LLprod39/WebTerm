"""Internal-only authenticated HTTP streaming surface."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from .config import RunnerManagerConfig
from .docker_runtime import DockerCliRuntime
from .fake_runtime import FakeCliRuntime
from .protocol import RunnerProtocolError, RunnerRequestV1, error_event
from .security import RunnerManagerAuthError, authorize_request

config = RunnerManagerConfig.from_env()
runtime: DockerCliRuntime | FakeCliRuntime = FakeCliRuntime() if config.fake_runtime else DockerCliRuntime(config)


async def _require_token(authorization: str | None = Header(default=None)) -> None:
    try:
        authorize_request(config.token, authorization)
    except RunnerManagerAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    config.validate_startup()
    yield


app = FastAPI(title="WebTerm AI CLI Runner Manager", lifespan=_lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "service": "ai-cli-runner-manager", "fake_runtime": config.fake_runtime}


@app.post("/v1/stream", dependencies=[Depends(_require_token)])
async def stream(request: Request) -> StreamingResponse:
    try:
        body = await request.json()
        runner_request = RunnerRequestV1.from_dict(body)
    except (ValueError, RunnerProtocolError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def _events() -> AsyncIterator[bytes]:
        try:
            async for event in runtime.stream(runner_request):
                yield (json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        except Exception:  # noqa: BLE001 - never expose provider stderr or credentials
            event = error_event("provider_runner_unavailable", "CLI runner is unavailable", retryable=True)
            yield (json.dumps(event.to_dict(), separators=(",", ":")) + "\n").encode()

    return StreamingResponse(_events(), media_type="application/x-ndjson")


@app.delete("/v1/invocations/{invocation_id}", dependencies=[Depends(_require_token)])
async def cancel(invocation_id: str) -> dict[str, bool]:
    return {"cancelled": await runtime.cancel(invocation_id)}


@app.delete("/v1/connections/{connection_ref}", dependencies=[Depends(_require_token)])
async def revoke_connection(connection_ref: str) -> dict[str, bool]:
    try:
        revoked = await runtime.revoke_connection(connection_ref)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Credential cleanup failed") from exc
    if not revoked:
        raise HTTPException(status_code=503, detail="Credential cleanup failed")
    return {"revoked": True}
