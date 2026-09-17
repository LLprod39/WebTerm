"""Operator duty session: morning briefing and proactive chat posts."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib.auth.models import User
from django.utils import timezone
from loguru import logger

from core_ui.access import feature_allowed_for_user
from core_ui.models import ChatMessage, ChatSession

DEFAULT_BRIEFING_HOUR = 9  # local server time
MIN_HOURS_BETWEEN_BRIEFINGS = 20


def get_or_create_duty_session(user: User) -> ChatSession:
    """Duty chat removed — do not create new sessions."""
    session = ChatSession.objects.filter(user=user, kind=ChatSession.KIND_DUTY).order_by("-updated_at").first()
    if session is not None:
        return session
    raise RuntimeError("Duty chat has been removed")


def duty_enabled(session: ChatSession) -> bool:
    return False


def set_duty_enabled(user: User, *, enabled: bool) -> ChatSession:
    raise RuntimeError("Duty chat has been removed")


def _collect_facts_for_user(user: User) -> dict[str, Any]:
    from app.agent_kernel import operator_provider_registry

    return operator_provider_registry.collect_duty_facts(
        user, include_agent_runs=feature_allowed_for_user(user, "agents")
    )


def render_briefing_markdown(facts: dict[str, Any], *, lang: str = "ru") -> str:
    counts = facts.get("status_counts") or {}
    worst = facts.get("worst") or []
    alerts = facts.get("open_alerts") or []
    preds = facts.get("predictions") or []
    runs = facts.get("agent_runs") or []

    lines = [
        "## Утренний брифинг дежурного" if lang == "ru" else "## Duty morning briefing",
        "",
        f"**Флот:** {facts.get('server_count', 0)} серверов · "
        f"healthy={counts.get('healthy', 0)}, warning={counts.get('warning', 0)}, "
        f"critical={counts.get('critical', 0)}, unreachable={counts.get('unreachable', 0)}",
    ]
    if worst:
        lines.append("")
        lines.append("**Худшие:**")
        for item in worst[:8]:
            lines.append(f"- `{item.get('name')}` — {item.get('status')}")
    else:
        lines.append("")
        lines.append("_Критических/warning хостов нет._" if lang == "ru" else "_No warning/critical hosts._")

    lines.append("")
    lines.append(f"**Открытые алерты (ночь/утро):** {len(alerts)}")
    for a in alerts[:8]:
        lines.append(f"- [{a.get('severity')}] `{a.get('server')}` — {a.get('title')}")

    lines.append("")
    lines.append(f"**Активные прогнозы:** {len(preds)}")
    for p in preds[:8]:
        eta = p.get("eta_days")
        eta_s = f"{eta:.1f}д" if isinstance(eta, (int, float)) else "?"
        lines.append(f"- [{p.get('severity')}] `{p.get('server')}` {p.get('kind')}/{p.get('target')} ETA {eta_s}")

    if runs:
        lines.append("")
        lines.append(f"**Раны агентов за период:** {len(runs)}")
        for r in runs[:8]:
            lines.append(f"- #{r.get('id')} {r.get('agent')} [{r.get('status')}] {r.get('server')}")

    lines.append("")
    if (
        alerts
        or any(w.get("status") in {"critical", "unreachable"} for w in worst)
        or any(p.get("severity") == "critical" for p in preds)
    ):
        lines.append(
            "Рекомендация: разберите critical/unreachable в чате (`/fleet` или «Разобрать в чате»)."
            if lang == "ru"
            else "Recommendation: triage critical/unreachable hosts in chat."
        )
    else:
        lines.append(
            "Ночь спокойная. Можно заняться плановой работой."
            if lang == "ru"
            else "Quiet night. Safe for planned work."
        )
    return "\n".join(lines)


def _should_brief_now(session: ChatSession, *, now=None, force: bool = False) -> bool:
    if force:
        return True
    if not duty_enabled(session):
        return False
    now = now or timezone.now()
    local = timezone.localtime(now)
    pinned = session.pinned_context if isinstance(session.pinned_context, dict) else {}
    hour = int(pinned.get("briefing_hour") or DEFAULT_BRIEFING_HOUR)
    if local.hour < hour:
        return False
    last = pinned.get("last_briefing_at")
    if last:
        try:
            from django.utils.dateparse import parse_datetime

            last_dt = parse_datetime(str(last))
            if last_dt is not None:
                if timezone.is_naive(last_dt):
                    last_dt = timezone.make_aware(last_dt, timezone.get_current_timezone())
                if now - last_dt < timedelta(hours=MIN_HOURS_BETWEEN_BRIEFINGS):
                    return False
        except Exception as exc:  # noqa: BLE001
            logger.debug("operator duty briefing timestamp ignored: {}", exc)
    return True


def post_duty_message(session: ChatSession, content: str, *, metadata: dict | None = None) -> ChatMessage:
    msg = ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content=content,
        metadata={"source": "operator_duty", **(metadata or {})},
    )
    session.updated_at = timezone.now()
    session.save(update_fields=["updated_at"])
    return msg


def deliver_morning_briefing(user: User, *, force: bool = False) -> dict[str, Any] | None:
    """Duty chat removed — briefings are disabled."""
    return {"skipped": True, "reason": "duty_removed"}


def deliver_briefings_for_all_users(*, force: bool = False) -> dict[str, Any]:
    """Duty chat removed — briefings are disabled."""
    return {"delivered": 0, "skipped": 0, "errors": 0, "users": 0, "reason": "duty_removed"}


def post_critical_alert_to_duty(alert) -> bool:
    """Duty chat removed — critical alert posts are disabled."""
    return False


def _encode(text: str) -> str:
    from urllib.parse import quote

    return quote(text, safe="")
