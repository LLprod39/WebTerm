from __future__ import annotations

import json

from django.contrib.auth.models import User

from core_ui.models import UserAppPermission
from studio.models import Pipeline, PipelineRun


def json_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


def report_node(node_id: str, label: str | None = None, *, extra: dict | None = None) -> dict:
    return {
        "id": node_id,
        "type": "output/report",
        "position": {"x": 0, "y": 0},
        "data": {"label": label or node_id, **(extra or {})},
    }


def build_run(pipeline: Pipeline, *, entry_node_id: str, context: dict | None = None) -> PipelineRun:
    return PipelineRun.objects.create(
        pipeline=pipeline,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=json.loads(json.dumps(pipeline.nodes or [])),
        edges_snapshot=json.loads(json.dumps(pipeline.edges or [])),
        context=dict(context or {}),
        entry_node_id=entry_node_id,
        routing_state={
            "entry_node_id": entry_node_id,
            "activated_nodes": [entry_node_id],
            "completed_nodes": [],
            "queued_nodes": [],
            "pending_merges": {},
        },
    )


def disable_activity_logging(monkeypatch) -> None:
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("studio.pipeline_agent_runtime.log_user_activity_async", _noop)
