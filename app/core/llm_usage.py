import asyncio
from typing import Any

from django.conf import settings as django_settings
from loguru import logger

from app.core.llm_usage_sink import LLMUsageEvent, capture_llm_usage_context, record_llm_usage_event


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
        captured_audit_ctx = capture_llm_usage_context()
    except Exception:
        captured_audit_ctx = {}

    def _do_log():
        try:
            record_llm_usage_event(
                LLMUsageEvent(
                    provider=provider,
                    model_name=model_name,
                    input_text=input_text,
                    output_text=output_text,
                    duration_ms=duration_ms,
                    status=status,
                    purpose=purpose,
                    metadata=metadata,
                    audit_context=captured_audit_ctx,
                )
            )
        except Exception as e:
            logger.debug(f"Failed to log LLM usage: {e}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        if _uses_sqlite_database() and getattr(django_settings, "LLM_USAGE_SKIP_DETACHED_SQLITE_LOGGING", True):
            logger.debug("Skipping detached async LLM usage logging on SQLite to avoid database locks")
            return
        # Detached background logging must not inherit asgiref's thread-sensitive
        # executor context, otherwise later ASGI requests can fail with a broken
        # CurrentThreadExecutor after this task outlives the originating request.
        loop.run_in_executor(None, _do_log)
        return

    _do_log()
