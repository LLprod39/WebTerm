"""Durable checkpoint preparation and operator-gated pipeline resumption."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from studio.models import PipelineRun
from studio.node_manifest import get_node_manifest

_AMBIGUOUS_STATUSES = {"running", "stopped", "pending_resume"}


class PipelineResumeError(ValueError):
    def __init__(self, message: str, *, code: str = "pipeline_resume_invalid", details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


class PipelineResumeConfirmationRequired(PipelineResumeError):
    def __init__(self, nodes: list[dict[str, str]]):
        super().__init__(
            "Operator confirmation is required before retrying non-idempotent nodes.",
            code="resume_confirmation_required",
            details={"nodes": nodes},
        )


@dataclass(slots=True)
class ResumeCheckpoint:
    node_states: dict[str, dict[str, Any]]
    routing_state: dict[str, Any]
    retry_node_ids: list[str]
    confirmation_nodes: list[dict[str, str]]


def _node_lookup(run: PipelineRun) -> dict[str, dict[str, Any]]:
    return {
        str(node.get("id") or ""): node
        for node in (run.nodes_snapshot or [])
        if isinstance(node, dict) and str(node.get("id") or "").strip()
    }


def _failed_node_requires_retry(node: dict[str, Any]) -> bool:
    node_type = str(node.get("type") or "")
    on_failure = str((node.get("data") or {}).get("on_failure") or "continue").strip().lower()
    return on_failure == "abort" and (node_type.startswith("agent/") or node_type.startswith("output/"))


def _resume_retry_node_ids(run: PipelineRun) -> list[str]:
    nodes = _node_lookup(run)
    states = run.node_states if isinstance(run.node_states, dict) else {}
    retry: list[str] = []
    for node_id, raw_state in states.items():
        node = nodes.get(str(node_id))
        if node is None or not isinstance(raw_state, dict):
            continue
        status = str(raw_state.get("status") or "").strip().lower()
        if status in _AMBIGUOUS_STATUSES or (status == "failed" and _failed_node_requires_retry(node)):
            retry.append(str(node_id))
    return sorted(set(retry))


def node_type_idempotency(node_type: str) -> str:
    manifest = get_node_manifest(node_type)
    value = str(getattr(manifest, "idempotency", "non_idempotent") or "non_idempotent").strip().lower()
    return "idempotent" if value == "idempotent" else "non_idempotent"


def _confirmation_nodes(run: PipelineRun, retry_node_ids: list[str]) -> list[dict[str, str]]:
    nodes = _node_lookup(run)
    required: list[dict[str, str]] = []
    for node_id in retry_node_ids:
        node = nodes.get(node_id) or {}
        node_type = str(node.get("type") or "")
        if node_type_idempotency(node_type) == "idempotent":
            continue
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        required.append(
            {
                "id": node_id,
                "type": node_type,
                "label": str(data.get("label") or node_id),
                "idempotency": "non_idempotent",
            }
        )
    return required


def build_resume_checkpoint(run: PipelineRun) -> ResumeCheckpoint:
    nodes = _node_lookup(run)
    states = deepcopy(run.node_states) if isinstance(run.node_states, dict) else {}
    routing = deepcopy(run.routing_state) if isinstance(run.routing_state, dict) else {}
    entry_node_id = str(routing.get("entry_node_id") or run.entry_node_id or "").strip()
    completed = {str(item) for item in (routing.get("completed_nodes") or []) if str(item) in nodes}
    activated = {str(item) for item in (routing.get("activated_nodes") or []) if str(item) in nodes}
    queued = [str(item) for item in (routing.get("queued_nodes") or []) if str(item) in nodes]
    retry_node_ids = _resume_retry_node_ids(run)

    for node_id in retry_node_ids:
        completed.discard(node_id)
        activated.add(node_id)
        if node_id not in queued:
            queued.append(node_id)
        state = states.get(node_id) if isinstance(states.get(node_id), dict) else {}
        previous_status = str(state.get("status") or "")
        states[node_id] = {
            **state,
            "status": "pending_resume",
            "resume_from_status": previous_status,
            "resume_requested_at": timezone.now().isoformat(),
        }

    if entry_node_id:
        activated.add(entry_node_id)
        completed.add(entry_node_id)
    routing.update(
        {
            "entry_node_id": entry_node_id,
            "activated_nodes": sorted(activated),
            "completed_nodes": sorted(completed),
            "queued_nodes": list(dict.fromkeys(queued)),
            "pending_merges": routing.get("pending_merges") if isinstance(routing.get("pending_merges"), dict) else {},
        }
    )
    return ResumeCheckpoint(
        node_states=states,
        routing_state=routing,
        retry_node_ids=retry_node_ids,
        confirmation_nodes=_confirmation_nodes(run, retry_node_ids),
    )


@transaction.atomic
def request_pipeline_run_resume(
    run_id: int,
    *,
    actor,
    confirm_non_idempotent: bool = False,
) -> PipelineRun:
    run = (
        PipelineRun.objects.select_for_update()
        .select_related("pipeline", "pipeline__owner", "triggered_by")
        .get(pk=run_id)
    )
    if run.status not in {PipelineRun.STATUS_FAILED, PipelineRun.STATUS_STOPPED}:
        raise PipelineResumeError("Only failed or stopped pipeline runs can be resumed.")

    checkpoint = build_resume_checkpoint(run)
    if checkpoint.confirmation_nodes and not confirm_non_idempotent:
        raise PipelineResumeConfirmationRequired(checkpoint.confirmation_nodes)

    previous_status = run.status
    trigger_data = dict(run.trigger_data) if isinstance(run.trigger_data, dict) else {}
    resume_history = list(trigger_data.get("resume_history") or [])
    resume_history.append(
        {
            "requested_at": timezone.now().isoformat(),
            "requested_by_id": getattr(actor, "pk", None),
            "previous_status": previous_status,
            "retry_node_ids": checkpoint.retry_node_ids,
            "confirmed_non_idempotent": bool(confirm_non_idempotent),
        }
    )
    trigger_data["resume_history"] = resume_history[-20:]
    run.status = PipelineRun.STATUS_PENDING
    run.finished_at = None
    run.error = ""
    run.runtime_control = {}
    run.trigger_data = trigger_data
    run.save(update_fields=["status", "finished_at", "error", "runtime_control", "trigger_data"])

    from studio.dispatch import requeue_pipeline_run_dispatch

    requeue_pipeline_run_dispatch(
        run,
        metadata={
            "resume": True,
            "requested_by_id": getattr(actor, "pk", None),
            "non_idempotent_confirmed": bool(confirm_non_idempotent),
            "confirmed_node_ids": [item["id"] for item in checkpoint.confirmation_nodes],
        },
    )
    return run
