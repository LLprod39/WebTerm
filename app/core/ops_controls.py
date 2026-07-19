"""Global ops controls: kill switch for scheduled pipelines/agents and new agent runs."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from django.conf import settings

_FLAG_ENV = "WEBTERM_OPS_PAUSE_ALL"
_REASON_ENV = "WEBTERM_OPS_PAUSE_REASON"
_DEFAULT_RELATIVE = Path("runtime_logs") / "ops_kill_switch.json"


def kill_switch_path() -> Path:
    configured = str(os.getenv("WEBTERM_OPS_KILL_SWITCH_PATH") or "").strip()
    if configured:
        return Path(configured)
    base = Path(getattr(settings, "BASE_DIR", Path.cwd()))
    return base / _DEFAULT_RELATIVE


def _read_flag_file() -> dict[str, Any]:
    path = kill_switch_path()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def is_ops_paused() -> bool:
    env_flag = str(os.getenv(_FLAG_ENV) or "").strip().lower()
    if env_flag in {"1", "true", "yes", "on"}:
        return True
    data = _read_flag_file()
    return bool(data.get("paused"))


def ops_pause_reason() -> str:
    env_reason = str(os.getenv(_REASON_ENV) or "").strip()
    if env_reason:
        return env_reason
    data = _read_flag_file()
    return str(data.get("reason") or "Global ops kill switch is active").strip()


def assert_agents_not_paused() -> str | None:
    """Return error message if new agent work must not start, else None."""
    if not is_ops_paused():
        return None
    return (
        f"Agent execution paused by global kill switch: {ops_pause_reason()}. "
        "Clear with `python manage.py ops_kill_switch --resume` or unset WEBTERM_OPS_PAUSE_ALL."
    )


def assert_schedulers_not_paused() -> str | None:
    if not is_ops_paused():
        return None
    return f"Schedulers paused by global kill switch: {ops_pause_reason()}"


def set_ops_paused(paused: bool, *, reason: str = "", actor: str = "") -> dict[str, Any]:
    path = kill_switch_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "paused": bool(paused),
        "reason": str(reason or ("Paused by operator" if paused else "")).strip(),
        "actor": str(actor or "").strip(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def get_ops_control_status() -> dict[str, Any]:
    data = _read_flag_file()
    return {
        "paused": is_ops_paused(),
        "reason": ops_pause_reason() if is_ops_paused() else "",
        "path": str(kill_switch_path()),
        "env_override": str(os.getenv(_FLAG_ENV) or "").strip().lower() in {"1", "true", "yes", "on"},
        "file": data,
    }
