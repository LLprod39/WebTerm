"""Conservative shell-command structure analysis for execution policies.

This is deliberately not a full shell parser.  It extracts command fragments
separated by shell control operators while respecting quotes and marks syntax
that a simple allowlist cannot safely reason about.  Callers must fail closed
when ``is_classifiable`` is false.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

_SHELLS = {"bash", "dash", "fish", "ksh", "sh", "zsh"}
_INDIRECT_COMMANDS = {".", "eval", "exec", "source", "xargs"}
_FIND_EXEC_OPTIONS = {"-exec", "-execdir", "-ok", "-okdir"}
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


@dataclass(frozen=True)
class ShellCommandAnalysis:
    """Security-relevant structure of one shell command string."""

    fragments: tuple[str, ...]
    operators: tuple[str, ...]
    has_dynamic_evaluation: bool = False
    has_redirection: bool = False
    has_indirect_execution: bool = False
    has_unbalanced_quotes: bool = False

    @property
    def is_classifiable(self) -> bool:
        return not (
            self.has_dynamic_evaluation
            or self.has_redirection
            or self.has_indirect_execution
            or self.has_unbalanced_quotes
        )


def _tokenize_fragment(fragment: str) -> tuple[str, ...]:
    try:
        return tuple(shlex.split(fragment, posix=True))
    except ValueError:
        return ()


def _has_indirect_execution(fragments: tuple[str, ...]) -> bool:
    for fragment in fragments:
        tokens = _tokenize_fragment(fragment)
        if not tokens:
            continue

        lowered = tuple(token.lower() for token in tokens)
        executable_index = 0
        while executable_index < len(lowered) and _ASSIGNMENT_RE.match(lowered[executable_index]):
            executable_index += 1
        if executable_index >= len(lowered):
            continue

        executable = lowered[executable_index].rsplit("/", 1)[-1]
        remaining = lowered[executable_index + 1 :]
        if executable in _INDIRECT_COMMANDS:
            return True
        if executable == "env":
            return True
        if executable in _SHELLS and "-c" in remaining:
            return True
        if any(token.rsplit("/", 1)[-1] in _SHELLS for token in lowered) and "-c" in lowered:
            return True
        if executable == "find" and any(token in _FIND_EXEC_OPTIONS for token in remaining):
            return True
    return False


def analyze_shell_command(command: str) -> ShellCommandAnalysis:
    """Split shell control flow and flag structures unsafe for allowlisting."""

    text = str(command or "")
    fragments: list[str] = []
    operators: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    escaped = False
    dynamic = False
    redirection = False
    index = 0

    def flush() -> None:
        fragment = "".join(buffer).strip()
        if fragment:
            fragments.append(fragment)
        buffer.clear()

    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if escaped:
            buffer.append(char)
            escaped = False
            index += 1
            continue

        if char == "\\" and quote != "'":
            buffer.append(char)
            escaped = True
            index += 1
            continue

        if quote == "'":
            buffer.append(char)
            if char == "'":
                quote = None
            index += 1
            continue

        if char == "'" and quote is None:
            quote = "'"
            buffer.append(char)
            index += 1
            continue

        if char == '"':
            quote = None if quote == '"' else '"'
            buffer.append(char)
            index += 1
            continue

        # Command substitutions execute even inside double quotes.
        if char == "`" or (char == "$" and next_char == "("):
            dynamic = True
            buffer.append(char)
            index += 1
            continue

        if quote == '"':
            buffer.append(char)
            index += 1
            continue

        if char in "<>" or (char.isdigit() and next_char in "<>"):
            redirection = True
            buffer.append(char)
            index += 1
            continue

        # Parenthesized groups and process substitutions are control flow that
        # this intentionally small parser cannot safely classify.
        if char in "()":
            dynamic = True
            buffer.append(char)
            index += 1
            continue

        if char == "#" and (not buffer or buffer[-1].isspace()):
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue

        operator = ""
        if char in "&|" and next_char == char:
            operator = char + next_char
        elif char in ";|&\r\n":
            operator = "\n" if char in "\r\n" else char

        if operator:
            flush()
            operators.append(operator)
            index += len(operator)
            if char == "\r" and next_char == "\n":
                index += 1
            continue

        buffer.append(char)
        index += 1

    flush()
    fragment_tuple = tuple(fragments)
    return ShellCommandAnalysis(
        fragments=fragment_tuple,
        operators=tuple(operators),
        has_dynamic_evaluation=dynamic,
        has_redirection=redirection,
        has_indirect_execution=_has_indirect_execution(fragment_tuple),
        has_unbalanced_quotes=quote is not None or escaped,
    )
