from __future__ import annotations

from studio.model_helpers import collect_monitoring_filters
from studio.model_policy import sanitize_pipeline_nodes_for_user


def sync_pipeline_triggers_from_nodes(pipeline) -> None:
    from studio.models import PipelineTrigger

    trigger_type_map = {
        "trigger/manual": PipelineTrigger.TYPE_MANUAL,
        "trigger/webhook": PipelineTrigger.TYPE_WEBHOOK,
        "trigger/schedule": PipelineTrigger.TYPE_SCHEDULE,
        "trigger/monitoring": PipelineTrigger.TYPE_MONITORING,
    }
    keep_node_ids: set[str] = set()

    for node in pipeline.nodes or []:
        node_type = str(node.get("type") or "")
        trigger_type = trigger_type_map.get(node_type)
        node_id = str(node.get("id") or "").strip()
        if not trigger_type or not node_id:
            continue

        data = node.get("data") or {}
        payload_map = data.get("webhook_payload_map")
        if not isinstance(payload_map, dict):
            payload_map = {}

        defaults = {
            "name": (str(data.get("label") or "").strip() or node_id),
            "trigger_type": trigger_type,
            "is_active": bool(data.get("is_active", True)),
            "cron_expression": str(data.get("cron_expression") or "").strip(),
            "webhook_payload_map": payload_map,
            "monitoring_filters": collect_monitoring_filters(data),
        }
        existing = list(pipeline.triggers.filter(node_id=node_id).order_by("id"))
        if existing:
            trigger = existing[0]
            created = False
            if len(existing) > 1:
                pipeline.triggers.filter(node_id=node_id).exclude(pk=trigger.pk).delete()
        else:
            trigger = PipelineTrigger.objects.create(
                pipeline=pipeline,
                node_id=node_id,
                **defaults,
            )
            created = True

        if not created:
            changed = False
            for field, value in defaults.items():
                if getattr(trigger, field) != value:
                    setattr(trigger, field, value)
                    changed = True
            if changed:
                trigger.save()

        keep_node_ids.add(node_id)

    if keep_node_ids:
        pipeline.triggers.exclude(node_id__in=keep_node_ids).delete()
    else:
        pipeline.triggers.all().delete()


def instantiate_template_for_user(template, user):
    from studio.models import CURRENT_PIPELINE_GRAPH_VERSION, Pipeline

    nodes = sanitize_pipeline_nodes_for_user(user, list(template.nodes))
    edges = list(template.edges)

    if template.slug == "server-update-approval":
        from .services.server_access import get_preferred_owned_server_id

        server_id = get_preferred_owned_server_id(user, preferred_name="backup-01", fallback_order_by="name")
        if server_id:
            server_ids = [server_id]
            for node in nodes:
                node_id = node.get("id")
                if node_id in ("n2", "n8", "n10"):
                    data = dict(node.get("data") or {})
                    data["server_ids"] = server_ids
                    node = dict(node)
                    node["data"] = data
                    for index, current_node in enumerate(nodes):
                        if current_node.get("id") == node_id:
                            nodes[index] = node
                            break

    pipeline = Pipeline.objects.create(
        name=template.name,
        description=template.description,
        icon=template.icon,
        tags=template.tags,
        nodes=nodes,
        edges=edges,
        graph_version=template.graph_version or CURRENT_PIPELINE_GRAPH_VERSION,
        owner=user,
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline
