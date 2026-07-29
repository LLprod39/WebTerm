from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.egress_redaction import redact_egress_text
from app.outbound_http import OutboundHTTPPolicyError, request_outbound_http
from studio.executor.nodes.base import NodeResult
from studio.executor.nodes.ops_helpers import coerce_int as _coerce_int
from studio.executor.nodes.ops_helpers import coerce_list as _coerce_list

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


async def execute_http_check(ctx: ExecutionContext, config: dict[str, Any], *, async_client_factory: Any) -> NodeResult:
    url = ctx.resolve_template(str(config.get("url") or ""))
    if not url:
        return NodeResult(error="url is required")
    method = str(config.get("method") or "GET").strip().upper()
    if method not in {"GET", "HEAD"}:
        return NodeResult(error="method must be GET or HEAD")
    expected_status = [_coerce_int(item) for item in _coerce_list(config.get("expected_status"))]
    expected = {item for item in expected_status if item is not None} or set(range(200, 400))
    timeout = max(1, min(_coerce_int(config.get("timeout_seconds")) or 15, 120))
    retries = max(1, min(_coerce_int(config.get("retries")) or 1, 5))
    body_contains = ctx.resolve_template(str(config.get("body_contains") or ""))
    last_error = ""
    response_payload: dict[str, Any] = {}
    safe_url = redact_egress_text(url).text
    for attempt in range(1, retries + 1):
        try:
            response = await request_outbound_http(
                method,
                url,
                timeout=timeout,
                max_redirects=5,
                client_factory=async_client_factory,
            )
            body = response.text[:2000] if method != "HEAD" else ""
            safe_body = redact_egress_text(body).text
            response_payload = {
                "url": safe_url,
                "method": method,
                "status_code": response.status_code,
                "attempt": attempt,
                "body_excerpt": safe_body,
            }
            if response.status_code not in expected:
                last_error = f"Unexpected status {response.status_code}"
                continue
            if body_contains and body_contains not in body:
                last_error = "Expected body text was not found"
                continue
            text = f"HTTP check passed: {method} {safe_url} -> {response.status_code}"
            return NodeResult(output={"output": text, "http_check": response_payload})
        except OutboundHTTPPolicyError as exc:
            last_error = str(exc)
            response_payload = {"url": safe_url, "method": method, "attempt": attempt, "error": last_error}
            break
        except Exception as exc:
            last_error = redact_egress_text(str(exc)).text
            response_payload = {"url": safe_url, "method": method, "attempt": attempt, "error": last_error}

    return NodeResult(
        error=last_error or "HTTP check failed",
        output={"output": f"HTTP check failed: {method} {safe_url}: {last_error}", "http_check": response_payload},
    )
