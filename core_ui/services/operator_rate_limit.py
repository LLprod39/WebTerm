"""Simple per-user / per-session rate limits for Operator turns."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from core_ui.models import ChatMessage, ChatSession, ChatTurnState

MAX_TURNS_PER_HOUR = 60
MAX_CONCURRENT_ASYNC = 3
MAX_MESSAGE_CHARS = 12_000
MAX_ARTIFACT_CHARS = 256_000


def check_turn_rate_limit(session: ChatSession, *, message: str = "") -> str | None:
    """Return error message if rate-limited, else None."""
    if len(message) > MAX_MESSAGE_CHARS:
        return f"Message is too large (max {MAX_MESSAGE_CHARS} characters)."

    since = timezone.now() - timedelta(hours=1)
    recent = ChatMessage.objects.filter(
        session__user_id=session.user_id,
        role=ChatMessage.ROLE_USER,
        created_at__gte=since,
    ).count()
    if recent >= MAX_TURNS_PER_HOUR:
        return f"Rate limit: max {MAX_TURNS_PER_HOUR} messages per hour for this user."

    async_count = ChatTurnState.objects.filter(
        session__user_id=session.user_id,
        status=ChatTurnState.STATUS_AWAITING_ASYNC,
    ).count()
    if async_count >= MAX_CONCURRENT_ASYNC:
        return f"Too many async runs in flight (max {MAX_CONCURRENT_ASYNC}). Wait for completion."
    return None
