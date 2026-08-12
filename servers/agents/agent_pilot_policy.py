"""Server-authoritative safety policy for restricted pilot agents."""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

from app.sudo_policy import SUDO_POLICY_DISABLED, normalize_sudo_policy
from core_ui.access import build_user_access_payload
from core_ui.context_processors import user_can_feature
from servers.agents.agent_tools import DEFAULT_READ_ONLY_AGENT_TOOLS

PILOT_AGENT_ALLOWED_TOOLS = frozenset(
    {
        *DEFAULT_READ_ONLY_AGENT_TOOLS,
        "ssh_execute",
        "open_connection",
        "close_connection",
    }
)
PILOT_MAX_ITERATIONS = 15
PILOT_MAX_SESSION_TIMEOUT_SECONDS = 600


def user_can_automate(user, *, request=None) -> bool:
    if not user_can_feature(user, "automation", request=request):
        return False
    pilot_restricted = os.getenv("PILOT_RESTRICTED_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if not pilot_restricted:
        return True
    return build_user_access_payload(user, request=request).get("access_profile") == "pilot_operator"


def pilot_agent_policy_violations(
    *,
    user,
    servers: Iterable[Any],
    tools_config: Any,
    sudo_policy: Any,
    schedule_minutes: Any,
    schedule_config: Any,
    allow_multi_server: Any,
    max_connections: Any,
    max_iterations: Any,
    session_timeout_seconds: Any,
    request=None,
) -> list[str]:
    if user_can_automate(user, request=request):
        return []
    violations: list[str] = []
    unsafe_servers = [
        str(getattr(server, "pk", getattr(server, "id", "?")))
        for server in servers
        if not bool(getattr(server, "ai_read_only", False))
    ]
    if unsafe_servers:
        violations.append(f"servers must be AI read-only: {', '.join(unsafe_servers[:10])}")
    if not isinstance(tools_config, dict):
        violations.append("tools_config must be an object")
    else:
        non_boolean = sorted(name for name, enabled in tools_config.items() if not isinstance(enabled, bool))
        if non_boolean:
            violations.append(f"tool flags must be boolean: {', '.join(non_boolean[:10])}")
        unsafe_tools = sorted(
            name for name, enabled in tools_config.items() if enabled is True and name not in PILOT_AGENT_ALLOWED_TOOLS
        )
        if unsafe_tools:
            violations.append(f"tools require automation capability: {', '.join(unsafe_tools[:10])}")
    if normalize_sudo_policy(sudo_policy) != SUDO_POLICY_DISABLED:
        violations.append("sudo requires automation capability")
    try:
        scheduled = int(schedule_minutes or 0) > 0
    except (TypeError, ValueError):
        scheduled = True
    if isinstance(schedule_config, dict) and str(schedule_config.get("mode") or "manual") != "manual":
        scheduled = True
    if scheduled:
        violations.append("scheduled execution requires automation capability")
    if allow_multi_server is not False:
        violations.append("multi-server execution requires automation capability")
    try:
        if int(max_connections) != 1:
            violations.append("max_connections must be 1 without automation capability")
    except (TypeError, ValueError):
        violations.append("max_connections must be 1 without automation capability")
    try:
        iterations = int(max_iterations)
        if iterations < 1 or iterations > PILOT_MAX_ITERATIONS:
            violations.append(f"max_iterations must be between 1 and {PILOT_MAX_ITERATIONS}")
    except (TypeError, ValueError):
        violations.append(f"max_iterations must be between 1 and {PILOT_MAX_ITERATIONS}")
    try:
        timeout_seconds = int(session_timeout_seconds)
        if timeout_seconds < 30 or timeout_seconds > PILOT_MAX_SESSION_TIMEOUT_SECONDS:
            violations.append(f"session_timeout_seconds must be between 30 and {PILOT_MAX_SESSION_TIMEOUT_SECONDS}")
    except (TypeError, ValueError):
        violations.append(f"session_timeout_seconds must be between 30 and {PILOT_MAX_SESSION_TIMEOUT_SECONDS}")
    return violations


def pilot_agent_policy_violations_for_agent(
    *,
    user,
    agent,
    servers: Iterable[Any] | None = None,
    request=None,
) -> list[str]:
    """Evaluate the effective persisted agent configuration at every launch boundary."""
    effective_servers = list(servers) if servers is not None else list(agent.servers.all())
    return pilot_agent_policy_violations(
        user=user,
        servers=effective_servers,
        tools_config=agent.tools_config,
        sudo_policy=agent.sudo_policy,
        schedule_minutes=agent.schedule_minutes,
        schedule_config=agent.schedule_config,
        allow_multi_server=agent.allow_multi_server,
        max_connections=agent.max_connections,
        max_iterations=agent.max_iterations,
        session_timeout_seconds=agent.session_timeout_seconds,
        request=request,
    )
