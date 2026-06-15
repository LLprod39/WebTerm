from __future__ import annotations

from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

try:
    from croniter import croniter
except ModuleNotFoundError:  # pragma: no cover - optional dependency in local mini env
    croniter = None


_FIELD_RANGES = (
    (0, 59),  # minute
    (0, 23),  # hour
    (1, 31),  # day of month
    (1, 12),  # month
    (0, 7),  # weekday; 0 and 7 are Sunday
)


def _parse_cron_field(raw_value: str, *, min_value: int, max_value: int, normalize_weekday: bool = False) -> set[int]:
    values: set[int] = set()
    raw_parts = [part.strip() for part in str(raw_value or "").split(",") if part.strip()]
    if not raw_parts:
        raise ValueError("empty field")

    for part in raw_parts:
        if "/" in part:
            range_part, step_part = part.split("/", 1)
            try:
                step = int(step_part)
            except ValueError as exc:
                raise ValueError(f"invalid step '{step_part}'") from exc
            if step <= 0:
                raise ValueError("step must be positive")
        else:
            range_part = part
            step = 1

        if range_part == "*":
            start, end = min_value, max_value
        elif "-" in range_part:
            start_raw, end_raw = range_part.split("-", 1)
            start, end = int(start_raw), int(end_raw)
        else:
            start = end = int(range_part)

        if start < min_value or end > max_value or start > end:
            raise ValueError(f"value outside allowed range {min_value}-{max_value}")

        values.update(range(start, end + 1, step))

    if normalize_weekday:
        values = {0 if value == 7 else value for value in values}
    return values


def _parse_fallback_cron(expression: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    fields = [part for part in str(expression or "").split() if part]
    if len(fields) != 5:
        raise ValueError("cron expression must contain 5 fields")

    parsed: list[set[int]] = []
    for index, field in enumerate(fields):
        min_value, max_value = _FIELD_RANGES[index]
        parsed.append(
            _parse_cron_field(
                field,
                min_value=min_value,
                max_value=max_value,
                normalize_weekday=index == 4,
            )
        )
    return parsed[0], parsed[1], parsed[2], parsed[3], parsed[4]


def validate_cron_expression(expression: str) -> tuple[bool, str]:
    cron_expression = str(expression or "").strip()
    if not cron_expression:
        return True, ""
    if croniter is not None:
        try:
            croniter(cron_expression)
            return True, ""
        except Exception as exc:
            return False, str(exc)

    try:
        _parse_fallback_cron(cron_expression)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def _matches_fallback_cron(
    candidate: datetime,
    *,
    minutes: set[int],
    hours: set[int],
    month_days: set[int],
    months: set[int],
    weekdays: set[int],
) -> bool:
    if candidate.minute not in minutes or candidate.hour not in hours or candidate.month not in months:
        return False

    cron_weekday = (candidate.weekday() + 1) % 7
    month_day_matches = candidate.day in month_days
    weekday_matches = cron_weekday in weekdays
    month_day_is_wildcard = month_days == set(range(1, 32))
    weekday_is_wildcard = weekdays == set(range(0, 7))

    if not month_day_is_wildcard and not weekday_is_wildcard:
        return month_day_matches or weekday_matches
    return month_day_matches and weekday_matches


def previous_due_datetime(expression: str, now: datetime, *, croniter_factory=None) -> datetime:
    cron_expression = str(expression or "").strip()
    if not cron_expression:
        raise ValueError("cron expression is empty")

    effective_croniter = croniter if croniter_factory is None else croniter_factory
    if effective_croniter is not None:
        previous_due_ts = effective_croniter(cron_expression, now).get_prev(float)
        previous_due_dt = datetime.fromtimestamp(previous_due_ts, tz=dt_timezone.utc)
        if now.tzinfo is not None:
            previous_due_dt = previous_due_dt.astimezone(now.tzinfo)
        return previous_due_dt

    minutes, hours, month_days, months, weekdays = _parse_fallback_cron(cron_expression)
    candidate = now.replace(second=0, microsecond=0)
    if candidate >= now:
        candidate -= timedelta(minutes=1)

    deadline = candidate - timedelta(days=366)
    while candidate >= deadline:
        if _matches_fallback_cron(
            candidate,
            minutes=minutes,
            hours=hours,
            month_days=month_days,
            months=months,
            weekdays=weekdays,
        ):
            return candidate
        candidate -= timedelta(minutes=1)

    raise ValueError("could not find a previous due time within 366 days")
