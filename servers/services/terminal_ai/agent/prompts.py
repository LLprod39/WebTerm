"""
Prompt builders for the Terminal Agent.

The agent works in a single long-running conversation: one system
message describing the rules + tool schemas, then alternating
``user`` (observations) and ``assistant`` (tool calls) turns rendered
as text inside a single prompt per iteration (JSON mode on the LLM
guarantees the response is a valid :class:`AgentStep`).

Design notes
------------
- We do **not** rely on native tool-calling APIs. A provider-agnostic
  JSON response is emitted by the LLM and validated via pydantic.
- Tool descriptions are inlined into the system prompt so the model
  sees them every turn. We also inline the pydantic JSON schema of
  each tool's args so the model learns the exact argument shape.
- Observations (tool results) are passed through
  :func:`sanitize_for_prompt` to neutralise prompt-injection attempts
  and redact secrets leaked by commands.
"""

from __future__ import annotations

import json
from typing import Any

from servers.services.terminal_ai.agent.tools.base import (
    ServerTarget,
    TerminalTool,
)
from servers.services.terminal_ai.prompts import sanitize_for_prompt

# Hard cap on how much history we keep in the prompt before summarising
# older turns. Beyond this the loop will trim the oldest exchanges.
MAX_HISTORY_TURNS = 30


def build_tool_catalogue(tools: dict[str, TerminalTool]) -> str:
    """Render a Markdown-style tool catalogue for the system prompt."""
    lines: list[str] = ["Available tools (call exactly ONE per turn):"]
    for name, tool in tools.items():
        schema = tool.args_schema.model_json_schema()
        # Strip verbose pydantic noise.
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        arg_lines = []
        for arg_name, arg_spec in props.items():
            is_req = "req" if arg_name in required else "opt"
            default = arg_spec.get("default")
            arg_type = arg_spec.get("type", arg_spec.get("anyOf", [{}])[0].get("type", "any"))
            desc = arg_spec.get("description", "") or arg_spec.get("title", "")
            default_s = f" default={default!r}" if default is not None and is_req == "opt" else ""
            arg_lines.append(
                f"    - {arg_name} [{is_req}:{arg_type}]{default_s}: {desc}"
            )
        arg_block = "\n".join(arg_lines) if arg_lines else "    (no args)"
        lines.append(f"\n● {name}\n  {tool.description}\n  args:\n{arg_block}")
    return "\n".join(lines)


def build_targets_block(primary: ServerTarget, extras: dict[str, ServerTarget]) -> str:
    """Describe authorised targets at the top of the system prompt."""
    lines = [
        "Authorised servers for this session:",
        f"- PRIMARY {primary.name!r} → {primary.display_name or primary.host} "
        f"(server_id={primary.server_id}"
        + (", read-only" if primary.read_only else "")
        + ")",
    ]
    for t in extras.values():
        lines.append(
            f"- extra   {t.name!r} → {t.display_name or t.host} "
            f"(server_id={t.server_id}"
            + (", read-only" if t.read_only else "")
            + ")"
        )
    if not extras:
        lines.append("  (no extra targets granted — user can add them via settings)")
    lines.append(
        "Pass `target: \"<name>\"` on file/shell/grep tools to select a "
        "non-primary server. Empty `target` means PRIMARY."
    )
    return "\n".join(lines)


SYSTEM_PROMPT_TEMPLATE = """\
You are Nova — an autonomous terminal assistant running inside a user's \
SSH session. You orchestrate a ReAct loop: you observe, reason briefly, \
then call exactly ONE tool per turn. Never emit free-form prose — every \
response MUST be a single JSON object of the form:

  {{
    "thinking": "<one or two short sentences of reasoning>",
    "tool": "<tool name>",
    "args": {{<tool args>}},
    "final_text": ""
  }}

Language policy (STRICT):
- The operator's working language is Russian. ALL natural-language \
strings you produce MUST be written in Russian: `thinking`, \
`final_text`, questions in `ask_user.question`, todo item `content`, \
notes in `remember.note`.
- Shell commands, file paths, tool names, JSON keys, server names, \
log lines quoted verbatim and other technical identifiers stay in \
their original form (do NOT transliterate or translate them).
- Never mix English narrative into the `thinking` / `final_text` \
fields even if the tool output or user message is in English. If the \
user writes in another language, still reply in Russian unless they \
explicitly request otherwise.

Special rules:
- Emit `tool: "done"` with `final_text` set to your final user-facing \
summary (in Russian) when the task is complete. The loop stops as \
soon as `done` is seen.
- Keep `thinking` tight — it burns tokens; it is shown to the user in \
a collapsible block.
- Before invoking destructive commands, update the todo list and/or \
ask the user via `ask_user`.
- Keep the `todo_write` list current so the human operator can follow \
progress on long tasks.
- Use `list_targets` if unsure which server name to pass as `target`.
- Prefer `read_file`, `edit_file`, `grep`, `list_files` over `shell` \
for file operations — they are deterministic and take snapshots.
- Treat live shell/session context and recent human activity as \
best-effort current-session evidence, not durable memory. Verify before \
risky actions.
- If a command is vetoed by the safety engine, DO NOT retry the same \
command differently quoted; instead `ask_user` for confirmation with \
clear risk description.

{targets_block}

{memory_block}

{tool_catalogue}
"""


# Heading placed above the layered-server-memory block so the model
# understands *why* this block matters (persistent facts across sessions)
# and that it is safe to trust these as prior knowledge (unlike raw tool
# output which may come from untrusted sources).
_MEMORY_HEADER = (
    "Persistent server memory (from previous sessions — trusted prior\n"
    "knowledge about layouts, configs, risks, runbooks). Use it to skip\n"
    "re-discovery and to know where things live. If something looks\n"
    "stale or contradicts reality, verify and then `remember` a correction."
)


def build_system_prompt(
    *,
    tools: dict[str, TerminalTool],
    primary: ServerTarget,
    extras: dict[str, ServerTarget],
    rules_context: str = "",
    memory_context: str = "",
) -> str:
    """Compose the full system prompt for the agent loop.

    ``memory_context`` is the rendered layered-server-memory block for
    the authorised targets (see :mod:`app.agent_kernel.memory.server_cards`).
    When non-empty it is inlined between the targets list and the tool
    catalogue so the LLM reads it as trusted prior knowledge.
    """
    mem = (memory_context or "").strip()
    memory_block = (
        f"{_MEMORY_HEADER}\n\n{sanitize_for_prompt(mem, mode='context')}"
        if mem
        else "Persistent server memory: (empty — build it up via `remember` for "
        "durable facts that generalise beyond this task)."
    )
    base = SYSTEM_PROMPT_TEMPLATE.format(
        targets_block=build_targets_block(primary, extras),
        memory_block=memory_block,
        tool_catalogue=build_tool_catalogue(tools),
    )
    if rules_context.strip():
        base += "\n\nAdditional rules from the user:\n" + sanitize_for_prompt(
            rules_context, mode="context"
        )
    return base


def build_user_turn_prompt(
    *,
    user_message: str,
    history: list[dict[str, Any]],
    session_context: str = "",
    recent_activity_context: str = "",
) -> str:
    """Render the running conversation into a single user-role string.

    ``history`` entries have the shape::

        {"role": "user"|"tool_call"|"tool_result", "content": <dict|str>}

    Tool results are sanitised through
    :func:`sanitize_for_prompt` before inclusion to block prompt
    injection and redact secrets.
    """
    # Keep only the last MAX_HISTORY_TURNS entries — older context rolls off.
    recent = history[-MAX_HISTORY_TURNS:]

    parts: list[str] = []
    if user_message.strip():
        parts.append(f"User task: {sanitize_for_prompt(user_message, mode='context')}")
    if session_context.strip():
        parts.append(
            "\nLive shell/session context:\n"
            + sanitize_for_prompt(session_context, mode="context")
        )
    if recent_activity_context.strip():
        parts.append(
            "\nRecent human activity in this terminal session:\n"
            + sanitize_for_prompt(recent_activity_context, mode="context")
        )

    for entry in recent:
        role = entry.get("role")
        content = entry.get("content")
        if role == "tool_call":
            # Content is {tool, args, thinking}
            parts.append(
                f"\n[turn {entry.get('turn', '?')}] agent → tool:\n"
                + json.dumps(content, ensure_ascii=False)[:2000]
            )
        elif role == "tool_result":
            raw = content if isinstance(content, str) else json.dumps(
                content, ensure_ascii=False
            )
            sanitized = sanitize_for_prompt(raw[:4000], mode="observation")
            parts.append(
                f"\n[turn {entry.get('turn', '?')}] tool → observation:\n{sanitized}"
            )
        elif role == "user":
            parts.append(
                "\nUser interjection: "
                + sanitize_for_prompt(str(content or ""), mode="context")
            )

    parts.append(
        "\nPick the next tool. Respond ONLY with the JSON object described "
        "in the system prompt."
    )
    return "\n".join(parts)
