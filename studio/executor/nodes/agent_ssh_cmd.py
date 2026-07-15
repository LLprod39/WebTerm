from __future__ import annotations

from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async

from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry
from studio.models import PipelineRun

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


@registry.register
class AgentSSHCommandNode(BaseNode):
    node_type = "agent/ssh_cmd"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        from studio.pipeline_agent_runtime import execute_agent_ssh_cmd

        run = ctx.extra.get("run")
        if not isinstance(run, PipelineRun):
            run = await sync_to_async(lambda: PipelineRun.objects.get(pk=ctx.run_id), thread_sensitive=False)()

        result = await execute_agent_ssh_cmd(
            {"id": self.node_id, "type": self.node_type, "data": self.node_data},
            dict(ctx.extra.get("context") or {}),
            run,
        )
        return NodeResult(output=dict(result or {}))
