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
    from studio.models import Pipeline


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
    pipeline: Pipeline
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
        base_context = self.extra.get("context")
        if isinstance(base_context, dict):
            for key, value in base_context.items():
                flat[str(key)] = str(value) if value is not None else ""
        if self.pipeline is not None:
            flat["pipeline_name"] = str(getattr(self.pipeline, "name", "") or "")
        flat["run_id"] = str(self.run_id)
        for key, value in (self.extra.get("runtime") or {}).items():
            flat[str(key)] = str(value) if value is not None else ""
        for node_id, output in self.node_outputs.items():
            if isinstance(output, dict):
                for k, v in output.items():
                    flat[k] = str(v) if v is not None else ""
                    flat[f"{node_id}.{k}"] = str(v) if v is not None else ""

        def _replace(m: re.Match) -> str:
            key = m.group(1)
            return flat.get(key, m.group(0))

        return _TEMPLATE_PATTERN.sub(_replace, template)

    def get_variable(self, key: str, default: Any = "") -> Any:
        """Return a value from runtime/base context or upstream node outputs."""
        runtime = self.extra.get("runtime")
        if isinstance(runtime, dict) and key in runtime:
            return runtime[key]
        base_context = self.extra.get("context")
        if isinstance(base_context, dict) and key in base_context:
            return base_context[key]
        if key == "pipeline_name" and self.pipeline is not None:
            return getattr(self.pipeline, "name", default)
        if key == "run_id":
            return self.run_id
        for node_id, output in self.node_outputs.items():
            if key == node_id:
                return output.get("output", default) if isinstance(output, dict) else default
            if isinstance(output, dict):
                if key in output:
                    return output[key]
                if key == f"{node_id}_output":
                    return output.get("output", default)
                if key == f"{node_id}_error":
                    return output.get("error", default)
                if key == f"{node_id}_status":
                    return output.get("status", default)
        return default

    def get_upstream_output(self, node_id: str) -> dict[str, Any]:
        """Return the output dict of a specific upstream node, or empty dict."""
        return self.node_outputs.get(node_id, {})

    def record_node_output(self, node_id: str, output: dict[str, Any]) -> None:
        """Called by the executor after a node completes successfully."""
        self.node_outputs[node_id] = output

    @property
    def should_stop(self) -> bool:
        return self.stop_event.is_set()
