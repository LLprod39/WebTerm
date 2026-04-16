"""
studio/executor/context.py

ExecutionContext — shared state passed to every node during pipeline execution.
Nodes read upstream outputs, emit events, and resolve template variables through
this object. This decouples node logic from the executor engine.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from studio.models import Pipeline, PipelineRun


_TEMPLATE_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class ExecutionContext:
    """
    Shared execution state for one pipeline run.

    Attributes:
        run_id        — PipelineRun.pk
        user          — Django User who triggered the run
        pipeline      — Pipeline model instance
        node_outputs  — dict mapping node_id → output dict from BaseNode.execute()
        stop_event    — threading.Event; set to True to abort execution
        memory_store  — optional MemoryStore instance for agent nodes
        hook_manager  — optional HookManager for observability
        extra         — arbitrary extras injected by the executor
    """
    run_id: int
    user: Any
    pipeline: "Pipeline"
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    stop_event: threading.Event = field(default_factory=threading.Event)
    memory_store: Any = None
    hook_manager: Any = None
    extra: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Template resolution
    # ------------------------------------------------------------------

    def resolve_template(self, template: str) -> str:
        """
        Replace {variable} placeholders with values from node_outputs.
        If a variable is not found the placeholder is left unchanged.
        """
        if not template or "{" not in template:
            return template

        flat: dict[str, str] = {}
        for node_id, output in self.node_outputs.items():
            if isinstance(output, dict):
                for k, v in output.items():
                    flat[k] = str(v) if v is not None else ""
                    flat[f"{node_id}.{k}"] = str(v) if v is not None else ""

        def _replace(m: re.Match) -> str:
            key = m.group(1)
            return flat.get(key, m.group(0))

        return _TEMPLATE_PATTERN.sub(_replace, template)

    def get_upstream_output(self, node_id: str) -> dict[str, Any]:
        """Return the output dict of a specific upstream node, or empty dict."""
        return self.node_outputs.get(node_id, {})

    def record_node_output(self, node_id: str, output: dict[str, Any]) -> None:
        """Called by the executor after a node completes successfully."""
        self.node_outputs[node_id] = output

    @property
    def should_stop(self) -> bool:
        return self.stop_event.is_set()
