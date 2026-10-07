"""In-process authorization-code handoff for live AUTH_START runners."""

from __future__ import annotations

import asyncio
import re

_AUTH_CODE = re.compile(r"^[A-Za-z0-9_./+=-]{8,2048}$")
_queues: dict[str, asyncio.Queue[str]] = {}


def register_auth_input_queue(invocation_id: str) -> asyncio.Queue[str]:
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
    _queues[invocation_id] = queue
    return queue


def unregister_auth_input_queue(invocation_id: str) -> None:
    _queues.pop(invocation_id, None)


def normalize_authorization_code(value: str) -> str:
    code = (value or "").strip()
    if not _AUTH_CODE.fullmatch(code):
        raise ValueError("authorization_code has an invalid format")
    return code


async def publish_auth_input(invocation_id: str, authorization_code: str) -> bool:
    queue = _queues.get(invocation_id)
    if queue is None:
        return False
    code = normalize_authorization_code(authorization_code)
    if queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    queue.put_nowait(code)
    return True


async def wait_auth_input(invocation_id: str, *, timeout: float) -> str | None:
    queue = _queues.get(invocation_id)
    if queue is None:
        return None
    try:
        return await asyncio.wait_for(queue.get(), timeout=timeout)
    except TimeoutError:
        return None
