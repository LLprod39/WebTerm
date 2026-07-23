"""Tests for terminal-AI asyncio lifecycle state."""

from __future__ import annotations

import asyncio

from servers.services.terminal_ai.run_controller import TerminalAiRunController


async def _sleep_until_cancelled() -> None:
    try:
        await asyncio.sleep(60)
    except asyncio.CancelledError:
        raise


def test_start_task_tracks_active_task() -> None:
    async def scenario() -> None:
        controller = TerminalAiRunController()
        task = controller.start_task(_sleep_until_cancelled())

        assert controller.task is task
        assert controller.has_active_task() is True

        controller.cancel_task()
        assert controller.task is None
        assert task.cancelled() is False
        await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled() is True

    asyncio.run(scenario())


def test_cancel_task_does_not_cancel_current_task() -> None:
    async def scenario() -> None:
        controller = TerminalAiRunController()
        current = asyncio.current_task()
        assert current is not None
        controller.task = current  # type: ignore[assignment]

        controller.cancel_task(current=current)

        assert controller.task is None
        assert current.cancelled() is False

    asyncio.run(scenario())


def test_clear_task_if_current_only_clears_matching_task() -> None:
    async def scenario() -> None:
        controller = TerminalAiRunController()
        current = asyncio.current_task()
        assert current is not None
        controller.task = current  # type: ignore[assignment]

        controller.clear_task_if_current()

        assert controller.task is None

    asyncio.run(scenario())


def test_reply_future_lifecycle() -> None:
    async def scenario() -> None:
        controller = TerminalAiRunController()
        reply_fut = controller.create_reply_future("q1")

        assert controller.resolve_reply("missing", "ignored") is False
        assert controller.resolve_reply("q1", "answer") is True
        assert await reply_fut == "answer"
        assert controller.resolve_reply("q1", "second") is False

        controller.discard_reply_future("q1")
        assert controller.reply_futures == {}

    asyncio.run(scenario())


def test_cancel_reply_futures_cancels_and_clears_pending_replies() -> None:
    async def scenario() -> None:
        controller = TerminalAiRunController()
        first = controller.create_reply_future("q1")
        second = controller.create_reply_future("q2")
        second.set_result("done")

        controller.cancel_reply_futures()

        assert first.cancelled() is True
        assert second.result() == "done"
        assert controller.reply_futures == {}

    asyncio.run(scenario())


def test_ask_user_sends_event_resolves_reply_and_discards_future() -> None:
    async def scenario() -> None:
        controller = TerminalAiRunController()
        sent: list[dict] = []

        async def send_event(event: dict) -> None:
            sent.append(event)
            assert "q1" in controller.reply_futures
            controller.resolve_reply("q1", "answer")

        reply = await controller.ask_user(
            q_id="q1",
            event={"type": "ai_question", "q_id": "q1"},
            send_event=send_event,
            timeout_seconds=1,
        )

        assert reply == "answer"
        assert sent == [{"type": "ai_question", "q_id": "q1"}]
        assert controller.reply_futures == {}

    asyncio.run(scenario())


def test_ask_user_timeout_discards_future() -> None:
    async def scenario() -> None:
        controller = TerminalAiRunController()
        sent: list[dict] = []

        async def send_event(event: dict) -> None:
            sent.append(event)

        try:
            await controller.ask_user(
                q_id="q-timeout",
                event={"type": "ai_question", "q_id": "q-timeout"},
                send_event=send_event,
                timeout_seconds=0.01,
            )
        except TimeoutError:
            pass
        else:  # pragma: no cover - assertion clarity
            raise AssertionError("ask_user should time out")

        assert sent == [{"type": "ai_question", "q_id": "q-timeout"}]
        assert controller.reply_futures == {}

    asyncio.run(scenario())
