from __future__ import annotations

import pytest

import servers.services.terminal_ai.memory_extraction as mod
from servers.services.terminal_ai.memory_extraction import (
    extract_server_memory,
    run_memory_extraction,
    save_extracted_server_memory,
)


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
async def test_extract_server_memory_parses_and_cleans_llm_output():
    calls: list[dict] = []
    result = await extract_server_memory(
        user_message="check nginx",
        commands_with_output=[
            {
                "cmd": "systemctl status nginx",
                "exit_code": 0,
                "output": "active (running)",
            }
        ],
        report="nginx ok",
        llm_factory=_fake_llm_factory(
            [
                "```json\n",
                (
                    '{"summary":" nginx active\\n ","facts":["nginx 1.24",'
                    '"NGINX 1.24","port 443 open"],"issues":[" disk 85% "]}'
                ),
                "\n```",
            ],
            calls,
        ),
    )

    assert result == {
        "summary": "nginx active",
        "facts": ["nginx 1.24", "port 443 open"],
        "issues": ["disk 85%"],
    }
    assert calls[0]["purpose"] == "memory_extraction"
    assert calls[0]["model"] == "auto"
    assert "systemctl status nginx" in calls[0]["prompt"]


@pytest.mark.asyncio
async def test_extract_server_memory_returns_empty_payload_on_parse_error():
    result = await extract_server_memory(
        user_message="x",
        commands_with_output=[],
        llm_factory=_fake_llm_factory(["not json"], []),
    )

    assert result == {"summary": "", "facts": [], "issues": []}


@pytest.mark.asyncio
async def test_extract_server_memory_limits_lists():
    facts = [f"fact {idx}" for idx in range(12)]
    issues = [f"issue {idx}" for idx in range(7)]
    result = await extract_server_memory(
        user_message="x",
        commands_with_output=[],
        llm_factory=_fake_llm_factory(
            [
                (
                    '{"summary":"ok","facts":'
                    + repr(facts).replace("'", '"')
                    + ',"issues":'
                    + repr(issues).replace("'", '"')
                    + "}"
                )
            ],
            [],
        ),
    )

    assert len(result["facts"]) == 8
    assert len(result["issues"]) == 4


@pytest.mark.asyncio
async def test_save_extracted_server_memory_skips_empty_payload(monkeypatch):
    calls: list[dict] = []

    async def fake_save_server_profile(**kwargs):
        calls.append(kwargs)
        return {"saved": 1}

    monkeypatch.setattr(mod, "save_server_profile", fake_save_server_profile)

    result = await save_extracted_server_memory(
        user_id=1,
        server_id=2,
        memory_obj={"summary": "", "facts": [], "issues": []},
    )

    assert result is None
    assert calls == []


@pytest.mark.asyncio
async def test_run_memory_extraction_persists_non_empty_payload(monkeypatch):
    calls: list[dict] = []

    async def fake_extract_server_memory(**kwargs):
        calls.append({"extract": kwargs})
        return {"summary": "nginx", "facts": ["port 443"], "issues": []}

    async def fake_save_server_profile(**kwargs):
        calls.append({"save": kwargs})
        return {"saved": 1}

    monkeypatch.setattr(mod, "extract_server_memory", fake_extract_server_memory)
    monkeypatch.setattr(mod, "save_server_profile", fake_save_server_profile)

    result = await run_memory_extraction(
        user_message="check",
        commands_with_output=[{"cmd": "ss -ltnp", "output": ":443", "exit_code": 0}],
        report="ok",
        user_id=11,
        server_id=22,
        semaphore="sem",
        llm_factory="llm",
    )

    assert result == {"saved": 1}
    assert calls[0]["extract"]["semaphore"] == "sem"
    assert calls[0]["extract"]["llm_factory"] == "llm"
    assert calls[1]["save"] == {
        "user_id": 11,
        "server_id": 22,
        "summary": "nginx",
        "facts": ["port 443"],
        "issues": [],
    }
