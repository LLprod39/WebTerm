"""Django HTTP server spans with W3C Trace Context extraction."""

from __future__ import annotations

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.conf import settings
from opentelemetry.trace import SpanKind, Status, StatusCode

from app.observability import current_trace_identifiers, extract_trace_context, start_span


class OpenTelemetryMiddleware:
    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if iscoroutinefunction(get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        if iscoroutinefunction(self.get_response):
            return self.__acall__(request)
        if self._should_skip(request):
            return self.get_response(request)
        with self._request_span(request) as span:
            response = self.get_response(request)
            return self._finish_response(request, response, span)

    async def __acall__(self, request):
        if self._should_skip(request):
            return await self.get_response(request)
        with self._request_span(request) as span:
            response = await self.get_response(request)
            return self._finish_response(request, response, span)

    def _should_skip(self, request) -> bool:
        path = str(getattr(request, "path", "") or "")
        static_url = str(getattr(settings, "STATIC_URL", "/static/") or "/static/")
        media_url = str(getattr(settings, "MEDIA_URL", "/media/") or "/media/")
        return path.startswith(static_url) or path.startswith(media_url) or path == "/favicon.ico"

    def _request_span(self, request):
        method = str(getattr(request, "method", "GET") or "GET").upper()
        path = str(getattr(request, "path", "/") or "/")
        parent_context = extract_trace_context(
            {
                "traceparent": request.headers.get("traceparent", ""),
                "tracestate": request.headers.get("tracestate", ""),
            }
        )
        return start_span(
            f"{method} {path}",
            kind=SpanKind.SERVER,
            context=parent_context,
            attributes={
                "http.request.method": method,
                "url.path": path,
            },
        )

    @staticmethod
    def _finish_response(request, response, span):
        method = str(getattr(request, "method", "GET") or "GET").upper()
        resolver_match = getattr(request, "resolver_match", None)
        route = str(getattr(resolver_match, "route", "") or getattr(request, "path", "/") or "/")
        span.update_name(f"{method} {route}")
        span.set_attribute("http.route", route)
        span.set_attribute("http.response.status_code", int(response.status_code))
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            span.set_attribute("enduser.id", str(user.pk))
        if int(response.status_code) >= 500:
            span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
        trace_ids = current_trace_identifiers()
        if trace_ids:
            response["X-Trace-ID"] = trace_ids["trace_id"]
        return response
