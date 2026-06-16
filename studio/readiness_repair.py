from __future__ import annotations

from typing import Any

from studio.models import Pipeline


def quarantine_candidates(report: dict[str, Any], *, include_warnings: bool = False) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    statuses = {"error", "not_ready"}
    if include_warnings:
        statuses.add("warning")

    for pipeline in report.get("pipelines") or []:
        if pipeline.get("status") not in statuses:
            continue
        trigger_node_ids = [
            str(trigger.get("node_id") or "").strip()
            for trigger in pipeline.get("triggers") or []
            if trigger.get("is_active") and str(trigger.get("node_id") or "").strip()
        ]
        if not trigger_node_ids:
            continue
        issue_codes = sorted(
            {
                str(issue.get("code") or "").strip()
                for issue in pipeline.get("issues") or []
                if issue.get("severity") == "error" or include_warnings
            }
            - {""}
        )
        candidates.append(
            {
                "pipeline_id": pipeline.get("id"),
                "pipeline_name": pipeline.get("name"),
                "status": pipeline.get("status"),
                "trigger_node_ids": trigger_node_ids,
                "issue_codes": issue_codes,
                "errors": list(pipeline.get("errors") or []),
                "warnings": list(pipeline.get("warnings") or []),
            }
        )
    return candidates


def deactivate_pipeline_trigger_nodes(pipeline: Pipeline, node_ids: list[str]) -> list[str]:
    target_ids = {str(item or "").strip() for item in node_ids if str(item or "").strip()}
    if not target_ids:
        return []

    changed: list[str] = []
    nodes = []
    for raw_node in pipeline.nodes or []:
        node = dict(raw_node)
        node_id = str(node.get("id") or "").strip()
        node_type = str(node.get("type") or "").strip()
        if node_id in target_ids and node_type.startswith("trigger/"):
            data = dict(node.get("data") or {})
            if data.get("is_active", True) is not False:
                data["is_active"] = False
                node["data"] = data
                changed.append(node_id)
        nodes.append(node)

    if changed:
        pipeline.nodes = nodes
        pipeline.save(update_fields=["nodes", "updated_at"])
        pipeline.sync_triggers_from_nodes()
    return changed
