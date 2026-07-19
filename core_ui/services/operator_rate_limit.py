"""Simple per-user / per-session rate limits for Operator turns."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from core_ui.models import ChatMessage, ChatSession, ChatTurnState

MAX_TURNS_PER_HOUR = 60
MAX_CONCURRENT_ASYNC = 3


def check_turn_rate_limit(session: ChatSession) -> str | None:
    """Return error message if rate-limited, else None."""
    since = timezone.now() - timedelta(hours=1)
    recent = ChatMessage.objects.filter(
        session=session,
        role=ChatMessage.ROLE_USER,
        created_at__gte=since,
    ).count()
    if recent >= MAX_TURNS_PER_HOUR:
        return f"Rate limit: max {MAX_TURNS_PER_HOUR} messages per hour in this chat."

    async_count = ChatTurnState.objects.filter(
        session=session,
        status=ChatTurnState.STATUS_AWAITING_ASYNC,
    ).count()
    if async_count >= MAX_CONCURRENT_ASYNC:
        return f"Too many async runs in flight (max {MAX_CONCURRENT_ASYNC}). Wait for completion."
    return None
