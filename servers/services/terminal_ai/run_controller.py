"""Async lifecycle controller for one terminal-AI run."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any


class TerminalAiRunController:
    """Own task, lock, and reply-future state for terminal-AI orchestration.

    The WebSocket consumer still drives SSH and event emission. This object keeps
    the asyncio lifecycle primitives together so cancellation and user-reply
    handling can be tested without a Channels consumer.
    """

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.task: asyncio.Task[None] | None = None
        self.reply_futures: dict[str, asyncio.Future[Any]] = {}

    def has_active_task(self) -> bool:
        return bool(self.task and not self.task.done())

    def start_task(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        self.task = asyncio.create_task(coro)
        return self.task

    def cancel_task(self, *, current: asyncio.Task[Any] | None = None) -> None:
        if self.task and not self.task.done() and (current is None or self.task is not current):
            self.task.cancel()
        self.task = None

    def clear_task_if_current(self) -> None:
        if self.task is asyncio.current_task():
            self.task = None

    def create_reply_future(self, q_id: str) -> asyncio.Future[Any]:
        reply_fut: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self.reply_futures[q_id] = reply_fut
        return reply_fut

    def resolve_reply(self, q_id: str, text: str) -> bool:
        reply_fut = self.reply_futures.get(q_id)
        if not reply_fut or reply_fut.done():
            return False
        reply_fut.set_result(text)
        return True

    def discard_reply_future(self, q_id: str) -> None:
        self.reply_futures.pop(q_id, None)

    def cancel_reply_futures(self) -> None:
        for reply_fut in self.reply_futures.values():
            if not reply_fut.done():
                reply_fut.cancel()
        self.reply_futures = {}

    async def ask_user(
        self,
        *,
        q_id: str,
        event: dict[str, Any],
        send_event: Callable[[dict[str, Any]], Awaitable[None]],
        timeout_seconds: float,
    ) -> Any:
        reply_fut = self.create_reply_future(q_id)
        try:
            await send_event(event)
            return await asyncio.wait_for(reply_fut, timeout=timeout_seconds)
        finally:
            self.discard_reply_future(q_id)
