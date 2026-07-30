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
    session = ChatSession.objects.filter(user=user, kind=ChatSession.KIND_DUTY).order_by("-updated_at").first()
    if session is not None:
        return session
    return ChatSession.objects.create(
        user=user,
        title="Дежурный",
        kind=ChatSession.KIND_DUTY,
        pinned_context={
            "duty_enabled": True,
            "briefing_hour": DEFAULT_BRIEFING_HOUR,
        },
    )


def duty_enabled(session: ChatSession) -> bool:
    pinned = session.pinned_context if isinstance(session.pinned_context, dict) else {}
    return bool(pinned.get("duty_enabled", True))


def set_duty_enabled(user: User, *, enabled: bool) -> ChatSession:
    session = get_or_create_duty_session(user)
    pinned = dict(session.pinned_context or {})
    pinned["duty_enabled"] = bool(enabled)
    session.pinned_context = pinned
    session.save(update_fields=["pinned_context", "updated_at"])
    return session


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
    if not feature_allowed_for_user(user, "orchestrator"):
        return None
    session = get_or_create_duty_session(user)
    if not _should_brief_now(session, force=force):
        return {"skipped": True, "session_id": session.pk, "reason": "not_due"}

    facts = _collect_facts_for_user(user)
    text = render_briefing_markdown(facts)
    msg = post_duty_message(
        session,
        text,
        metadata={
            "kind": "morning_briefing",
            "facts": {
                "server_count": facts.get("server_count"),
                "status_counts": facts.get("status_counts"),
                "alert_count": len(facts.get("open_alerts") or []),
                "prediction_count": len(facts.get("predictions") or []),
            },
        },
    )
    pinned = dict(session.pinned_context or {})
    pinned["last_briefing_at"] = timezone.now().isoformat()
    pinned["duty_enabled"] = pinned.get("duty_enabled", True)
    session.pinned_context = pinned
    session.save(update_fields=["pinned_context", "updated_at"])
    return {
        "session_id": session.pk,
        "message_id": msg.pk,
        "alert_count": len(facts.get("open_alerts") or []),
        "prediction_count": len(facts.get("predictions") or []),
    }


def deliver_briefings_for_all_users(*, force: bool = False) -> dict[str, Any]:
    """Run for all users with orchestrator feature (or existing duty sessions)."""
    from core_ui.models import UserAppPermission

    user_ids = set(
        UserAppPermission.objects.filter(feature="orchestrator", allowed=True).values_list("user_id", flat=True)
    )
    # Also staff
    user_ids.update(User.objects.filter(is_staff=True, is_active=True).values_list("id", flat=True))
    # Existing duty sessions
    user_ids.update(ChatSession.objects.filter(kind=ChatSession.KIND_DUTY).values_list("user_id", flat=True))

    delivered = 0
    skipped = 0
    errors = 0
    for uid in user_ids:
        user = User.objects.filter(pk=uid, is_active=True).first()
        if user is None:
            continue
        try:
            result = deliver_morning_briefing(user, force=force)
            if result and result.get("skipped"):
                skipped += 1
            elif result:
                delivered += 1
        except Exception as exc:  # noqa: BLE001
            errors += 1
            logger.exception("duty briefing failed user=%s: %s", uid, exc)
    return {"delivered": delivered, "skipped": skipped, "errors": errors, "users": len(user_ids)}


def post_critical_alert_to_duty(alert) -> bool:
    """Proactive: push a short note into the server owner's duty chat."""
    try:
        server = getattr(alert, "server", None)
        if server is None:
            return False
        owner = getattr(server, "user", None)
        if owner is None or not feature_allowed_for_user(owner, "orchestrator"):
            return False
        session = get_or_create_duty_session(owner)
        if not duty_enabled(session):
            return False
        severity = getattr(alert, "severity", "critical")
        if severity not in {"critical"}:
            return False
        text = (
            f"### 🚨 Критический алерт\n"
            f"**{server.name}** — {alert.title}\n"
            f"{(alert.message or '')[:400]}\n\n"
            f"[Разобрать в чате](/chat?q={_encode(f'Разобрать алерт #{alert.id} на {server.name}: {alert.title}')})"
        )
        post_duty_message(
            session,
            text,
            metadata={"kind": "critical_alert", "alert_id": alert.id, "server_id": server.id},
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("duty critical alert post skipped: %s", exc)
        return False


def _encode(text: str) -> str:
    from urllib.parse import quote

    return quote(text, safe="")
