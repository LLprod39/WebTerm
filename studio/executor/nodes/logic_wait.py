from __future__ import annotations

from typing import TYPE_CHECKING

from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry
from studio.pipeline.pipeline_logic import execute_logic_wait_node

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


@registry.register
class LogicWaitNode(BaseNode):
    node_type = "logic/wait"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        config = self.node_data if isinstance(self.node_data, dict) else {}
        result = await execute_logic_wait_node(self.node_id, config, ctx.run_id, ctx.stop_event)
        return NodeResult(output=result)
