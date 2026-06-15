from __future__ import annotations

from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async

from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry
from studio.models import PipelineRun

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


@registry.register
class LogicTelegramInputNode(BaseNode):
    node_type = "logic/telegram_input"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        from studio.pipeline_executor import _execute_logic_telegram_input

        run = ctx.extra.get("run")
        if not isinstance(run, PipelineRun):
            run = await sync_to_async(lambda: PipelineRun.objects.get(pk=ctx.run_id), thread_sensitive=False)()

        result = await _execute_logic_telegram_input(
            {"id": self.node_id, "type": self.node_type, "data": self.node_data},
            dict(ctx.extra.get("context") or {}),
            ctx.node_outputs,
            run,
            ctx.stop_event,
        )
        return NodeResult(output=dict(result or {}))
