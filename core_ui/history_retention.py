"""Bounded, background-only retention for high-volume history tables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.apps import apps
from django.db.models import QuerySet
from django.utils import timezone

from core_ui.audit import get_logging_config


@dataclass(frozen=True)
class RetentionPolicy:
    name: str
    queryset: QuerySet
    timestamp_field: str
    max_age_days: int
    max_rows: int


def _bounded_env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    try:
        value = int(raw) if raw else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def configured_retention_policies() -> tuple[RetentionPolicy, ...]:
    audit_days = int(get_logging_config().get("retention_days") or 90)
    PipelineRun = apps.get_model("studio", "PipelineRun")
    AgentRun = apps.get_model("servers", "AgentRun")
    ServerCommandHistory = apps.get_model("servers", "ServerCommandHistory")
    ChatArtifact = apps.get_model("core_ui", "ChatArtifact")
    UserActivityLog = apps.get_model("core_ui", "UserActivityLog")
    LLMUsageLog = apps.get_model("core_ui", "LLMUsageLog")
    terminal_pipeline_statuses = ("completed", "failed", "stopped")
    terminal_agent_statuses = ("completed", "failed", "stopped")

    def policy(
        name: str,
        queryset: QuerySet,
        timestamp_field: str,
        *,
        days: int,
        rows: int,
    ) -> RetentionPolicy:
        prefix = f"HISTORY_RETENTION_{name.upper()}"
        return RetentionPolicy(
            name=name,
            queryset=queryset,
            timestamp_field=timestamp_field,
            max_age_days=_bounded_env_int(f"{prefix}_DAYS", days, minimum=1, maximum=3650),
            max_rows=_bounded_env_int(f"{prefix}_MAX_ROWS", rows, minimum=1, maximum=50_000_000),
        )

    return (
        policy(
            "pipeline_run",
            PipelineRun.objects.filter(status__in=terminal_pipeline_statuses),
            "created_at",
            days=90,
            rows=100_000,
        ),
        policy(
            "agent_run",
            AgentRun.objects.filter(status__in=terminal_agent_statuses),
            "started_at",
            days=90,
            rows=100_000,
        ),
        policy(
            "server_command_history",
            ServerCommandHistory.objects.all(),
            "executed_at",
            days=90,
            rows=500_000,
        ),
        policy(
            "chat_artifact",
            ChatArtifact.objects.all(),
            "created_at",
            days=90,
            rows=100_000,
        ),
        policy(
            "user_activity_log",
            UserActivityLog.objects.all(),
            "created_at",
            days=max(1, min(audit_days, 3650)),
            rows=500_000,
        ),
        policy(
            "llm_usage_log",
            LLMUsageLog.objects.all(),
            "created_at",
            days=max(1, min(audit_days, 3650)),
            rows=500_000,
        ),
    )


def _delete_oldest(queryset: QuerySet, *, timestamp_field: str, batch_size: int, limit: int | None) -> int:
    deleted_rows = 0
    model = queryset.model
    while limit is None or deleted_rows < limit:
        remaining = batch_size if limit is None else min(batch_size, limit - deleted_rows)
        row_ids = list(queryset.order_by(timestamp_field, "pk").values_list("pk", flat=True)[:remaining])
        if not row_ids:
            break
        model.objects.filter(pk__in=row_ids).delete()
        deleted_rows += len(row_ids)
    return deleted_rows


def prune_history(*, dry_run: bool = False, batch_size: int = 1000) -> dict[str, dict[str, Any]]:
    """Prune eligible terminal/history rows without running inside an HTTP request."""
    if batch_size < 1 or batch_size > 10_000:
        raise ValueError("batch_size must be between 1 and 10000")

    now = timezone.now()
    report: dict[str, dict[str, Any]] = {}
    for policy in configured_retention_policies():
        cutoff = now - timedelta(days=policy.max_age_days)
        age_filter = {f"{policy.timestamp_field}__lt": cutoff}
        age_queryset = policy.queryset.filter(**age_filter)
        age_candidates = age_queryset.count()

        if dry_run:
            remaining = policy.queryset.exclude(**age_filter).count()
            overflow_candidates = max(remaining - policy.max_rows, 0)
            deleted = 0
        else:
            deleted = _delete_oldest(
                age_queryset,
                timestamp_field=policy.timestamp_field,
                batch_size=batch_size,
                limit=None,
            )
            overflow_candidates = max(policy.queryset.count() - policy.max_rows, 0)
            deleted += _delete_oldest(
                policy.queryset,
                timestamp_field=policy.timestamp_field,
                batch_size=batch_size,
                limit=overflow_candidates,
            )

        report[policy.name] = {
            "max_age_days": policy.max_age_days,
            "max_rows": policy.max_rows,
            "age_candidates": age_candidates,
            "overflow_candidates": overflow_candidates,
            "deleted": deleted,
        }
    return report
