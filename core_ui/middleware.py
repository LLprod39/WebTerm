"""
Middleware: русский язык для админки Django + определение мобильных устройств.
"""

import contextlib
import json
import re
import time
import uuid

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.conf import settings
from django.utils import translation
from loguru import logger

from core_ui.activity import log_user_activity
from core_ui.audit import audit_context, infer_request_category

_SENSITIVE_REQUEST_KEYS = (
    "password",
    "master_password",
    "token",
    "secret",
    "api_key",
    "authorization",
    "smtp_password",
    "encrypted_password",
)
_REQUEST_ID_PATTERN = re.compile(r"[^A-Za-z0-9._:-]+")


def _is_sensitive_key(key: str) -> bool:
    key_lower = str(key or "").strip().lower()
    return any(part in key_lower for part in _SENSITIVE_REQUEST_KEYS)


def _sanitize_request_value(value, *, max_len: int = 2000):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                result[str(key)] = "***"
            else:
                result[str(key)] = _sanitize_request_value(item, max_len=max_len)
        return result
    if isinstance(value, (list, tuple)):
        return [_sanitize_request_value(item, max_len=max_len) for item in value[:100]]
    text = str(value or "")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _extract_request_payload(request):
    method = (request.method or "GET").upper()
    content_type = str(request.META.get("CONTENT_TYPE") or "").lower()
    query_params = {key: request.GET.getlist(key) for key in request.GET}
    metadata = {"query": _sanitize_request_value(query_params)}

    if method in {"GET", "HEAD", "OPTIONS"}:
        return metadata

    if "application/json" in content_type:
        try:
            body_bytes = request.body or b""
            if len(body_bytes) > 128 * 1024:
                metadata["payload"] = {"_truncated": True, "_bytes": len(body_bytes)}
                return metadata
            parsed = json.loads(body_bytes.decode("utf-8") or "{}")
            metadata["payload"] = _sanitize_request_value(parsed)
            return metadata
        except Exception:
            metadata["payload_raw"] = _sanitize_request_value((request.body or b"")[:4096].decode("utf-8", "ignore"))
            return metadata

    if content_type.startswith("multipart/form-data") or content_type.startswith("application/x-www-form-urlencoded"):
        metadata["payload"] = _sanitize_request_value({key: request.POST.getlist(key) for key in request.POST})
        if request.FILES:
            metadata["files"] = [
                {
                    "field": key,
                    "name": file_obj.name,
                    "size": getattr(file_obj, "size", 0),
                }
                for key, file_obj in request.FILES.items()
            ]
        return metadata

    body_bytes = request.body or b""
    if body_bytes:
        metadata["payload_raw"] = _sanitize_request_value(body_bytes[:4096].decode("utf-8", "ignore"))
    return metadata


class AdminRussianMiddleware:
    """Включает русский интерфейс для страниц /admin/."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/admin/"):
            translation.activate("ru")
        response = self.get_response(request)
        return response


class RequestAuditMiddleware:
    """Bind audit context to HTTP requests and optionally persist request-level logs."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if iscoroutinefunction(get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        if iscoroutinefunction(self.get_response):
            return self.__acall__(request)
        return self._call_sync(request)

    def _should_skip(self, request) -> bool:
        path = str(getattr(request, "path", "") or "")
        static_url = str(getattr(settings, "STATIC_URL", "/static/") or "/static/")
        media_url = str(getattr(settings, "MEDIA_URL", "/media/") or "/media/")
        return path.startswith(static_url) or path.startswith(media_url) or path == "/favicon.ico"

    def _normalize_request_id(self, value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return uuid.uuid4().hex
        normalized = _REQUEST_ID_PATTERN.sub("-", raw)[:128].strip("-")
        return normalized or uuid.uuid4().hex

    def _ensure_request_id(self, request) -> str:
        request_id = getattr(request, "request_id", "")
        if request_id:
            return str(request_id)
        incoming = request.META.get("HTTP_X_REQUEST_ID") or request.META.get("HTTP_X_CORRELATION_ID") or ""
        request_id = self._normalize_request_id(incoming)
        request.request_id = request_id
        return request_id

    def _attach_request_id(self, response, request_id: str):
        if response is not None:
            response["X-Request-ID"] = request_id
        return response

    def _audit_scope(self, request):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return None
        return audit_context(
            user_id=int(user.id),
            username_snapshot=str(user.username or ""),
            channel="http",
            path=str(getattr(request, "path", "") or ""),
            method=str(getattr(request, "method", "GET") or "GET").upper(),
            request_id=str(getattr(request, "request_id", "") or ""),
        )

    def _logger_scope(self, request):
        user = getattr(request, "user", None)
        return logger.contextualize(
            request_id=str(getattr(request, "request_id", "") or "-"),
            channel="http",
            user_id=str(getattr(user, "id", "") or "-"),
            path=str(getattr(request, "path", "") or "-"),
        )

    def _log_request(self, request, *, status_code: int, duration_ms: int, error_text: str = "") -> None:
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False) or self._should_skip(request):
            return
        method = str(getattr(request, "method", "GET") or "GET").upper()
        path = str(getattr(request, "path", "") or "")
        category = infer_request_category(path)
        metadata = _extract_request_payload(request)
        metadata.update(
            {
                "method": method,
                "path": path,
                "status_code": int(status_code),
                "duration_ms": int(duration_ms),
                "request_id": str(getattr(request, "request_id", "") or ""),
            }
        )
        if error_text:
            metadata["error"] = _sanitize_request_value(error_text, max_len=4000)
        log_user_activity(
            user=user,
            request=request,
            category=category,
            action="http_request",
            status="success" if 200 <= int(status_code) < 400 else "error",
            description=f"{method} {path} -> {status_code}",
            entity_type="http_request",
            entity_name=path,
            metadata=metadata,
        )

    def _call_sync(self, request):
        start_ts = time.monotonic()
        request_id = self._ensure_request_id(request)
        scope = self._audit_scope(request)
        with scope or contextlib.nullcontext(), self._logger_scope(request):
            try:
                response = self.get_response(request)
            except Exception as exc:
                self._log_request(
                    request,
                    status_code=500,
                    duration_ms=int((time.monotonic() - start_ts) * 1000),
                    error_text=str(exc),
                )
                raise
            response = self._attach_request_id(response, request_id)
            if not self._should_skip(request):
                self._log_request(
                    request,
                    status_code=getattr(response, "status_code", 200),
                    duration_ms=int((time.monotonic() - start_ts) * 1000),
                )
            return response

    async def __acall__(self, request):
        start_ts = time.monotonic()
        request_id = self._ensure_request_id(request)
        scope = self._audit_scope(request)
        with scope or contextlib.nullcontext(), self._logger_scope(request):
            try:
                response = await self.get_response(request)
            except Exception as exc:
                self._log_request(
                    request,
                    status_code=500,
                    duration_ms=int((time.monotonic() - start_ts) * 1000),
                    error_text=str(exc),
                )
                raise
            response = self._attach_request_id(response, request_id)
            if not self._should_skip(request):
                self._log_request(
                    request,
                    status_code=getattr(response, "status_code", 200),
                    duration_ms=int((time.monotonic() - start_ts) * 1000),
                )
            return response


class MobileDetectionMiddleware:
    """
    Определяет мобильные устройства по User-Agent.
    Устанавливает request.is_mobile = True/False.
    """

    MOBILE_KEYWORDS = [
        "mobile",
        "android",
        "iphone",
        "ipad",
        "ipod",
        "webos",
        "blackberry",
        "opera mini",
        "opera mobi",
        "iemobile",
        "windows phone",
        "palm",
        "symbian",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_agent = request.META.get("HTTP_USER_AGENT", "").lower()
        request.is_mobile = any(kw in user_agent for kw in self.MOBILE_KEYWORDS)

        # Также проверяем query параметр для тестирования
        if request.GET.get("mobile") == "1":
            request.is_mobile = True
        elif request.GET.get("mobile") == "0":
            request.is_mobile = False

        response = self.get_response(request)
        return response


def get_template_name(request, default_template: str) -> str:
    """
    Возвращает мобильный шаблон или базовый шаблон в зависимости от устройства.

    Args:
        request: Django request object
        default_template: имя базового шаблона (например 'chat.html')

    Returns:
        Путь к шаблону: 'mobile/chat.html' или 'chat.html'
    """
    if getattr(request, "is_mobile", False):
        return f"mobile/{default_template}"
    return default_template
