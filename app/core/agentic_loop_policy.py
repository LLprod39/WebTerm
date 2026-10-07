"""Shared policy helpers for model-driven agentic LLM loops.

Used by Operator (and optionally Ops agents) so continuation / early-stop
guards are not copy-pasted keyword stacks. Keyword heuristics remain a
fallback in product loops; this module owns the primary self-check contract.
"""

from __future__ import annotations

import re
from typing import Any

MAX_GOAL_SELF_CHECKS = 1

GOAL_SELF_CHECK_NUDGE = (
    "Self-check before ending the turn: is the user goal fully answered with "
    "tool evidence? If not, call the next needed tool now (for host checks: "
    "operator.read_command / server.diagnostics.overview on the resolved "
    "server_id — e.g. systemctl list-units --type=service --state=running, "
    "docker ps, ss -tlnp, journalctl). "
    "If the goal is complete, call operator.finish_report with a short summary "
    "or give the final report. Do not ask «что дальше?»."
)

_HOST_MENTION_RE = re.compile(r"@[\w.\-]+", re.UNICODE)


def messages_have_host_mention(text: str) -> bool:
    """True when the user message names a host via @mention."""
    return bool(_HOST_MENTION_RE.search(str(text or "")))


def should_goal_self_check(
    *,
    tools_executed: bool,
    self_checks_used: int,
    has_task_evidence: bool,
    inventory_only: bool,
    host_ops_goal: bool,
    host_mention: bool,
    max_self_checks: int = MAX_GOAL_SELF_CHECKS,
) -> bool:
    """One-shot model-driven guard when the model stops early after tools.

    Intermediate text after tool results is progress, not a final answer, until
    we have real task evidence (e.g. SSH) or the model explicitly finishes.
    """
    if not tools_executed:
        return False
    if has_task_evidence:
        return False
    if self_checks_used >= max_self_checks:
        return False
    # Host-ops / @host / stuck on inventory → ask the model once.
    return bool(inventory_only or host_ops_goal or host_mention)


def assistant_called_finish_tool(tool_calls: list[dict[str, Any]] | None) -> bool:
    """True when this model step includes operator.finish_report (any name shape)."""
    for call in tool_calls or []:
        raw = str(call.get("name") or "").strip().lower().replace("-", "_")
        underscored = raw.replace(".", "_")
        if underscored in {"operator_finish_report", "finish_report"}:
            return True
    return False
