from __future__ import annotations

import json

import pytest

from servers.services.terminal_ai.planning import extract_json_object, plan_terminal_commands


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


def test_extract_json_object_handles_prose_and_code_fence():
    result = extract_json_object('text\n```json\n{"mode":"answer","commands":[]}\n```\ntrail')

    assert result == {"mode": "answer", "commands": []}


def test_extract_json_object_rejects_missing_object():
    with pytest.raises(ValueError, match="AI не вернул JSON"):
        extract_json_object("no object here")


@pytest.mark.asyncio
async def test_plan_terminal_commands_parses_schema_and_preserves_exec_mode():
    calls: list[dict] = []
    result = await plan_terminal_commands(
        user_message="list services",
        rules_context="readonly",
        terminal_tail="",
        history=[{"role": "user", "content": "hi"}],
        unavailable_cmds={"netstat"},
        execution_mode="fast",
        llm_factory=_fake_llm_factory(
            [
                json.dumps(
                    {
                        "mode": "execute",
                        "execution_mode": "fast",
                        "assistant_text": "checking",
                        "commands": [
                            {
                                "cmd": "ss -ltnp",
                                "why": "list listening sockets",
                                "exec_mode": "direct",
                            }
                        ],
                    }
                )
            ],
            calls,
        ),
    )

    assert result["mode"] == "execute"
    assert result["execution_mode"] == "fast"
    assert result["commands"] == [
        {
            "cmd": "ss -ltnp",
            "why": "list listening sockets",
            "exec_mode": "direct",
        }
    ]
    assert calls[0]["purpose"] == "terminal_planning"
    assert calls[0]["json_mode"] is True
    assert calls[0]["system_prompt"]


@pytest.mark.asyncio
async def test_plan_terminal_commands_uses_legacy_object_fallback_on_schema_error():
    raw_payload = {
        "mode": "execute",
        "assistant_text": "legacy",
        "commands": [{"cmd": f"echo {idx}", "why": ""} for idx in range(20)],
    }

    result = await plan_terminal_commands(
        user_message="x",
        rules_context="",
        terminal_tail="",
        llm_factory=_fake_llm_factory([json.dumps(raw_payload)], []),
    )

    assert result == raw_payload


@pytest.mark.asyncio
async def test_plan_terminal_commands_returns_user_safe_fallback_when_unparseable():
    result = await plan_terminal_commands(
        user_message="x",
        rules_context="",
        terminal_tail="",
        execution_mode="auto",
        llm_factory=_fake_llm_factory(["not json"], []),
    )

    assert result["mode"] == "answer"
    assert result["execution_mode"] == "step"
    assert result["commands"] == []
    assert "Не удалось разобрать" in result["assistant_text"]


@pytest.mark.asyncio
async def test_plan_terminal_commands_provider_error_text_raises():
    with pytest.raises(ValueError, match="ERROR: temporary"):
        await plan_terminal_commands(
            user_message="x",
            rules_context="",
            terminal_tail="",
            llm_factory=_fake_llm_factory(["ERROR: temporary"], []),
        )
