"""
studio/executor/nodes/base.py

Base abstractions for the Pipeline Node Registry.
Every pipeline node type must subclass BaseNode and implement execute().

Usage:
    from studio.executor.nodes.base import BaseNode, NodeResult

    class SlackOutputNode(BaseNode):
        node_type = "output/slack"

        async def execute(self, ctx: "ExecutionContext") -> NodeResult:
            ...
            return NodeResult(output={"sent": True})
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from studio.executor.context import ExecutionContext


@dataclass
class NodeResult:
    """
    Result returned by BaseNode.execute().
    output      — dict passed downstream to dependent nodes via context.node_outputs
    error       — human-readable error string if execution failed
    stop_pipeline — if True, executor halts the entire pipeline
    """
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    stop_pipeline: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None


class BaseNode(ABC):
    """
    Abstract base for all pipeline node types.

    Subclasses:
      - Set class attribute `node_type` to the string identifier (e.g. "output/slack")
      - Implement `async def execute(self, ctx: ExecutionContext) -> NodeResult`
      - Register via NodeRegistry.register(MyNode) in studio/executor/registry.py
    """

    node_type: str = ""

    def __init__(self, node_id: str, node_data: dict[str, Any]) -> None:
        if not self.node_type:
            raise TypeError(f"{type(self).__name__} must define a non-empty node_type class attribute")
        self.node_id = node_id
        self.node_data = node_data

    @abstractmethod
    async def execute(self, ctx: "ExecutionContext") -> NodeResult:
        """Execute this node and return the result."""
        ...

    def __repr__(self) -> str:
        return f"<{type(self).__name__} id={self.node_id!r} type={self.node_type!r}>"
