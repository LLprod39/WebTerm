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

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext

_TEMPLATE_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@registry.register
class OutputReportNode(BaseNode):
    """Compile a markdown report from upstream outputs and attach it to the run."""

    node_type = "output/report"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        from studio.models import PipelineRun

        template: str = self.node_data.get("template", "")

        if template:
            report = ctx.resolve_template(template)
        else:
            run = await sync_to_async(PipelineRun.objects.select_related("pipeline").get)(pk=ctx.run_id)
            lines = [f"# Pipeline Run Report: {run.pipeline.name}\n"]
            for node_id, output in ctx.node_outputs.items():
                lines.append(f"## Node `{node_id}`")
                status = output.get("status", "unknown")
                lines.append(f"**Status:** {status}")
                if output.get("output"):
                    lines.append(f"```\n{str(output['output'])[:2000]}\n```")
                if output.get("error"):
                    lines.append(f"**Error:** {output['error']}")
                lines.append("")
            report = "\n".join(lines)

        await sync_to_async(
            lambda: __import__("studio.models", fromlist=["PipelineRun"])
            .PipelineRun.objects.filter(pk=ctx.run_id)
            .update(summary=report)
        )()

        return NodeResult(output={"status": "completed", "report": report[:500]})
