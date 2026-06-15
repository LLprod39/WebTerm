from __future__ import annotations

from typing import TYPE_CHECKING

from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


@registry.register
class LogicMergeNode(BaseNode):
    node_type = "logic/merge"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        config = self.node_data if isinstance(self.node_data, dict) else {}
        mode = str(config.get("mode") or "all").strip().lower()
        if mode not in {"all", "any"}:
            mode = "all"

        mode_label = "любая ветка" if mode == "any" else "все ветки"
        return NodeResult(output={"status": "completed", "output": f"объединение: {mode_label}"})
