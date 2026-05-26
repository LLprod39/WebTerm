import asyncio
import contextlib
from typing import Any

from django.conf import settings as django_settings
from loguru import logger


def _uses_sqlite_database() -> bool:
    try:
        engine = str(django_settings.DATABASES["default"].get("ENGINE", ""))
    except Exception:
        return False
    return engine.endswith("sqlite3")


def log_llm_usage(
    provider: str,
    model_name: str,
    input_text: str,
    output_text: str,
    duration_ms: int,
    status: str = "success",
    *,
    purpose: str = "",
    metadata: dict[str, Any] | None = None,
):
    """Best-effort LLM usage logging that never blocks model responses."""
    try:
        from core_ui.audit import get_audit_context

        captured_audit_ctx = get_audit_context()
    except Exception:
        captured_audit_ctx = {}

    def _do_log():
        try:
            from django.db import close_old_connections

            from core_ui.activity import log_llm_activity
            from core_ui.audit import audit_context, get_audit_context, maybe_apply_log_retention, should_log_llm
            from core_ui.models import LLMUsageLog

            close_old_connections()
            with audit_context(**captured_audit_ctx):
                if not should_log_llm():
                    return

                maybe_apply_log_retention()
                audit_ctx = get_audit_context()
                LLMUsageLog.objects.create(
                    provider=provider,
                    model_name=model_name,
                    user_id=audit_ctx.get("user_id"),
                    input_tokens=len(input_text) // 4,
                    output_tokens=len(output_text) // 4,
                    duration_ms=duration_ms,
                    status=status,
                )
                log_llm_activity(
                    provider=provider,
                    model_name=model_name,
                    prompt=input_text,
                    response=output_text,
                    duration_ms=duration_ms,
                    status=status,
                    purpose=purpose,
                    metadata=metadata,
                )
        except Exception as e:
            logger.debug(f"Failed to log LLM usage: {e}")
        finally:
            with contextlib.suppress(Exception):
                close_old_connections()

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        if _uses_sqlite_database():
            logger.debug("Skipping detached async LLM usage logging on SQLite to avoid database locks")
            return
        # Detached background logging must not inherit asgiref's thread-sensitive
        # executor context, otherwise later ASGI requests can fail with a broken
        # CurrentThreadExecutor after this task outlives the originating request.
        loop.run_in_executor(None, _do_log)
        return

    _do_log()
