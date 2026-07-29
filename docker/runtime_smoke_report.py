from __future__ import annotations

import statistics
from typing import Any


def _flatten(items: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for item in items:
        values.extend(float(value) for value in item.get(key, []))
    return values


def build_runtime_smoke_summary(results: list[dict[str, Any]], *, elapsed: float) -> dict[str, Any]:
    terminal_latencies = _flatten(results, "terminal_latencies")
    pipeline_latencies = _flatten(results, "pipeline_latencies")
    agent_latencies = _flatten(results, "agent_latencies")
    return {
        "users": len(results),
        "terminal_sessions_total": len(terminal_latencies),
        "pipeline_runs_total": len(pipeline_latencies),
        "agent_runs_total": len(agent_latencies),
        "elapsed_seconds": round(elapsed, 3),
        "terminal_latency_avg": round(statistics.mean(terminal_latencies), 3) if terminal_latencies else 0.0,
        "terminal_latency_max": round(max(terminal_latencies), 3) if terminal_latencies else 0.0,
        "pipeline_latency_avg": round(statistics.mean(pipeline_latencies), 3) if pipeline_latencies else 0.0,
        "pipeline_latency_max": round(max(pipeline_latencies), 3) if pipeline_latencies else 0.0,
        "agent_latency_avg": round(statistics.mean(agent_latencies), 3) if agent_latencies else 0.0,
        "agent_latency_max": round(max(agent_latencies), 3) if agent_latencies else 0.0,
        "results": results,
    }
