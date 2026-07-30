from __future__ import annotations

import asyncio
import logging
from threading import Event
from typing import Any

from asgiref.sync import sync_to_async as _s2a

from studio.models import PipelineRun

logger = logging.getLogger(__name__)


def _node_data(node: dict[str, Any] | None) -> dict[str, Any]:
    data = (node or {}).get("data")
    return data if isinstance(data, dict) else {}


def evaluate_logic_condition(node_data: dict[str, Any], node_outputs: dict[str, dict]) -> dict[str, Any]:
    """Evaluate a condition node against previous node output."""
    source_node_id = str(node_data.get("source_node_id") or "")
    source_state = node_outputs.get(source_node_id, {})
    source_output = str(source_state.get("output") or "")

    check_type = str(node_data.get("check_type") or "contains")
    check_value = str(node_data.get("check_value") or "")

    passed = False
    if check_type == "contains":
        passed = check_value.lower() in source_output.lower()
    elif check_type == "not_contains":
        passed = check_value.lower() not in source_output.lower()
    elif check_type == "status_ok":
        passed = source_state.get("status") == "completed"
    elif check_type == "status_failed":
        passed = source_state.get("status") == "failed"
    elif check_type == "always_true":
        passed = True

    return {"status": "completed", "passed": passed, "output": str(passed)}


async def execute_logic_condition(
    node: dict[str, Any],
    context: dict[str, Any],
    node_outputs: dict[str, dict],
    run: PipelineRun | None = None,
) -> dict[str, Any]:
    return evaluate_logic_condition(_node_data(node), node_outputs)


async def execute_logic_wait_node(
    node_id: str,
    node_data: dict[str, Any],
    run_id: int,
    stop_event: Event | None = None,
) -> dict[str, Any]:
    """Pause pipeline execution for a configurable number of minutes."""
    try:
        minutes = float(node_data.get("wait_minutes", 1))
    except (TypeError, ValueError):
        minutes = 1.0

    minutes = max(0.1, min(minutes, 1440))
    logger.info("logic/wait node %s: sleeping %.1f minutes", node_id, minutes)

    remaining_seconds = minutes * 60
    while remaining_seconds > 0:
        if stop_event and stop_event.is_set():
            return {"status": "stopped", "output": "Wait cancelled by stop request", "stopped": True}

        fresh_status = await _s2a(
            lambda: PipelineRun.objects.filter(pk=run_id).values_list("status", flat=True).first(),
            thread_sensitive=False,
        )()
        if fresh_status == PipelineRun.STATUS_STOPPED:
            return {"status": "stopped", "output": "Wait cancelled by stop request", "stopped": True}

        sleep_seconds = min(1.0, remaining_seconds)
        await asyncio.sleep(sleep_seconds)
        remaining_seconds -= sleep_seconds

    return {"status": "completed", "output": f"⏱️ Ожидание завершено: {minutes:.1f} мин."}


async def execute_logic_wait(
    node: dict[str, Any],
    context: dict[str, Any],
    run: PipelineRun,
    stop_event: Event | None = None,
) -> dict[str, Any]:
    return await execute_logic_wait_node(
        str((node or {}).get("id") or ""),
        _node_data(node),
        run.pk,
        stop_event,
    )


def logic_merge_result(node_data: dict[str, Any]) -> dict[str, Any]:
    mode = str(node_data.get("mode") or "all").strip().lower()
    if mode not in {"all", "any"}:
        mode = "all"

    mode_label = "любая ветка" if mode == "any" else "все ветки"
    return {"status": "completed", "output": f"объединение: {mode_label}"}


async def execute_logic_merge(
    node: dict[str, Any],
    context: dict[str, Any],
    node_outputs: dict[str, dict],
    run: PipelineRun | None = None,
) -> dict[str, Any]:
    return logic_merge_result(_node_data(node))
