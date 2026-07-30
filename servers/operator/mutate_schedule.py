"""Operator mutate tools: agent scheduling and undo of the last action (F-08a split)."""

from __future__ import annotations

from typing import Any

from app.assistant_actions import AssistantActionContext, AssistantActionError
from servers.operator.mutate_exec import run_command
from servers.operator.tools_common import _int_arg


def _hhmm_or_none(value: Any) -> str | None:
    """Return a normalized HH:MM string, or None when the input isn't a valid time."""
    text = str(value or "").strip()
    if not text or ":" not in text:
        return None
    try:
        hour, minute = (int(part) for part in text.split(":", 1))
    except (TypeError, ValueError):
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return f"{hour:02d}:{minute:02d}"
    return None


def _cron_to_schedule_config(cron: str) -> dict[str, Any]:
    """Map a simple 5-field cron (m h dom mon dow) to normalize_schedule_config keys.

    Handles the common daily/weekly forms; returns {} when it can't parse cleanly.
    """
    parts = cron.split()
    if len(parts) != 5:
        return {}
    minute, hour, dom, _mon, dow = parts
    if not (minute.isdigit() and hour.isdigit()):
        return {}
    time_str = f"{int(hour):02d}:{int(minute):02d}"
    if dow not in ("*", "?"):
        weekdays: list[int] = []
        for token in dow.split(","):
            # cron dow: 0/7 = Sunday; normalize uses Mon=0..Sun=6.
            if token.isdigit():
                cron_dow = int(token) % 7
                weekdays.append((cron_dow + 6) % 7)
        if weekdays:
            return {"mode": "weekly", "time": time_str, "weekdays": sorted(set(weekdays))}
    if dom.isdigit():
        return {"mode": "monthly", "time": time_str, "day_of_month": int(dom)}
    return {"mode": "daily", "time": time_str}


def schedule_agent(ctx: AssistantActionContext) -> dict[str, Any]:
    """Attach a schedule to an existing agent (phrase → cron-ish config)."""
    from core_ui.projects import active_project_for_user
    from servers.agents.agent_schedule import normalize_schedule_config, schedule_minutes_for_config
    from servers.models import ServerAgent

    agent_id = _int_arg(ctx, "agent_id")
    assert agent_id is not None
    agent = ServerAgent.objects.filter(pk=agent_id, user=ctx.user, project=active_project_for_user(ctx.user)).first()
    if agent is None:
        raise AssistantActionError("Agent not found", status=404)

    schedule_minutes = 0
    try:
        schedule_minutes = int(ctx.input_payload.get("schedule_minutes") or 0)
    except (TypeError, ValueError):
        schedule_minutes = 0

    raw_config = ctx.input_payload.get("schedule_config")
    raw_config = dict(raw_config) if isinstance(raw_config, dict) else {}

    # Friendly inputs → the canonical keys normalize_schedule_config actually reads
    # (mode / time / interval_minutes / weekdays). The previous mapping used type/
    # minutes/hour, which normalize ignored — every schedule silently became "manual".
    cron = str(ctx.input_payload.get("cron") or "").strip()
    daily_hour = ctx.input_payload.get("daily_hour")
    daily_time = _hhmm_or_none(ctx.input_payload.get("daily_time"))
    weekdays_in = ctx.input_payload.get("weekdays")

    if daily_time is None and daily_hour is not None:
        try:
            daily_time = f"{max(0, min(23, int(daily_hour))):02d}:00"
        except (TypeError, ValueError):
            daily_time = None

    if isinstance(weekdays_in, list) and weekdays_in:
        raw_config["mode"] = "weekly"
        raw_config["weekdays"] = weekdays_in
        if daily_time:
            raw_config["time"] = daily_time
    elif daily_time:
        raw_config.setdefault("mode", "daily")
        raw_config["time"] = daily_time
    elif cron:
        raw_config.update(_cron_to_schedule_config(cron))
    elif schedule_minutes > 0 and not raw_config.get("mode"):
        raw_config["mode"] = "interval"
        raw_config["interval_minutes"] = schedule_minutes

    config = normalize_schedule_config(raw_config, fallback_minutes=schedule_minutes)
    minutes = schedule_minutes_for_config(config, schedule_minutes)
    agent.schedule_config = config
    agent.schedule_minutes = minutes
    agent.is_enabled = True
    agent.save(update_fields=["schedule_config", "schedule_minutes", "is_enabled", "updated_at"])

    deliver_to_chat = bool(ctx.input_payload.get("deliver_to_chat"))
    if deliver_to_chat:
        delivery = agent.report_delivery if isinstance(agent.report_delivery, dict) else {}
        delivery = {
            **delivery,
            "chat": {"enabled": True, "note": "Deliver report summary to operator chat when available"},
        }
        agent.report_delivery = delivery
        agent.save(update_fields=["report_delivery", "updated_at"])

    return {
        "ok": True,
        "agent": {"id": agent.id, "name": agent.name},
        "schedule_config": config,
        "schedule_minutes": minutes,
        "deliver_to_chat": deliver_to_chat,
        "target_url": "/agents",
    }


def undo_last_action(ctx: AssistantActionContext) -> dict[str, Any]:
    """Execute reverse command from a prior action's undo_payload."""
    from core_ui.models import AssistantAction

    action_id = _int_arg(ctx, "action_id", required=False)
    if action_id:
        action = AssistantAction.objects.filter(pk=action_id, user=ctx.user).first()
    else:
        action = (
            AssistantAction.objects.filter(user=ctx.user, status=AssistantAction.STATUS_COMPLETED)
            .exclude(undo_payload={})
            .order_by("-completed_at", "-id")
            .first()
        )
    if action is None or not action.undo_payload:
        raise AssistantActionError("No undoable action found")
    undo = action.undo_payload if isinstance(action.undo_payload, dict) else {}
    server_id = undo.get("server_id")
    command = str(undo.get("command") or "").strip()
    if not server_id or not command:
        raise AssistantActionError("Undo payload incomplete")
    # Reuse run_command path
    nested = AssistantActionContext(
        user=ctx.user,
        input_payload={"server_id": server_id, "command": command, "allow_destructive": True},
        request=ctx.request,
        source=ctx.source,
    )
    result = run_command(nested)
    result["undid_action_id"] = action.pk
    return result
