"""
studio/executor/nodes/output_webhook.py

Node type: output/webhook
POSTs pipeline result payload to an external URL.

Migrated from: studio/pipeline_executor.py:_execute_output_webhook()
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

import httpx

from app.agent_kernel.memory.redaction import redact_payload, sanitize_observation_text
from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext

_SIMPLE_TEMPLATE_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _render_template_value(value, ctx: "ExecutionContext"):
    if isinstance(value, str):
        return _SIMPLE_TEMPLATE_PATTERN.sub(lambda match: str(ctx.get_variable(match.group(1), "")), value)
    if isinstance(value, list):
        return [_render_template_value(item, ctx) for item in value]
    if isinstance(value, dict):
        return {key: _render_template_value(item, ctx) for key, item in value.items()}
    return value


def _redact_pipeline_text(value, *, limit: int | None = None) -> str:
    text = sanitize_observation_text(str(value or "")).text
    if limit is None:
        return text
    return text[: max(0, int(limit))]


def _redact_pipeline_value(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _redact_pipeline_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_pipeline_value(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_pipeline_value(item) for item in value]
    if isinstance(value, (int, float, bool)):
        return value
    return _redact_pipeline_text(value)


def _redacted_context(ctx: "ExecutionContext") -> defaultdict[str, object]:
    raw_context = ctx.extra.get("context")
    if not isinstance(raw_context, dict):
        raw_context = {}
    return defaultdict(str, {str(key): _redact_pipeline_value(value) for key, value in raw_context.items()})


def _redacted_node_outputs_payload(node_outputs: dict[str, dict], *, max_output_chars: int = 1000) -> dict[str, dict[str, object]]:
    return {
        str(node_id): {
            "status": state.get("status"),
            "output": _redact_pipeline_text(state.get("output", ""), limit=max_output_chars),
        }
        for node_id, state in node_outputs.items()
    }


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

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        url = str(_render_template_value(self.node_data.get("url", ""), ctx) or "").strip()
        if not url:
            return NodeResult(error="No URL configured")

        payload: dict = {
            "context": dict(_redacted_context(ctx)),
            "outputs": _redacted_node_outputs_payload(ctx.node_outputs),
        }
        extra = self.node_data.get("extra_payload", {})
        if isinstance(extra, dict):
            payload.update(_render_template_value(extra, ctx))
        payload, _redaction_report, _redaction_hashes = redact_payload(payload)

        raw_headers = self.node_data.get("headers")
        headers = _render_template_value(raw_headers, ctx) if isinstance(raw_headers, dict) else {}
        timeout = _coerce_timeout(self.node_data.get("timeout_seconds"))
        fail_on_non_2xx = _coerce_bool(self.node_data.get("fail_on_non_2xx"))

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
            output = {
                "status": "completed",
                "output": f"POST {url} -> {resp.status_code}",
                "http_status": resp.status_code,
            }
            if fail_on_non_2xx and not (200 <= resp.status_code < 300):
                output["status"] = "failed"
                return NodeResult(error=f"Webhook returned HTTP {resp.status_code}", output=output)
            return NodeResult(output=output)
        except Exception as exc:
            return NodeResult(error=str(exc))
