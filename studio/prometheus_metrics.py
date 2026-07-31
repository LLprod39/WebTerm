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


def _dispatch_health(now) -> tuple[int, int, int, int]:
    """Return (inflight, stalled, retrying, failed) dispatch counts."""
    claimed = PipelineRunDispatch.objects.filter(status=PipelineRunDispatch.STATUS_CLAIMED)
    return (
        claimed.filter(lease_expires_at__gt=now).count(),
        claimed.filter(lease_expires_at__lte=now).count(),
        PipelineRunDispatch.objects.filter(
            status__in=[PipelineRunDispatch.STATUS_QUEUED, PipelineRunDispatch.STATUS_CLAIMED],
            attempt_count__gt=1,
        ).count(),
        PipelineRunDispatch.objects.filter(status=PipelineRunDispatch.STATUS_FAILED).count(),
    )


def _open_dead_letters() -> int:
    PipelineNodeDeadLetter = django_apps.get_model("studio", "PipelineNodeDeadLetter")
    return PipelineNodeDeadLetter.objects.filter(status=PipelineNodeDeadLetter.STATUS_OPEN).count()


def studio_prometheus_lines() -> list[str]:
    now = timezone.now()
    queued = PipelineRunDispatch.objects.filter(status=PipelineRunDispatch.STATUS_QUEUED)
    oldest = queued.order_by("queued_at").values_list("queued_at", flat=True).first()
    inflight, stalled, retrying, failed = _dispatch_health(now)
    lines = [
        "# HELP webterm_pipeline_queue_depth Pipeline dispatches waiting for a worker.",
        "# TYPE webterm_pipeline_queue_depth gauge",
        f"webterm_pipeline_queue_depth {queued.count()}",
        "# HELP webterm_pipeline_queue_oldest_age_seconds Age of the oldest waiting pipeline dispatch.",
        "# TYPE webterm_pipeline_queue_oldest_age_seconds gauge",
        f"webterm_pipeline_queue_oldest_age_seconds {max((now - oldest).total_seconds(), 0.0) if oldest else 0.0:.6f}",
        "# HELP webterm_pipeline_inflight_dispatches Pipeline dispatches held by a worker with a live lease.",
        "# TYPE webterm_pipeline_inflight_dispatches gauge",
        f"webterm_pipeline_inflight_dispatches {inflight}",
        "# HELP webterm_pipeline_stalled_dispatches Claimed dispatches whose lease expired without a heartbeat.",
        "# TYPE webterm_pipeline_stalled_dispatches gauge",
        f"webterm_pipeline_stalled_dispatches {stalled}",
        "# HELP webterm_pipeline_retrying_dispatches Dispatches queued or claimed on a second or later attempt.",
        "# TYPE webterm_pipeline_retrying_dispatches gauge",
        f"webterm_pipeline_retrying_dispatches {retrying}",
        "# HELP webterm_pipeline_failed_dispatches Dispatches that exhausted their permitted attempts.",
        "# TYPE webterm_pipeline_failed_dispatches gauge",
        f"webterm_pipeline_failed_dispatches {failed}",
        "# HELP webterm_pipeline_open_dead_letters Pipeline nodes parked for explicit operator review.",
        "# TYPE webterm_pipeline_open_dead_letters gauge",
        f"webterm_pipeline_open_dead_letters {_open_dead_letters()}",
        "# HELP webterm_pipeline_node_latency_seconds Pipeline node execution latency by node type.",
        "# TYPE webterm_pipeline_node_latency_seconds summary",
    ]
    for node_type, values in sorted(_node_durations().items()):
        label = _label(node_type)
        lines.append(f'webterm_pipeline_node_latency_seconds_count{{node_type="{label}"}} {len(values)}')
        lines.append(f'webterm_pipeline_node_latency_seconds_sum{{node_type="{label}"}} {sum(values):.6f}')
    return lines
