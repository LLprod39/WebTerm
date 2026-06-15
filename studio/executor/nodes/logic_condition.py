from __future__ import annotations

from typing import TYPE_CHECKING

from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


@registry.register
class LogicConditionNode(BaseNode):
    node_type = "logic/condition"

    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        config = self.node_data if isinstance(self.node_data, dict) else {}
        source_node_id = str(config.get("source_node_id") or "")
        source_state = ctx.node_outputs.get(source_node_id, {})
        source_output = str(source_state.get("output") or "")
        check_type = str(config.get("check_type") or "contains")
        check_value = str(config.get("check_value") or "")

        passed = False
        if check_type == "contains":
            passed = check_value.lower() in source_output.lower()
        elif check_type == "not_contains":
            passed = check_value.lower() not in source_output.lower()
        elif check_type == "status_ok":
            passed = source_state.get("status") == "completed"
        elif check_type == "status_failed":
            passed = source_state.get("status") == "failed"
        elif check_type == "always_true":
            passed = True

        return NodeResult(output={"status": "completed", "passed": passed, "output": str(passed)})
