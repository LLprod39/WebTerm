"""
studio/executor/nodes/output_webhook.py

Node type: output/webhook
POSTs pipeline result payload to an external URL.

Migrated from: studio/pipeline_executor.py:_execute_output_webhook()
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


@registry.register
class OutputWebhookNode(BaseNode):
    """POST pipeline results to an external webhook URL."""

    node_type = "output/webhook"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        url = ctx.resolve_template(self.node_data.get("url", "").strip())
        if not url:
            return NodeResult(error="output/webhook: no URL configured")

        payload: dict = {
            "run_id": ctx.run_id,
            "outputs": {
                node_id: {"output": str(out.get("output", ""))[:1000]}
                for node_id, out in ctx.node_outputs.items()
            },
        }
        extra = self.node_data.get("extra_payload", {})
        if isinstance(extra, dict):
            payload.update(extra)

        timeout = float(self.node_data.get("timeout_seconds", 30))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload)
            return NodeResult(output={
                "status": "completed",
                "http_status": resp.status_code,
                "url": url,
            })
        except Exception as exc:
            return NodeResult(error=f"output/webhook POST failed: {exc}")
