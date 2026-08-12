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
_CODE_INTERPRETERS = {
    "node",
    "nodejs",
    "perl",
    "php",
    "python",
    "python2",
    "python3",
    "ruby",
}
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
        if executable in _CODE_INTERPRETERS and any(flag in remaining for flag in ("-c", "-e", "--eval")):
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

        if char in "<>" or (char.isdigit() and bool(next_char) and next_char in "<>"):
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


_SIMPLE_READ_ONLY_PATTERN = re.compile(
    r"^(?:sudo\s+(?:-n\s+)?)?"
    r"(?:ls|cat|grep|head|tail|pwd|whoami|printenv|ps|ss|netstat|"
    r"df|free|uptime|du|uname|id|groups|which|stat|wc|cut|tr|echo|printf|"
    r"test|true|false)(?:\s|$)",
    re.IGNORECASE,
)
_SYSTEM_READ_ONLY_PATTERN = re.compile(
    r"^(?:sudo\s+(?:-n\s+)?)?(?:"
    r"systemctl\s+(?:status|is-active|is-enabled|show|list-units|list-unit-files)\b|"
    r"service\s+\S+\s+status\b|"
    r"nginx\s+-t\b)",
    re.IGNORECASE,
)
_DOCKER_READ_ONLY_PATTERN = re.compile(
    r"^(?:sudo\s+(?:-n\s+)?)?docker\s+(?:"
    r"ps|inspect|logs|images|info|version|stats|"
    r"compose\s+(?:ps|config|logs|images))\b",
    re.IGNORECASE,
)
_KUBECTL_READ_ONLY_PATTERN = re.compile(
    r"^(?:kubectl\s+)(?:get|describe|logs|top|api-resources|api-versions|version|explain)\b|"
    r"^kubectl\s+auth\s+can-i\b",
    re.IGNORECASE,
)
_GIT_READ_ONLY_PATTERN = re.compile(r"^git\s+(?:status|log|show|diff|remote\s+-v)\b", re.IGNORECASE)


def is_read_only_command(command: str) -> bool:
    """Return true only for structurally classifiable diagnostic commands."""

    return is_read_only_analysis(analyze_shell_command(command))


def is_read_only_analysis(analysis: ShellCommandAnalysis) -> bool:
    return (
        bool(analysis.fragments)
        and analysis.is_classifiable
        and all(_is_read_only_fragment(fragment) for fragment in analysis.fragments)
    )


def _is_read_only_fragment(fragment: str) -> bool:
    value = fragment.strip()
    lowered = value.lower()
    if _SIMPLE_READ_ONLY_PATTERN.match(value):
        if re.match(r"^(?:sudo\s+(?:-n\s+)?)?ss(?:\s|$)", value, re.IGNORECASE):
            return not re.search(r"(?:^|\s)(?:-K|--kill)(?:\s|$)", value)
        return True
    if _SYSTEM_READ_ONLY_PATTERN.match(value):
        if re.match(r"^(?:sudo\s+(?:-n\s+)?)?nginx(?:\s|$)", value, re.IGNORECASE):
            return not re.search(
                r"(?:^|\s)-s(?:\s|=|(?:stop|quit|reopen|reload)\b)",
                value,
                re.IGNORECASE,
            )
        return True
    if _DOCKER_READ_ONLY_PATTERN.match(value):
        return not re.search(r"(?:^|\s)--output(?:=|\s)", value, re.IGNORECASE)
    if _KUBECTL_READ_ONLY_PATTERN.match(value) or _GIT_READ_ONLY_PATTERN.match(value):
        return not re.search(r"(?:^|\s)--output(?:=|\s)", value, re.IGNORECASE)
    if re.match(r"^(?:sudo\s+(?:-n\s+)?)?hostname(?:\s|$)", value, re.IGNORECASE):
        return bool(
            re.fullmatch(
                r"(?:sudo\s+(?:-n\s+)?)?hostname(?:\s+(?:"
                r"-[adfFisAIVy]|--(?:alias|all-fqdns|all-ip-addresses|domain|fqdn|help|"
                r"ip-address|long|short|version)))*\s*",
                value,
                re.IGNORECASE,
            )
        )
    if re.match(r"^(?:sudo\s+(?:-n\s+)?)?date(?:\s|$)", value, re.IGNORECASE):
        return bool(
            re.fullmatch(
                r"(?:sudo\s+(?:-n\s+)?)?date(?:\s+(?:"
                r"\+\S+|-u|--utc|--universal|-R|--rfc-email|--debug|"
                r"-I(?:date|hours|minutes|seconds|ns)?|--iso-8601(?:=\S+)?))*\s*",
                value,
                re.IGNORECASE,
            )
        )
    if re.match(r"^(?:sudo\s+(?:-n\s+)?)?journalctl(?:\s|$)", value, re.IGNORECASE):
        return not any(
            option in lowered
            for option in (
                "--flush",
                "--relinquish-var",
                "--rotate",
                "--setup-keys",
                "--sync",
                "--update-catalog",
                "--vacuum",
            )
        )
    if re.match(r"^(?:sudo\s+(?:-n\s+)?)?find(?:\s|$)", value, re.IGNORECASE):
        return not re.search(
            r"(?:^|\s)-(?:delete|exec|execdir|fls|fprintf|fprint|fprint0|ok|okdir)\b",
            value,
        )
    if re.match(r"^(?:sudo\s+(?:-n\s+)?)?curl(?:\s|$)", value, re.IGNORECASE):
        has_head_mode = bool(re.search(r"(?:^|\s)(?:-I|--head)(?:\s|$)", value))
        mutating_option = re.search(
            r"(?:^|\s)(?:-d|--data(?:-ascii|-binary|-raw|-urlencode)?|-F|--form|-T|--upload-file|"
            r"-o|--output|-O|--remote-name|-X|--request|-c|--cookie-jar|--libcurl|"
            r"--trace[^\s=]*)(?:\s|=|/|$)|(?:^|\s)-[A-Za-z]*c(?:\s|=|/|$)",
            value,
            re.IGNORECASE,
        )
        return has_head_mode and not mutating_option
    if re.match(r"^(?:sudo\s+(?:-n\s+)?)?ip(?:\s|$)", value, re.IGNORECASE):
        read_prefix = bool(
            re.match(
                r"^(?:sudo\s+(?:-n\s+)?)?ip(?:\s+-(?:br|brief|details|json|oneline|pretty))*\s+"
                r"(?:a|addr|address|link|neigh|neighbor|r|route)(?:\s+(?:get|list|show))?(?:\s|$)",
                value,
                re.IGNORECASE,
            )
        )
        mutating_verb = re.search(
            r"(?:^|\s)(?:add|append|change|del|delete|flush|prepend|replace|restore|set)(?:\s|$)",
            value,
            re.IGNORECASE,
        )
        return read_prefix and not mutating_verb
    if re.match(r"^command\s+-v(?:\s|$)", value, re.IGNORECASE):
        return bool(re.fullmatch(r"command\s+-v\s+[^\s;&|<>]+\s*", value, re.IGNORECASE))
    return False
