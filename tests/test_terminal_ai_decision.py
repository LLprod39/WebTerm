from __future__ import annotations

import json

import pytest

from servers.services.terminal_ai.decision import decide_recovery, decide_step_next


class FakeLLM:
    def __init__(self, chunks: list[str], calls: list[dict]):
        self._chunks = chunks
        self._calls = calls

    async def stream_chat(self, prompt: str, **kwargs):
        self._calls.append({"prompt": prompt, **kwargs})
        for chunk in self._chunks:
            yield chunk


def _fake_llm_factory(chunks: list[str], calls: list[dict]):
    def _factory() -> FakeLLM:
        return FakeLLM(chunks, calls)

    return _factory


@pytest.mark.asyncio
async def test_decide_recovery_returns_valid_decision():
    calls: list[dict] = []
    result = await decide_recovery(
        cmd="netstat -ltnp",
        exit_code=127,
        output="netstat: command not found",
        remaining_cmds=["systemctl status nginx"],
        llm_factory=_fake_llm_factory(
            [
                json.dumps(
                    {
                        "action": "retry",
                        "cmd": "ss -ltnp",
                        "why": "netstat is missing",
                    }
                )
            ],
            calls,
        ),
    )

    assert result["action"] == "retry"
    assert result["cmd"] == "ss -ltnp"
    assert result["why"] == "netstat is missing"
    assert calls[0]["purpose"] == "terminal_recovery"
    assert calls[0]["json_mode"] is True
    assert "netstat -ltnp" in calls[0]["prompt"]


@pytest.mark.asyncio
async def test_decide_recovery_returns_skip_fallback_on_parse_error():
    result = await decide_recovery(
        cmd="x",
        exit_code=1,
        output="bad",
        remaining_cmds=[],
        llm_factory=_fake_llm_factory(["not json"], []),
    )

    assert result["action"] == "skip"
    assert "Не удалось разобрать" in result["why"]


@pytest.mark.asyncio
async def test_decide_step_next_returns_valid_decision():
    calls: list[dict] = []
    result = await decide_step_next(
        user_goal="restart nginx",
        last_cmd="systemctl reload nginx",
        exit_code=0,
        output="ok",
        remaining_cmds=[],
        llm_factory=_fake_llm_factory(
            [
                json.dumps(
                    {
                        "action": "done",
                        "assistant_text": "nginx reloaded",
                    }
                )
            ],
            calls,
        ),
    )

    assert result["action"] == "done"
    assert result["assistant_text"] == "nginx reloaded"
    assert calls[0]["purpose"] == "terminal_step_decision"
    assert calls[0]["json_mode"] is True
    assert "systemctl reload nginx" in calls[0]["prompt"]


@pytest.mark.asyncio
async def test_decide_step_next_returns_continue_fallback_on_parse_error():
    result = await decide_step_next(
        user_goal="x",
        last_cmd="echo x",
        exit_code=0,
        output="x",
        remaining_cmds=[],
        llm_factory=_fake_llm_factory(["not json"], []),
    )

    assert result == {"action": "continue"}
