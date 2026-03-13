"""
Activity logging helpers.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from asgiref.sync import sync_to_async
from loguru import logger

from core_ui.audit import get_audit_context, maybe_apply_log_retention, should_log_activity
from core_ui.models import UserActivityLog


def _extract_client_ip(request) -> str:
    if not request:
        return ""
    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if xff:
        # Keep first hop from X-Forwarded-For chain.
        return xff.split(",")[0].strip()
    return (request.META.get("REMOTE_ADDR") or "").strip()


def _normalize_text(value: Any, max_len: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3] + "..."


def _normalize_metadata_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return _normalize_text(value, 4000)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return _normalize_text(value.decode("utf-8", "ignore"), 4000)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (UUID, Path)):
        return str(value)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 200:
                result["_truncated"] = True
                break
            result[str(key)] = _normalize_metadata_value(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        items: list[Any] = []
        for index, item in enumerate(list(value)[:200]):
            items.append(_normalize_metadata_value(item, depth=depth + 1))
            if index >= 199:
                break
        return items
    return _normalize_text(value, 4000)


def _normalize_metadata(metadata: Any) -> dict[str, Any]:
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        return {
            str(key): _normalize_metadata_value(value, depth=1)
            for key, value in list(metadata.items())[:200]
        }
    return {"value": _normalize_metadata_value(metadata, depth=1)}


def log_user_activity(
    *,
    user=None,
    user_id: int | None = None,
    request=None,
    username_snapshot: str = "",
    category: str,
    action: str,
    status: str = UserActivityLog.STATUS_INFO,
    description: str = "",
    entity_type: str = "",
    entity_id: str | int = "",
    entity_name: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Persist user activity event.
    Never raises: logging failures must not break business logic.
    """
    try:
        audit_ctx = get_audit_context()
        normalized_metadata = _normalize_metadata(metadata)
        request_id = str(
            getattr(request, "request_id", "") or audit_ctx.get("request_id") or ""
        ).strip()
        if request_id and "request_id" not in normalized_metadata:
            normalized_metadata["request_id"] = request_id
        if request and "path" not in normalized_metadata:
            normalized_metadata["path"] = str(getattr(request, "path", "") or "").strip()
        if request and "method" not in normalized_metadata:
            normalized_metadata["method"] = str(getattr(request, "method", "GET") or "GET").upper()
        if audit_ctx.get("channel") and "channel" not in normalized_metadata:
            normalized_metadata["channel"] = str(audit_ctx.get("channel") or "").strip()
        if audit_ctx.get("path") and "path" not in normalized_metadata:
            normalized_metadata["path"] = str(audit_ctx.get("path") or "").strip()
        if audit_ctx.get("entity_type") and "entity_type" not in normalized_metadata:
            normalized_metadata["entity_type"] = str(audit_ctx.get("entity_type") or "").strip()
        if audit_ctx.get("entity_id") and "entity_id" not in normalized_metadata:
            normalized_metadata["entity_id"] = str(audit_ctx.get("entity_id") or "").strip()

        if not should_log_activity(category=category, action=action, metadata=normalized_metadata):
            return

        maybe_apply_log_retention()
        resolved_user = user or getattr(request, "user", None)
        resolved_user_id = user_id or (
            resolved_user.id if resolved_user and getattr(resolved_user, "id", None) else audit_ctx.get("user_id")
        )
        resolved_username_snapshot = str(username_snapshot or "").strip()
        if not resolved_username_snapshot:
            if resolved_user and getattr(resolved_user, "username", None):
                resolved_username_snapshot = str(resolved_user.username)
            elif getattr(request, "user", None) and getattr(request.user, "username", None):
                resolved_username_snapshot = str(request.user.username)
            elif audit_ctx.get("username_snapshot") or audit_ctx.get("username"):
                resolved_username_snapshot = str(
                    audit_ctx.get("username_snapshot") or audit_ctx.get("username") or ""
                ).strip()

        user_agent = ""
        if request:
            user_agent = _normalize_text(request.META.get("HTTP_USER_AGENT") or "", 512)

        UserActivityLog.objects.create(
            user_id=resolved_user_id,
            username_snapshot=_normalize_text(resolved_username_snapshot, 150),
            category=_normalize_text(category, 40) or "other",
            action=_normalize_text(action, 80) or "unknown_action",
            status=status if status in {UserActivityLog.STATUS_INFO, UserActivityLog.STATUS_SUCCESS, UserActivityLog.STATUS_ERROR} else UserActivityLog.STATUS_INFO,
            description=_normalize_text(description, 5000),
            entity_type=_normalize_text(entity_type, 40),
            entity_id=_normalize_text(entity_id, 64),
            entity_name=_normalize_text(entity_name, 255),
            ip_address=_extract_client_ip(request) or None,
            user_agent=user_agent,
            metadata=normalized_metadata,
        )
    except Exception as exc:
        logger.debug("log_user_activity failed: {}", exc)


async def log_user_activity_async(**kwargs) -> None:
    """Async wrapper for activity logging."""
    await sync_to_async(log_user_activity, thread_sensitive=True)(**kwargs)


def log_llm_activity(
    *,
    provider: str,
    model_name: str,
    prompt: str,
    response: str,
    duration_ms: int,
    status: str = "success",
    purpose: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist a user-visible audit event for an LLM request."""
    audit_ctx = get_audit_context()
    prompt_excerpt = _normalize_text(prompt, 5000)
    response_excerpt = _normalize_text(response, 5000)
    merged_metadata = {
        "provider": str(provider or "").strip(),
        "model_name": str(model_name or "").strip(),
        "purpose": str(purpose or "").strip(),
        "duration_ms": int(duration_ms or 0),
        "status": str(status or "success").strip(),
        "prompt_length": len(prompt or ""),
        "response_length": len(response or ""),
        "response_excerpt": response_excerpt,
        "channel": audit_ctx.get("channel") or "",
        "path": audit_ctx.get("path") or "",
    }
    if metadata:
        merged_metadata.update(metadata)

    user_status = UserActivityLog.STATUS_SUCCESS
    if status in {"error", "timeout", "failed"}:
        user_status = UserActivityLog.STATUS_ERROR

    log_user_activity(
        user_id=audit_ctx.get("user_id"),
        username_snapshot=str(audit_ctx.get("username_snapshot") or audit_ctx.get("username") or "").strip(),
        category="ai",
        action="llm_request",
        status=user_status,
        description=prompt_excerpt,
        entity_type=str(audit_ctx.get("entity_type") or "llm").strip() or "llm",
        entity_id=str(audit_ctx.get("entity_id") or "").strip(),
        entity_name=str(audit_ctx.get("entity_name") or f"{provider}:{model_name}").strip(),
        metadata=merged_metadata,
    )


async def log_llm_activity_async(**kwargs) -> None:
    """Async wrapper for LLM activity logging."""
    await sync_to_async(log_llm_activity, thread_sensitive=True)(**kwargs)
