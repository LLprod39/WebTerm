from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from servers.models import ServerAgent

SCHEDULE_MODES = {"manual", "interval", "daily", "weekly", "monthly", "once"}


def _positive_int(value, default: int = 0, *, lo: int = 0, hi: int = 10080) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(lo, min(hi, parsed))


def _hhmm(value: str | None, default: str = "09:00") -> str:
    text = str(value or default).strip()
    try:
        hour, minute = [int(part) for part in text.split(":", 1)]
    except Exception:
        return default
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return default
    return f"{hour:02d}:{minute:02d}"


def _tz(name: str | None) -> ZoneInfo:
    fallback = getattr(settings, "TIME_ZONE", "UTC") or "UTC"
    try:
        return ZoneInfo(str(name or fallback))
    except Exception:
        return ZoneInfo(fallback)


def _local(now, tz_name: str | None):
    return timezone.localtime(now or timezone.now(), _tz(tz_name))


def _combine(local_date, hhmm: str, tz: ZoneInfo):
    hour, minute = [int(part) for part in hhmm.split(":", 1)]
    return datetime.combine(local_date, time(hour, minute), tzinfo=tz)


def normalize_schedule_config(raw, *, fallback_minutes: int = 0) -> dict:
    data = raw if isinstance(raw, dict) else {}
    mode = str(data.get("mode") or "").strip().lower()
    if mode not in SCHEDULE_MODES:
        mode = "interval" if fallback_minutes else "manual"

    tz_name = str(data.get("timezone") or getattr(settings, "TIME_ZONE", "UTC") or "UTC")
    interval_minutes = _positive_int(
        data.get("interval_minutes", fallback_minutes),
        fallback_minutes,
        lo=0,
        hi=10080,
    )
    if mode == "interval" and interval_minutes <= 0:
        mode = "manual"

    weekdays = []
    for item in data.get("weekdays") or []:
        value = _positive_int(item, -1, lo=-1, hi=6)
        if 0 <= value <= 6 and value not in weekdays:
            weekdays.append(value)

    normalized = {
        "mode": mode,
        "timezone": tz_name,
        "interval_minutes": interval_minutes if mode == "interval" else 0,
        "time": _hhmm(data.get("time")),
        "weekdays": sorted(weekdays),
        "day_of_month": _positive_int(data.get("day_of_month"), 1, lo=1, hi=31),
        "run_at": str(data.get("run_at") or "").strip(),
    }

    if mode == "weekly" and not normalized["weekdays"]:
        normalized["weekdays"] = [0, 1, 2, 3, 4]
    return normalized


def schedule_minutes_for_config(config: dict, fallback_minutes: int = 0) -> int:
    mode = (config or {}).get("mode")
    if mode == "manual":
        return 0
    if mode == "interval":
        return _positive_int((config or {}).get("interval_minutes"), fallback_minutes, lo=1, hi=10080)
    if mode == "daily":
        return 1440
    if mode == "weekly":
        return 10080
    if mode == "monthly":
        return 10080
    if mode == "once":
        return 1
    return _positive_int(fallback_minutes, 0)


def _last_run_at_or_min(agent: ServerAgent, tz: ZoneInfo):
    if not agent.last_run_at:
        return None
    return timezone.localtime(agent.last_run_at, tz)


def _once_datetime(config: dict, tz: ZoneInfo):
    value = str(config.get("run_at") or "").strip()
    parsed = parse_datetime(value) if value else None
    if not parsed:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, tz)
    return parsed.astimezone(tz)


def _candidate_is_due(agent: ServerAgent, candidate, now_local) -> bool:
    if now_local < candidate:
        return False
    last_run = _last_run_at_or_min(agent, candidate.tzinfo)
    return last_run is None or last_run < candidate


def is_agent_due_by_schedule(agent: ServerAgent, now=None) -> bool:
    current_time = now or timezone.now()
    if not agent.is_enabled:
        return False

    config = normalize_schedule_config(
        getattr(agent, "schedule_config", None), fallback_minutes=int(agent.schedule_minutes or 0)
    )
    mode = config["mode"]
    if mode == "manual":
        return False
    if mode == "interval":
        minutes = schedule_minutes_for_config(config, int(agent.schedule_minutes or 0))
        if minutes <= 0:
            return False
        if agent.last_run_at is None:
            return True
        return agent.last_run_at <= current_time - timedelta(minutes=minutes)

    tz = _tz(config.get("timezone"))
    now_local = _local(current_time, config.get("timezone"))

    if mode == "daily":
        return _candidate_is_due(agent, _combine(now_local.date(), config["time"], tz), now_local)

    if mode == "weekly":
        if now_local.weekday() not in config["weekdays"]:
            return False
        return _candidate_is_due(agent, _combine(now_local.date(), config["time"], tz), now_local)

    if mode == "monthly":
        if now_local.day != int(config["day_of_month"]):
            return False
        return _candidate_is_due(agent, _combine(now_local.date(), config["time"], tz), now_local)

    if mode == "once":
        run_at = _once_datetime(config, tz)
        if not run_at:
            return False
        return _candidate_is_due(agent, run_at, now_local)

    return False


def compute_next_due_by_schedule(agent: ServerAgent, now=None):
    current_time = now or timezone.now()
    config = normalize_schedule_config(
        getattr(agent, "schedule_config", None), fallback_minutes=int(agent.schedule_minutes or 0)
    )
    mode = config["mode"]
    if mode == "manual" or not agent.is_enabled:
        return None
    if is_agent_due_by_schedule(agent, current_time):
        return current_time
    if mode == "interval":
        minutes = schedule_minutes_for_config(config, int(agent.schedule_minutes or 0))
        if minutes <= 0:
            return None
        if agent.last_run_at is None:
            return current_time
        return agent.last_run_at + timedelta(minutes=minutes)

    tz = _tz(config.get("timezone"))
    now_local = _local(current_time, config.get("timezone"))
    last_run = _last_run_at_or_min(agent, tz)

    if mode == "once":
        run_at = _once_datetime(config, tz)
        if not run_at:
            return None
        return None if last_run and last_run >= run_at else run_at.astimezone(timezone.get_current_timezone())

    for offset in range(0, 370 if mode == "monthly" else 14):
        local_date = now_local.date() + timedelta(days=offset)
        if mode == "weekly" and local_date.weekday() not in config["weekdays"]:
            continue
        if mode == "monthly" and local_date.day != int(config["day_of_month"]):
            continue
        candidate = _combine(local_date, config["time"], tz)
        if candidate < now_local:
            continue
        if last_run and last_run >= candidate:
            continue
        return candidate.astimezone(timezone.get_current_timezone())
    return None
