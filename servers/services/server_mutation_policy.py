"""Server-authoritative mutation policy for SSH and SFTP surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.shell_commands import is_read_only_command
from app.sudo_policy import command_uses_sudo


@dataclass(frozen=True)
class ServerMutationDecision:
    allowed: bool
    code: str = ""
    message: str = ""


def decide_server_mutation(user: Any, server: Any, *, request: Any = None) -> ServerMutationDecision:
    """Require automation capability for direct mutation endpoints."""

    from servers.agents.agent_pilot_policy import user_can_automate

    if not user_can_automate(user, request=request):
        return ServerMutationDecision(
            allowed=False,
            code="automation_required",
            message="Server mutations require automation access.",
        )
    if bool(getattr(server, "ai_read_only", True)):
        return ServerMutationDecision(
            allowed=False,
            code="server_ai_read_only",
            message="Direct server mutations are disabled for this legacy server record.",
        )
    return ServerMutationDecision(allowed=True)


def decide_server_command(
    user: Any,
    server: Any,
    command: str,
    *,
    request: Any = None,
) -> ServerMutationDecision:
    """Preserve classified diagnostics and gate every other raw SSH command."""

    if is_unprivileged_read_only_command(command):
        return ServerMutationDecision(allowed=True)
    return decide_server_mutation(user, server, request=request)


def is_unprivileged_read_only_command(command: str) -> bool:
    """Classify commands which do not require mutation authorization."""

    return is_read_only_command(command) and not command_uses_sudo(command)
