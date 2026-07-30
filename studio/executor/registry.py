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

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from studio.executor.nodes.base import BaseNode


class NodeRegistry:
    """Singleton registry mapping node_type string → BaseNode subclass."""

    def __init__(self) -> None:
        self._registry: dict[str, type[BaseNode]] = {}

    def register(self, node_class: type[BaseNode]) -> type[BaseNode]:
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

    def get(self, node_type: str) -> type[BaseNode] | None:
        """Return the node class for a given node_type, or None."""
        return self._registry.get(node_type)

    def create(self, node_type: str, node_id: str, node_data: dict) -> BaseNode:
        """
        Instantiate a node by type. Raises KeyError if type is unknown.
        """
        cls = self._registry.get(node_type)
        if cls is None:
            raise KeyError(f"Unknown node type: {node_type!r}. Registered types: {sorted(self._registry)}")
        return cls(node_id=node_id, node_data=node_data)

    def list_types(self) -> list[str]:
        return sorted(self._registry.keys())

    def snapshot(self) -> dict[str, type[BaseNode]]:
        """Return a copy of the current registrations for temporary overrides."""
        return dict(self._registry)

    def replace_all(self, node_classes: Mapping[str, type[BaseNode]]) -> None:
        """Replace registrations in-place while keeping the singleton object stable."""
        previous = self._registry
        self._registry = {}
        try:
            for node_type, node_class in node_classes.items():
                if getattr(node_class, "node_type", "") != node_type:
                    raise ValueError(
                        f"registry key {node_type!r} does not match "
                        f"{node_class.__name__}.node_type={getattr(node_class, 'node_type', None)!r}"
                    )
                self.register(node_class)
        except Exception:
            self._registry = previous
            raise

    def clear(self) -> None:
        """Clear registrations in-place for tests or host-managed registry reloads."""
        self._registry.clear()

    def __contains__(self, node_type: str) -> bool:
        return node_type in self._registry

    def __len__(self) -> int:
        return len(self._registry)


# Global singleton — import and use this instance everywhere.
registry = NodeRegistry()


def get_node_registry() -> NodeRegistry:
    """Return the process-global node registry."""
    return registry


def snapshot_node_registry() -> dict[str, type[BaseNode]]:
    """Return a restorable snapshot of the process-global node registry."""
    return registry.snapshot()


def restore_node_registry(snapshot: Mapping[str, type[BaseNode]]) -> None:
    """Restore the process-global node registry without replacing the singleton."""
    registry.replace_all(snapshot)


def clear_node_registry() -> None:
    """Clear the process-global node registry without replacing the singleton."""
    registry.clear()


def mutation_preview_required(node_type: str, node_data: dict) -> bool:
    """Evaluate the built-in mutation-preview contract without coupling the executor to its implementation."""
    from studio.executor.change_preview import node_requires_change_preview

    return node_requires_change_preview(node_type, node_data)


def mutation_preview_valid(value) -> bool:
    """Validate a mutation preview at the registry/executor boundary."""
    from studio.executor.change_preview import valid_change_preview

    return valid_change_preview(value)
