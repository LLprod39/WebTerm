"""Internal-only authenticated HTTP streaming surface."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .config import RunnerManagerConfig
from .docker_plane import docker_plane_is_ready
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


@app.get("/health", response_model=None)
async def health() -> JSONResponse:
    docker_plane = docker_plane_is_ready(fake_runtime=config.fake_runtime)
    payload = {
        "ok": bool(docker_plane),
        "service": "ai-cli-runner-manager",
        "fake_runtime": config.fake_runtime,
        "docker_plane": bool(docker_plane),
    }
    return JSONResponse(status_code=200 if docker_plane else 503, content=payload)


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


@app.post("/v1/invocations/{invocation_id}/auth-input", dependencies=[Depends(_require_token)])
async def submit_auth_input(invocation_id: str, request: Request) -> dict[str, bool]:
    try:
        body = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    raw_code = body.get("authorization_code")
    if not isinstance(raw_code, str):
        raise HTTPException(status_code=400, detail="authorization_code is required")
    raw_state = body.get("oauth_state")
    oauth_state = raw_state.strip() if isinstance(raw_state, str) else ""
    submit = getattr(runtime, "submit_auth_input", None)
    if submit is None:
        raise HTTPException(status_code=503, detail="Auth input is not supported")
    accepted = await submit(invocation_id, raw_code, oauth_state=oauth_state)
    if not accepted:
        raise HTTPException(status_code=409, detail="No live auth session accepts input")
    return {"accepted": True}


@app.delete("/v1/connections/{connection_ref}", dependencies=[Depends(_require_token)])
async def revoke_connection(connection_ref: str) -> dict[str, bool]:
    try:
        revoked = await runtime.revoke_connection(connection_ref)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Credential cleanup failed") from exc
    if not revoked:
        raise HTTPException(status_code=503, detail="Credential cleanup failed")
    return {"revoked": True}
