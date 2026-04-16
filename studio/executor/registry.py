"""
studio/executor/registry.py

NodeRegistry — maps node_type strings to BaseNode subclasses.

To add a new pipeline node type:
    1. Create studio/executor/nodes/<category>_<name>.py
    2. Subclass BaseNode, set node_type = "category/name"
    3. Call registry.register(YourNode) at module level OR add it to _AUTO_REGISTER below
    4. Write a test in tests/unit/studio/nodes/test_<name>.py

No changes to engine.py needed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from studio.executor.nodes.base import BaseNode


class NodeRegistry:
    """Singleton registry mapping node_type string → BaseNode subclass."""

    def __init__(self) -> None:
        self._registry: dict[str, Type["BaseNode"]] = {}

    def register(self, node_class: Type["BaseNode"]) -> Type["BaseNode"]:
        """
        Register a node class. Can be used as a decorator or called directly.

        Example:
            @registry.register
            class MyNode(BaseNode):
                node_type = "output/my_node"
        """
        node_type = node_class.node_type
        if not node_type:
            raise ValueError(f"{node_class.__name__} has no node_type defined")
        if node_type in self._registry and self._registry[node_type] is not node_class:
            raise ValueError(f"node_type {node_type!r} is already registered by {self._registry[node_type].__name__}")
        self._registry[node_type] = node_class
        return node_class

    def get(self, node_type: str) -> Type["BaseNode"] | None:
        """Return the node class for a given node_type, or None."""
        return self._registry.get(node_type)

    def create(self, node_type: str, node_id: str, node_data: dict) -> "BaseNode":
        """
        Instantiate a node by type. Raises KeyError if type is unknown.
        """
        cls = self._registry.get(node_type)
        if cls is None:
            raise KeyError(
                f"Unknown node type: {node_type!r}. "
                f"Registered types: {sorted(self._registry)}"
            )
        return cls(node_id=node_id, node_data=node_data)

    def list_types(self) -> list[str]:
        return sorted(self._registry.keys())

    def __contains__(self, node_type: str) -> bool:
        return node_type in self._registry

    def __len__(self) -> int:
        return len(self._registry)


# Global singleton — import and use this instance everywhere.
registry = NodeRegistry()
