"""Agent engine runner entrypoint.

F-08a.10: the ReAct loop body lives in ``agent_engine_runner_loop``.
This module re-exports ``run_agent_engine`` for a stable import path.
"""

from __future__ import annotations

from servers.agent_engine_runner_loop import run_agent_engine

__all__ = ["run_agent_engine"]
