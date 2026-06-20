from __future__ import annotations

import contextlib
from typing import Any

from app.core.llm_usage_sink import LLMUsageEvent


def capture_llm_usage_audit_context() -> dict[str, Any]:
    from core_ui.audit import get_audit_context

    return dict(get_audit_context() or {})


def record_llm_usage(event: LLMUsageEvent) -> None:
    from django.db import close_old_connections

    from core_ui.activity import log_llm_activity
    from core_ui.audit import audit_context, get_audit_context, maybe_apply_log_retention, should_log_llm
    from core_ui.models import LLMUsageLog

    try:
        close_old_connections()
        with audit_context(**event.audit_context):
            if not should_log_llm():
                return

            maybe_apply_log_retention()
            audit_ctx = get_audit_context()
            LLMUsageLog.objects.create(
                provider=event.provider,
                model_name=event.model_name,
                user_id=audit_ctx.get("user_id"),
                input_tokens=len(event.input_text) // 4,
                output_tokens=len(event.output_text) // 4,
                duration_ms=event.duration_ms,
                status=event.status,
            )
            log_llm_activity(
                provider=event.provider,
                model_name=event.model_name,
                prompt=event.input_text,
                response=event.output_text,
                duration_ms=event.duration_ms,
                status=event.status,
                purpose=event.purpose,
                metadata=event.metadata,
            )
    finally:
        with contextlib.suppress(Exception):
            close_old_connections()
