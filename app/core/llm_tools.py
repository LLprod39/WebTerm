"""Native tool-calling stream for the Operator chat loop.

Yields a unified event stream independent of provider:

  {"type": "text_delta", "text": str}
  {"type": "tool_call", "id": str, "name": str, "arguments": dict}
  {"type": "done", "usage": dict, "stop_reason": str}
  {"type": "error", "message": str}

F-08a: the implementation lives in focused submodules — ``llm_tool_helpers``
(schema/parsing/selection/message conversion) and ``llm_stream_{anthropic,
openai,ollama,fallback}``. This module keeps the public API stable via
re-exports.
"""

from __future__ import annotations

from app.core.llm_stream_anthropic import stream_anthropic_tools
from app.core.llm_stream_fallback import stream_json_tools_fallback
from app.core.llm_stream_ollama import ollama_model_supports_tools, stream_ollama_tools
from app.core.llm_stream_openai import stream_openai_tools
from app.core.llm_tool_helpers import (
    MAX_TOOL_NAME_LEN,
    NATIVE_TOOLS_SOFT_LIMIT,
    _all_user_text,
    _extract_tool_calls_loose,
    _is_tool_result_only,
    _looks_like_tool_json_leak,
    _messages_to_ollama,
    _messages_to_openai,
    _parse_json_object,
    bound_messages_for_local,
    normalise_tool_name,
    select_tools_for_request,
    tools_to_anthropic,
    tools_to_openai,
)

__all__ = [
    "MAX_TOOL_NAME_LEN",
    "NATIVE_TOOLS_SOFT_LIMIT",
    "_all_user_text",
    "_extract_tool_calls_loose",
    "_is_tool_result_only",
    "_looks_like_tool_json_leak",
    "_messages_to_ollama",
    "_messages_to_openai",
    "_parse_json_object",
    "bound_messages_for_local",
    "normalise_tool_name",
    "ollama_model_supports_tools",
    "select_tools_for_request",
    "stream_anthropic_tools",
    "stream_json_tools_fallback",
    "stream_ollama_tools",
    "stream_openai_tools",
    "tools_to_anthropic",
    "tools_to_openai",
]
