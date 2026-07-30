"""Cluster-wide capacity coordination for playbook dispatch claims."""

from __future__ import annotations

from django.conf import settings
from django.db import connection

DEFAULT_PLAYBOOK_GLOBAL_CONCURRENCY = 4
DEFAULT_PLAYBOOK_PER_USER_CONCURRENCY = 2
MAX_PLAYBOOK_GLOBAL_CONCURRENCY = 64
PLAYBOOK_CLAIM_CAPACITY_ADVISORY_LOCK = 871_932_441


def playbook_concurrency_limit(value: int | None, *, setting_name: str, default: int) -> int:
    configured = getattr(settings, setting_name, default) if value is None else value
    try:
        parsed = int(configured)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, MAX_PLAYBOOK_GLOBAL_CONCURRENCY))


def lock_playbook_claim_capacity() -> None:
    """Serialize only the final count-and-claim step on PostgreSQL."""
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [PLAYBOOK_CLAIM_CAPACITY_ADVISORY_LOCK])
