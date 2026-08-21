"""Operator policy derived from centrally managed automation access."""

from __future__ import annotations

from typing import Any

from servers.agents.agent_pilot_policy import user_can_automate

# Tools that pilot-restricted users must never see (even if feature gate passes).
PILOT_BLOCKED_ACTION_PREFIXES = (
    "studio.",
    "kubernetes.",
    "mars.",
)


def is_pilot_restricted_operator(user) -> bool:
    """Users without live automation access receive read-only tools."""
    if not user or not getattr(user, "is_authenticated", False):
        return True
    return not user_can_automate(user)


def filter_tools_for_policy(user, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not is_pilot_restricted_operator(user):
        return tools
    out: list[dict[str, Any]] = []
    for tool in tools:
        action_type = str(tool.get("action_type") or tool.get("name") or "")
        if any(action_type.startswith(p) for p in PILOT_BLOCKED_ACTION_PREFIXES):
            continue
        risk = str(tool.get("risk") or "read")
        if risk == "read":
            out.append(tool)
    return out


def pilot_policy_note(user) -> str:
    if not is_pilot_restricted_operator(user):
        return ""
    return (
        "Operator policy: only read tools are available; "
        "mutating tools require the automation capability."
    )
