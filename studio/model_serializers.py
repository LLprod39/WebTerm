from __future__ import annotations


def agent_config_to_dict(agent) -> dict:
    from .skill_policy import compile_skill_policies
    from .skill_registry import resolve_skills

    skills, skill_errors = resolve_skills(agent.skill_slugs or [])
    _, policy_errors = compile_skill_policies(skills)
    return {
        "id": agent.pk,
        "name": agent.name,
        "description": agent.description,
        "icon": agent.icon,
        "system_prompt": agent.system_prompt,
        "instructions": agent.instructions,
        "model": agent.model,
        "max_iterations": agent.max_iterations,
        "allowed_tools": agent.allowed_tools,
        "sudo_policy": agent.sudo_policy,
        "mcp_servers": list(agent.mcp_servers.filter(owner=agent.owner).values("id", "name", "transport")),
        "skill_slugs": list(agent.skill_slugs or []),
        "skills": [skill.to_summary_dict() for skill in skills],
        "skill_errors": [*skill_errors, *policy_errors],
        "server_scope": list(agent.server_scope.filter(user=agent.owner).values("id", "name")),
    }


def pipeline_get_last_run(pipeline):
    from .models import PipelineRun

    live_run = (
        pipeline.runs.filter(
            status__in=[
                PipelineRun.STATUS_PENDING,
                PipelineRun.STATUS_RUNNING,
            ]
        )
        .order_by("-created_at", "-id")
        .first()
    )
    if live_run:
        return live_run
    return pipeline.runs.order_by("-created_at", "-id").first()


def pipeline_get_trigger_summary(pipeline) -> dict:
    from .models import PipelineTrigger

    triggers = list(pipeline.triggers.all())
    active_triggers = [trigger for trigger in triggers if trigger.is_active]
    last_triggered_at = None
    for trigger in active_triggers:
        if trigger.last_triggered_at and (last_triggered_at is None or trigger.last_triggered_at > last_triggered_at):
            last_triggered_at = trigger.last_triggered_at
    return {
        "active_total": len(active_triggers),
        "active_manual": sum(1 for trigger in active_triggers if trigger.trigger_type == PipelineTrigger.TYPE_MANUAL),
        "active_webhook": sum(1 for trigger in active_triggers if trigger.trigger_type == PipelineTrigger.TYPE_WEBHOOK),
        "active_schedule": sum(
            1 for trigger in active_triggers if trigger.trigger_type == PipelineTrigger.TYPE_SCHEDULE
        ),
        "active_monitoring": sum(
            1 for trigger in active_triggers if trigger.trigger_type == PipelineTrigger.TYPE_MONITORING
        ),
        "last_triggered_at": last_triggered_at.isoformat() if last_triggered_at else None,
    }


def pipeline_to_list_dict(pipeline) -> dict:
    last_run = pipeline.get_last_run()
    return {
        "id": pipeline.pk,
        "name": pipeline.name,
        "description": pipeline.description,
        "icon": pipeline.icon,
        "tags": pipeline.tags,
        "is_shared": pipeline.is_shared,
        "is_template": pipeline.is_template,
        "graph_version": pipeline.graph_version,
        "node_count": len(pipeline.nodes) if pipeline.nodes else 0,
        "created_at": pipeline.created_at.isoformat(),
        "updated_at": pipeline.updated_at.isoformat(),
        "trigger_summary": pipeline.get_trigger_summary(),
        "last_run": {
            "id": last_run.pk,
            "status": last_run.status,
            "started_at": last_run.started_at.isoformat() if last_run.started_at else None,
            "finished_at": last_run.finished_at.isoformat() if last_run.finished_at else None,
        }
        if last_run
        else None,
    }


def pipeline_to_detail_dict(pipeline) -> dict:
    from studio.pipeline_secrets import redact_pipeline_nodes

    payload = pipeline.to_list_dict()
    payload["nodes"] = redact_pipeline_nodes(pipeline.nodes)
    payload["edges"] = pipeline.edges
    payload["triggers"] = [trigger.to_dict() for trigger in pipeline.triggers.order_by("created_at", "id")]
    return payload


def pipeline_run_to_dict(run) -> dict:
    from studio.pipeline_secrets import redact_pipeline_nodes, serialize_pipeline_node_states

    trigger = getattr(run, "trigger", None)
    return {
        "id": run.pk,
        "pipeline_id": run.pipeline_id,
        "pipeline_name": run.pipeline.name,
        "status": run.status,
        "node_states": serialize_pipeline_node_states(run.node_states),
        "nodes_snapshot": redact_pipeline_nodes(run.nodes_snapshot),
        "context": run.context,
        "summary": run.summary,
        "error": run.error,
        "duration_seconds": run.duration_seconds,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat(),
        "triggered_by": run.triggered_by.username if run.triggered_by else None,
        "trigger_id": trigger.pk if trigger else None,
        "entry_node_id": run.entry_node_id,
        "trigger_type": trigger.trigger_type if trigger else "manual",
        "trigger_name": trigger.name if trigger else "",
        "trigger_node_id": trigger.node_id if trigger else run.entry_node_id,
    }


def pipeline_template_to_dict(template) -> dict:
    return {
        "slug": template.slug,
        "name": template.name,
        "description": template.description,
        "icon": template.icon,
        "category": template.category,
        "tags": template.tags,
        "node_count": len(template.nodes),
        "graph_version": template.graph_version,
    }
