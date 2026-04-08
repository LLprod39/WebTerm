from __future__ import annotations

import re
from dataclasses import dataclass

from app.agent_kernel.domain.specs import ToolSpec
from app.agent_kernel.sandbox.profiles import NETWORKLESS_PROFILES, READ_ONLY_PROFILES
from app.tools.safety import is_dangerous_command

_READ_ONLY_COMMAND_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(ls|cat|grep|find|head|tail|pwd|whoami|env|printenv|ps|top|ss|netstat|ip\b|hostname)\b", re.IGNORECASE),
    re.compile(r"\b(df\s+-h|free\s+-m|uptime|du\s+-sh)\b", re.IGNORECASE),
    re.compile(r"\bsystemctl\s+status\b|\bservice\s+\S+\s+status\b|\bjournalctl\b", re.IGNORECASE),
    re.compile(r"\bdocker\s+(ps|inspect|logs)\b|\bdocker\s+compose\s+(ps|config)\b", re.IGNORECASE),
    re.compile(r"\bnginx\s+-t\b", re.IGNORECASE),
    re.compile(r"\bcurl\b", re.IGNORECASE),
)

_NETWORK_COMMAND_PATTERN = re.compile(
    r"\b(curl|wget|nc|ncat|telnet|ping|traceroute|dig|nslookup|scp|rsync)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SandboxDecision:
    allowed: bool
    reason: str = ""


class SandboxManager:
    def validate(self, spec: ToolSpec, args: dict, profile: str) -> SandboxDecision:
        command = str(args.get("command") or "")

        if command and is_dangerous_command(command):
            return SandboxDecision(False, "Sandbox blocked a dangerous command.")

        if profile in NETWORKLESS_PROFILES:
            if spec.category == "mcp":
                return SandboxDecision(False, f"Sandbox profile '{profile}' blocks MCP/network calls.")
            if command and _NETWORK_COMMAND_PATTERN.search(command):
                return SandboxDecision(False, f"Sandbox profile '{profile}' blocks network-oriented shell commands.")

        if (
            profile in READ_ONLY_PROFILES
            and spec.name == "ssh_execute"
            and command
            and not any(pattern.search(command) for pattern in _READ_ONLY_COMMAND_PATTERNS)
        ):
            return SandboxDecision(False, f"Sandbox profile '{profile}' allows only read-only shell commands.")

        if profile == "read_only" and (spec.mutates_state or spec.risk in {"write", "admin"}):
            return SandboxDecision(False, "Sandbox profile 'read_only' blocks mutating tools.")

        return SandboxDecision(True)
