"""
Shared response-parsing utilities for agent engines.

Both AgentEngine and MultiAgentEngine use the same ReAct-style
THOUGHT / ACTION protocol.  This module provides a single canonical
implementation so bug fixes apply everywhere.
"""
from __future__ import annotations

import json
import re

_ACTION_NAME_RE = re.compile(r"ACTION:\s*([\w_]+)\s*", re.DOTALL)
_THOUGHT_RE = re.compile(r"THOUGHT:\s*(.+?)(?=ACTION:|$)", re.DOTALL)


def parse_action(response: str) -> tuple[str | None, dict]:
    """Надёжный парсинг ACTION: tool_name {...}.

    Использует json.JSONDecoder.raw_decode вместо regex {.*?},
    чтобы корректно обрабатывать многострочные JSON-объекты с отступами.
    """
    name_match = _ACTION_NAME_RE.search(response)
    if not name_match:
        return None, {}

    action_name = name_match.group(1).strip()
    json_start = name_match.end()

    # Пропускаем пробелы до '{'
    while json_start < len(response) and response[json_start] in " \t\n\r":
        json_start += 1

    if json_start >= len(response) or response[json_start] != "{":
        return action_name, {}

    try:
        decoder = json.JSONDecoder()
        action_args, _ = decoder.raw_decode(response, json_start)
        if isinstance(action_args, dict):
            return action_name, action_args
    except json.JSONDecodeError:
        pass

    return action_name, {}


def parse_response(response: str) -> tuple[str, str | None, dict]:
    """Extract THOUGHT and ACTION from LLM response."""
    thought = ""
    thought_match = _THOUGHT_RE.search(response)
    if thought_match:
        thought = thought_match.group(1).strip()
    else:
        thought = response.split("ACTION:")[0].strip() if "ACTION:" in response else response.strip()

    action_name, action_args = parse_action(response)
    if action_name is not None:
        return thought, action_name, action_args

    return thought, None, {}
