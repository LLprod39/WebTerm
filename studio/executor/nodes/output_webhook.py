"""
studio/executor/nodes/output_webhook.py

Node type: output/webhook
POSTs pipeline result payload to an external URL.

Migrated from: studio/pipeline_executor.py:_execute_output_webhook()
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import httpx

from app.agent_kernel.memory.redaction import redact_payload
from app.outbound_http import request_outbound_http
from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry
from studio.pipeline.pipeline_redaction import (
    redact_pipeline_text as _redact_pipeline_text,
)
from studio.pipeline.pipeline_redaction import (
    redacted_execution_context as _redacted_context,
)
from studio.pipeline.pipeline_redaction import (
    redacted_node_outputs_payload as _redacted_node_outputs_payload,
)

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext

_SIMPLE_TEMPLATE_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _render_template_value(value, ctx: ExecutionContext, safe_context: dict[str, object] | None = None):
    if isinstance(value, str):
        return _SIMPLE_TEMPLATE_PATTERN.sub(
            lambda match: str((safe_context or {}).get(match.group(1), ctx.get_variable(match.group(1), ""))),
            value,
        )
    if isinstance(value, list):
        return [_render_template_value(item, ctx, safe_context) for item in value]
    if isinstance(value, dict):
        return {key: _render_template_value(item, ctx, safe_context) for key, item in value.items()}
    return value


def _coerce_timeout(value) -> int:
    try:
        return max(1, min(int(value or 30), 120))
    except (TypeError, ValueError):
        return 30


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@registry.register
class OutputWebhookNode(BaseNode):
    """POST pipeline results to an external webhook URL."""

    node_type = "output/webhook"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        url = str(_render_template_value(self.node_data.get("url", ""), ctx) or "").strip()
        if not url:
            return NodeResult(error="No URL configured")

        safe_context = _redacted_context(ctx)
        payload: dict = {
            "context": dict(safe_context),
            "outputs": _redacted_node_outputs_payload(ctx.node_outputs),
        }
        extra = self.node_data.get("extra_payload", {})
        if isinstance(extra, dict):
            payload.update(_render_template_value(extra, ctx, safe_context))
        payload, _redaction_report, _redaction_hashes = redact_payload(payload)

        raw_headers = self.node_data.get("headers")
        headers = _render_template_value(raw_headers, ctx, safe_context) if isinstance(raw_headers, dict) else {}
        timeout = _coerce_timeout(self.node_data.get("timeout_seconds"))
        fail_on_non_2xx = _coerce_bool(self.node_data.get("fail_on_non_2xx"))

        try:
            resp = await request_outbound_http(
                "POST",
                url,
                timeout=timeout,
                headers=headers,
                client_factory=httpx.AsyncClient,
                json=payload,
            )
            output = {
                "status": "completed",
                "output": f"POST {_redact_pipeline_text(url)} -> {resp.status_code}",
                "http_status": resp.status_code,
            }
            if fail_on_non_2xx and not (200 <= resp.status_code < 300):
                output["status"] = "failed"
                return NodeResult(error=f"Webhook returned HTTP {resp.status_code}", output=output)
            return NodeResult(output=output)
        except Exception as exc:
            return NodeResult(error=_redact_pipeline_text(str(exc)))
