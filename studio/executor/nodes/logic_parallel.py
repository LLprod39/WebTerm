from __future__ import annotations

from typing import TYPE_CHECKING

from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


@registry.register
class LogicParallelNode(BaseNode):
    node_type = "logic/parallel"

    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult(output={"status": "completed", "output": "параллельное разветвление"})
