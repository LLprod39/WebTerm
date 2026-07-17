"""Per-profile Operator policy (pilot = read + confirm-mutate only)."""

from __future__ import annotations

from typing import Any

from core_ui.access import feature_allowed_for_user
from core_ui.models import AssistantAction

# Tools that pilot-restricted users must never see (even if feature gate passes).
PILOT_BLOCKED_ACTION_PREFIXES = (
    "studio.",
    "kubernetes.",
    "mars.",
)


def is_pilot_restricted_operator(user) -> bool:
    """True for non-staff users without admin/studio elevation.

    Aligns with pilot_user: can operate servers/agents via chat when orchestrator
    is granted, but only read tools + confirmed mutates — never free-fire.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return True
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return False
    # Elevated if they have studio or settings (team admin-ish)
    return not (feature_allowed_for_user(user, "studio") or feature_allowed_for_user(user, "settings"))


def filter_tools_for_policy(user, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not is_pilot_restricted_operator(user):
        return tools
    out: list[dict[str, Any]] = []
    for tool in tools:
        action_type = str(tool.get("action_type") or tool.get("name") or "")
        if any(action_type.startswith(p) for p in PILOT_BLOCKED_ACTION_PREFIXES):
            continue
        risk = str(tool.get("risk") or "read")
        # Pilot: only read OR tools that require confirmation (mutate gated)
        if risk == "read" and not tool.get("requires_confirmation"):
            out.append(tool)
            continue
        # Force confirmation flag on non-read
        entry = dict(tool)
        entry["requires_confirmation"] = True
        # Drop pure external/unconfirmed dangerous without confirm path
        if risk == AssistantAction.RISK_DANGEROUS:
            entry["description"] = (
                str(entry.get("description") or "")
                + " [pilot: typed_confirm required]"
            )
        out.append(entry)
    return out


def pilot_policy_note(user) -> str:
    if not is_pilot_restricted_operator(user):
        return ""
    return (
        "Operator policy: pilot mode — only read tools auto-run; "
        "all mutations require operator confirmation (and typed confirm for destructive)."
    )
