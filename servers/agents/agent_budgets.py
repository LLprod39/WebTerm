"""Shared agent runtime budget defaults and caps.

These constants are the single source of truth for Full / Multi / Nova / Fast
defaults that gate long-running complex ops. Hard caps remain so runaway
loops stay bounded even when agent settings are misconfigured.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Full ReAct agent (Agents tab → Полный)
# ---------------------------------------------------------------------------

FULL_DEFAULT_MAX_ITERATIONS = 40
FULL_MAX_ITERATIONS_CAP = 100
FULL_DEFAULT_SESSION_TIMEOUT_SEC = 1200
FULL_DEFAULT_COMMAND_TIMEOUT_SEC = 90
FULL_COMMAND_TIMEOUT_CAP_SEC = 300

# ---------------------------------------------------------------------------
# Multi-agent pipeline (Agents tab → Пайплайн / multi)
# ---------------------------------------------------------------------------

MULTI_MAX_PLAN_TASKS = 15
MULTI_MAX_TASK_ITERATIONS = 12
MULTI_DEFAULT_SESSION_TIMEOUT_SEC = 1800
MULTI_DEFAULT_COMMAND_TIMEOUT_SEC = 90

# ---------------------------------------------------------------------------
# Nova (SSH terminal agent mode)
# ---------------------------------------------------------------------------

NOVA_DEFAULT_MAX_ITERATIONS = 30
NOVA_COMPLEX_MAX_ITERATIONS = 50
NOVA_DEFAULT_TOTAL_TIMEOUT_SEC = 1800
NOVA_COMPLEX_TOTAL_TIMEOUT_SEC = 2700
NOVA_DEFAULT_ITERATION_TIMEOUT_SEC = 180.0
NOVA_COMPACT_AFTER_TURNS = 20
NOVA_MAX_HISTORY_TURNS = 30

# ---------------------------------------------------------------------------
# Fast / step planner (SSH terminal plan-then-execute)
# ---------------------------------------------------------------------------

FAST_PLANNER_COMMAND_CAP = 10
FAST_PLANNER_COMMAND_HARD_MAX = 12


@dataclass(frozen=True)
class AgentRuntimeBudget:
    max_iterations: int
    session_timeout_seconds: int
    max_connections: int


def resolve_agent_runtime_budget(*, mode: str, goal: str = "", system_prompt: str = "", commands=None, skill_slugs=None, input_artifacts=None) -> AgentRuntimeBudget:
    """Choose a bounded runtime budget from task complexity, without asking end users."""
    complexity = len((goal or "").strip()) + len((system_prompt or "").strip())
    complexity += 180 * len(commands or []) + 220 * len(skill_slugs or []) + 240 * len(input_artifacts or [])
    if mode == "multi" or complexity >= 1200:
        return AgentRuntimeBudget(max_iterations=60, session_timeout_seconds=1800, max_connections=5)
    if complexity >= 400:
        return AgentRuntimeBudget(max_iterations=50, session_timeout_seconds=1500, max_connections=3)
    return AgentRuntimeBudget(max_iterations=40, session_timeout_seconds=1200, max_connections=1)


def clamp_command_timeout(seconds: int | float | None, *, default: int = FULL_DEFAULT_COMMAND_TIMEOUT_SEC) -> int:
    """Normalize a command timeout into [1, FULL_COMMAND_TIMEOUT_CAP_SEC]."""
    try:
        value = int(seconds) if seconds is not None else int(default)
    except (TypeError, ValueError):
        value = int(default)
    return max(1, min(value, FULL_COMMAND_TIMEOUT_CAP_SEC))


def clamp_full_iterations(value: int | None) -> int:
    try:
        raw = int(value) if value is not None else FULL_DEFAULT_MAX_ITERATIONS
    except (TypeError, ValueError):
        raw = FULL_DEFAULT_MAX_ITERATIONS
    return max(1, min(raw, FULL_MAX_ITERATIONS_CAP))


# Re-export budget profiles used by UI / optional API (see agent_runtime_guidance).
def full_budget_profiles() -> dict[str, dict[str, int]]:
    from servers.agents.agent_runtime_guidance import FULL_BUDGET_PROFILES

    return {key: dict(value) for key, value in FULL_BUDGET_PROFILES.items()}
