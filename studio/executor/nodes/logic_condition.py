from __future__ import annotations

from typing import TYPE_CHECKING

from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry
from studio.pipeline.pipeline_logic import execute_logic_condition

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


@registry.register
class LogicConditionNode(BaseNode):
    node_type = "logic/condition"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        result = await execute_logic_condition(
            {"id": self.node_id, "data": self.node_data},
            ctx.extra.get("context") or {},
            ctx.node_outputs,
            ctx.extra.get("run"),
        )
        return NodeResult(output=result)
