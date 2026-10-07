"""Regression: nested SingleThreadExecutor must not deadlock pipeline_draft LLM."""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async

from studio.services.pipeline_assistant import (
    PipelineAssistantError,
    _run_llm_in_fresh_thread,
    build_pipeline_assistant_response,
)


@pytest.mark.asyncio
async def test_pipeline_assistant_llm_ok_when_tool_runs_off_sensitive_executor():
    """Operator path: execute_tool uses thread_sensitive=False, then nested LLM is safe.

    Root cause of ``LLM error: Single thread executor already being used, would deadlock``:
    operator loop ran ``sync_to_async(execute_tool)`` (default thread_sensitive=True) and
    ``create_pipeline_draft`` nested ``asyncio.new_event_loop`` + LLM
    ``sync_to_async(thread_sensitive=True)`` on the same SingleThreadExecutor.
    """

    def _nested_sensitive_db_touch() -> str:
        return "ok-from-sensitive"

    async def fake_call_llm(*, user_prompt: str, execution_context=None) -> str:
        return await sync_to_async(_nested_sensitive_db_touch, thread_sensitive=True)()

    def _tool_handler() -> str:
        return _run_llm_in_fresh_thread(user_prompt="ping")

    with patch("studio.services.pipeline_assistant._call_llm", fake_call_llm):
        # Matches operator_loop_tool_cycle._execute_tool_async
        result = await sync_to_async(_tool_handler, thread_sensitive=False)()
    assert result == "ok-from-sensitive"


def test_build_pipeline_assistant_response_surfaces_llm_errors_without_deadlock():
    async def boom(*, user_prompt: str, execution_context=None):
        raise RuntimeError("provider down")

    with patch("studio.services.pipeline_assistant._call_llm", boom):
        with pytest.raises(PipelineAssistantError) as exc:
            build_pipeline_assistant_response(
                user_message="make a pipeline",
                conversation_history=[],
                assistant_context={"pipeline_name": "x"},
            )
    assert "LLM error:" in str(exc.value)
    assert "provider down" in str(exc.value)


def test_build_pipeline_assistant_no_longer_nests_event_loop_on_caller_thread():
    import studio.services.pipeline_assistant as mod

    source = inspect.getsource(mod.build_pipeline_assistant_response)
    assert "new_event_loop" not in source
    assert "_run_llm_in_fresh_thread" in source


def test_operator_tool_cycle_uses_nonsensitive_execute_tool():
    import core_ui.services.operator_loop_tool_cycle as mod

    source = inspect.getsource(mod)
    assert "thread_sensitive=False" in source
    assert "_execute_tool_async" in source
