"""Prometheus metrics owned by the Studio pipeline domain."""

from collections import defaultdict
from datetime import datetime

from django.apps import apps as django_apps
from django.utils import timezone

from studio.dispatch_models import PipelineRunDispatch


def _label(value: str) -> str:
    return str(value or "unknown").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _timestamp(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _node_durations() -> dict[str, list[float]]:
    PipelineRun = django_apps.get_model("studio", "PipelineRun")
    durations: dict[str, list[float]] = defaultdict(list)
    for run in PipelineRun.objects.exclude(node_states={}).order_by("-created_at")[:500]:
        node_types = {
            str(node.get("id") or ""): str(node.get("type") or "unknown")
            for node in (run.nodes_snapshot or [])
            if isinstance(node, dict)
        }
        for node_id, state in (run.node_states or {}).items():
            if not isinstance(state, dict):
                continue
            started = _timestamp(state.get("started_at"))
            finished = _timestamp(state.get("finished_at"))
            if started and finished and (finished - started).total_seconds() >= 0:
                durations[node_types.get(str(node_id), "unknown")].append((finished - started).total_seconds())
    return durations


def studio_prometheus_lines() -> list[str]:
    now = timezone.now()
    queued = PipelineRunDispatch.objects.filter(status=PipelineRunDispatch.STATUS_QUEUED)
    oldest = queued.order_by("queued_at").values_list("queued_at", flat=True).first()
    lines = [
        "# HELP webterm_pipeline_queue_depth Pipeline dispatches waiting for a worker.",
        "# TYPE webterm_pipeline_queue_depth gauge",
        f"webterm_pipeline_queue_depth {queued.count()}",
        "# HELP webterm_pipeline_queue_oldest_age_seconds Age of the oldest waiting pipeline dispatch.",
        "# TYPE webterm_pipeline_queue_oldest_age_seconds gauge",
        f"webterm_pipeline_queue_oldest_age_seconds {max((now - oldest).total_seconds(), 0.0) if oldest else 0.0:.6f}",
        "# HELP webterm_pipeline_node_latency_seconds Pipeline node execution latency by node type.",
        "# TYPE webterm_pipeline_node_latency_seconds summary",
    ]
    for node_type, values in sorted(_node_durations().items()):
        label = _label(node_type)
        lines.append(f'webterm_pipeline_node_latency_seconds_count{{node_type="{label}"}} {len(values)}')
        lines.append(f'webterm_pipeline_node_latency_seconds_sum{{node_type="{label}"}} {sum(values):.6f}')
    return lines
