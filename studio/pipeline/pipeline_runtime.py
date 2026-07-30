"""
In-process registry for live pipeline executor instances.

HTTP views and WebSocket consumers use this registry to deliver stop signals
to the currently running executor for a pipeline run.
"""

from __future__ import annotations

from threading import RLock
from typing import Any

_LOCK = RLock()
_EXECUTORS_BY_RUN_ID: dict[int, Any] = {}
DEFAULT_RUNTIME_CONTROL = {
    "stop_requested": False,
}


def build_runtime_control_state(raw: Any | None = None) -> dict[str, Any]:
    control = dict(DEFAULT_RUNTIME_CONTROL)
    if not isinstance(raw, dict):
        return control
    control["stop_requested"] = bool(raw.get("stop_requested"))
    return control


def reset_runtime_control_state() -> dict[str, Any]:
    return dict(DEFAULT_RUNTIME_CONTROL)


def is_runtime_stop_requested(run_or_control: Any | None) -> bool:
    raw = getattr(run_or_control, "runtime_control", run_or_control)
    control = build_runtime_control_state(raw)
    return bool(control["stop_requested"])


def update_runtime_control(
    run,
    *,
    live_executor: Any | None = None,
    stop_requested: bool | None = None,
) -> tuple[dict[str, Any], bool]:
    control = build_runtime_control_state(getattr(run, "runtime_control", None))

    if stop_requested is not None:
        control["stop_requested"] = bool(stop_requested)

    stop_delivered = False
    if live_executor is not None and stop_requested is True:
        live_executor.request_stop()
        stop_delivered = True

    run.runtime_control = control
    run.save(update_fields=["runtime_control"])
    return control, stop_delivered


def register_executor(run_id: int, executor: Any) -> None:
    with _LOCK:
        _EXECUTORS_BY_RUN_ID[int(run_id)] = executor


def unregister_executor(run_id: int, executor: Any | None = None) -> None:
    run_id = int(run_id)
    with _LOCK:
        current = _EXECUTORS_BY_RUN_ID.get(run_id)
        if current is None:
            return
        if executor is not None and current is not executor:
            return
        _EXECUTORS_BY_RUN_ID.pop(run_id, None)


def get_executor_for_run(run_id: int) -> Any | None:
    with _LOCK:
        return _EXECUTORS_BY_RUN_ID.get(int(run_id))
