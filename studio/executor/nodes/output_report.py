"""
studio/executor/nodes/output_report.py

Node type: output/report
Compiles a markdown summary from all upstream node outputs and saves it
to PipelineRun.summary.

Migrated from: studio/pipeline_executor.py:_execute_output_report()
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async

from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry
from studio.pipeline_redaction import (
    redact_pipeline_text as _redact_pipeline_text,
)
from studio.pipeline_redaction import (
    redacted_execution_context as _redacted_pipeline_context,
)

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext

_TEMPLATE_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _render_template_value(value, context: dict[str, object]) -> str:
    return _TEMPLATE_PATTERN.sub(lambda match: str(context.get(match.group(1), "")), str(value or ""))


@registry.register
class OutputReportNode(BaseNode):
    """Compile a markdown report from upstream outputs and attach it to the run."""

    node_type = "output/report"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        from studio.models import PipelineRun

        template = str(self.node_data.get("template") or "")
        safe_context = _redacted_pipeline_context(ctx)

        if template:
            report = _render_template_value(template, safe_context)
        else:
            pipeline_name = str(getattr(ctx.pipeline, "name", "") or f"Pipeline #{ctx.run_id}")
            lines = [f"# Pipeline Run Report: {pipeline_name}\n"]
            for node_id, output in ctx.node_outputs.items():
                lines.append(f"## Node `{node_id}`")
                status = output.get("status", "unknown")
                lines.append(f"**Status:** {status}")
                if output.get("output"):
                    lines.append(f"```\n{_redact_pipeline_text(output['output'], limit=2000)}\n```")
                if output.get("error"):
                    lines.append(f"**Error:** {_redact_pipeline_text(output['error'])}")
                lines.append("")
            report = "\n".join(lines)
        report = _redact_pipeline_text(report)

        await sync_to_async(
            lambda: __import__("studio.models", fromlist=["PipelineRun"])
            .PipelineRun.objects.filter(pk=ctx.run_id)
            .update(summary=report)
        )()

        return NodeResult(output={"status": "completed", "output": report})
