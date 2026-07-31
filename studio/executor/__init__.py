"""
studio/executor — Pipeline Node Registry architecture.

Public API:
    from studio.executor.registry import registry
    from studio.executor.context import ExecutionContext
    from studio.executor.nodes.base import BaseNode, NodeResult
"""

from studio.executor.context import ExecutionContext  # noqa: F401
from studio.executor.registry import registry  # noqa: F401
