"""
studio/executor — Pipeline Node Registry architecture.

Public API:
    from studio.executor.registry import registry
    from studio.executor.context import ExecutionContext
    from studio.executor.engine import PipelineEngine
    from studio.executor.nodes.base import BaseNode, NodeResult

Migration status (T-016): nodes are being moved from pipeline_executor.py
one at a time. Check studio/executor/nodes/ for migrated node types.
"""
from studio.executor.registry import registry  # noqa: F401
from studio.executor.context import ExecutionContext  # noqa: F401
from studio.executor.engine import PipelineEngine  # noqa: F401
