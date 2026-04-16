"""
studio/executor/engine.py

PipelineEngine — thin graph traversal + node dispatch.

Responsibility:
  1. Load pipeline graph (nodes + edges)
  2. Topological sort
  3. For each node: call registry.create(node_type, ...).execute(ctx)
  4. Pass results downstream via ExecutionContext

This file must NEVER contain node-specific logic.
Each node type lives in studio/executor/nodes/<type>.py.

NOTE (T-016): This engine is the TARGET architecture.
The existing studio/pipeline_executor.py still handles execution.
Nodes are being migrated one-by-one from pipeline_executor.py to
studio/executor/nodes/ — each migration step is a separate PR.
When all nodes are migrated, pipeline_executor.py is retired.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from typing import Any

from studio.executor.context import ExecutionContext
from studio.executor.nodes.base import NodeResult
from studio.executor.registry import registry

logger = logging.getLogger(__name__)


class PipelineEngine:
    """
    Graph-traversal engine for the node-registry architecture.

    Usage::
        engine = PipelineEngine(pipeline_definition, run_id=run_id, user=user)
        result = await engine.run(context)
    """

    def __init__(self, pipeline_definition: dict[str, Any], *, run_id: int, user: Any) -> None:
        self.nodes: list[dict] = pipeline_definition.get("nodes", [])
        self.edges: list[dict] = pipeline_definition.get("edges", [])
        self.run_id = run_id
        self.user = user

    # ------------------------------------------------------------------
    # Graph utilities
    # ------------------------------------------------------------------

    def _build_adjacency(self) -> tuple[dict[str, list[str]], dict[str, int]]:
        """Return (adjacency list, in-degree map) for topological sort."""
        successors: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {n["id"]: 0 for n in self.nodes}
        for edge in self.edges:
            src, dst = edge.get("source"), edge.get("target")
            if src and dst:
                successors[src].append(dst)
                in_degree[dst] = in_degree.get(dst, 0) + 1
        return successors, in_degree

    def _topological_order(self) -> list[str]:
        """Kahn's algorithm — raise RuntimeError on cycle."""
        successors, in_degree = self._build_adjacency()
        queue: deque[str] = deque(n for n, d in in_degree.items() if d == 0)
        order: list[str] = []
        while queue:
            node_id = queue.popleft()
            order.append(node_id)
            for succ in successors.get(node_id, []):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)
        if len(order) != len(self.nodes):
            raise RuntimeError("Pipeline graph contains a cycle")
        return order

    def _node_by_id(self) -> dict[str, dict]:
        return {n["id"]: n for n in self.nodes}

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run(self, ctx: ExecutionContext) -> dict[str, Any]:
        """
        Execute the pipeline in topological order.
        Returns a summary dict with per-node results.
        """
        try:
            order = self._topological_order()
        except RuntimeError as exc:
            logger.error("Pipeline %s: %s", self.run_id, exc)
            return {"ok": False, "error": str(exc)}

        node_by_id = self._node_by_id()
        results: dict[str, Any] = {}

        for node_id in order:
            if ctx.should_stop:
                logger.info("Pipeline %s: stop requested before node %s", self.run_id, node_id)
                break

            node_def = node_by_id.get(node_id)
            if not node_def:
                continue

            node_type: str = node_def.get("type", "")
            node_data: dict = node_def.get("data", {})

            if node_type not in registry:
                # Unknown node type — skip with a warning.
                # pipeline_executor.py handles legacy types during migration.
                logger.warning(
                    "Pipeline %s: node %s has unknown type %r (not in registry) — skipping",
                    self.run_id, node_id, node_type,
                )
                continue

            node = registry.create(node_type, node_id=node_id, node_data=node_data)
            logger.debug("Pipeline %s: executing node %s (%s)", self.run_id, node_id, node_type)

            try:
                result: NodeResult = await node.execute(ctx)
            except Exception as exc:
                logger.exception("Pipeline %s: node %s raised %s", self.run_id, node_id, exc)
                result = NodeResult(error=str(exc), stop_pipeline=True)

            results[node_id] = {
                "ok": result.ok,
                "output": result.output,
                "error": result.error,
            }
            if result.ok:
                ctx.record_node_output(node_id, result.output)
            if result.stop_pipeline:
                logger.warning("Pipeline %s: node %s requested stop", self.run_id, node_id)
                break

        return {"ok": True, "node_results": results}
