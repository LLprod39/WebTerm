from __future__ import annotations

import pytest

from servers.services.terminal_ai.report_generation import generate_ai_report_text, make_ai_report


class FakeLLM:
    async def stream_chat(self, prompt: str, *, model: str, purpose: str):
        assert purpose == "terminal_report"
        assert model == "auto"
        assert "df -h" in prompt
        yield "Сводка"
        yield ": ok"


class FailingLLM:
    async def stream_chat(self, *_args, **_kwargs):
        raise RuntimeError("provider down")
        yield ""


class FakeSemaphore:
    def __init__(self):
        self.entered = False

    async def __aenter__(self):
        self.entered = True

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_make_ai_report_uses_llm_factory_and_optional_semaphore() -> None:
    semaphore = FakeSemaphore()

    report = await make_ai_report(
        "check disk",
        [{"cmd": "df -h", "output": "ok", "exit_code": 0}],
        semaphore=semaphore,
        llm_factory=FakeLLM,
    )

    assert report == "Сводка: ok"
    assert semaphore.entered is True


@pytest.mark.asyncio
async def test_generate_ai_report_text_falls_back_when_no_output() -> None:
    report = await generate_ai_report_text("goal", [{"cmd": "true", "exit_code": 0}], llm_factory=FakeLLM)

    assert "Команды выполнены успешно" in report


@pytest.mark.asyncio
async def test_generate_ai_report_text_falls_back_on_llm_failure() -> None:
    report = await generate_ai_report_text(
        "goal",
        [{"cmd": "df -h", "output": "disk full", "exit_code": 1}],
        llm_factory=FailingLLM,
    )

    assert "Коды выхода: 1" in report
