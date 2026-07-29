"""Read-only shell command classification for agent permission modes."""

from __future__ import annotations

import re

from app.shell_commands import ShellCommandAnalysis, analyze_shell_command

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
    return is_read_only_analysis(analyze_shell_command(command))


def is_read_only_analysis(analysis: ShellCommandAnalysis) -> bool:
    return bool(analysis.fragments) and analysis.is_classifiable and all(
        _is_read_only_fragment(fragment) for fragment in analysis.fragments
    )


def _is_read_only_fragment(fragment: str) -> bool:
    value = fragment.strip()
    lowered = value.lower()
    if _SIMPLE_READ_ONLY_PATTERN.match(value):
        if re.match(r"^(?:sudo\s+(?:-n\s+)?)?ss(?:\s|$)", value, re.IGNORECASE):
            return not re.search(r"(?:^|\s)(?:-K|--kill)(?:\s|$)", value)
        return True
    if _SYSTEM_READ_ONLY_PATTERN.match(value):
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
            r"-o|--output|-O|--remote-name|-X|--request)(?:\s|=|$)",
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
