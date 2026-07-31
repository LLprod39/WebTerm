"""Database-backed pipeline runtime control shared by every process."""

from __future__ import annotations

from typing import Any

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
    stop_requested: bool | None = None,
) -> dict[str, Any]:
    control = build_runtime_control_state(getattr(run, "runtime_control", None))

    if stop_requested is not None:
        control["stop_requested"] = bool(stop_requested)

    run.runtime_control = control
    run.save(update_fields=["runtime_control"])
    return control
