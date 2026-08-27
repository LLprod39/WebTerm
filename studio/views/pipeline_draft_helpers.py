from studio.model_policy import sanitize_pipeline_draft_response_for_user
from studio.models import (
    CURRENT_PIPELINE_GRAPH_VERSION,
    PipelineDraftRevision,
    PipelineDraftSession,
)
from studio.pipeline.pipeline_validation import validate_pipeline_definition
from studio.services import list_owned_server_payloads
from studio.services.pipeline_template_recommendations import (
    build_template_graph_patch,
    build_template_resource_plan,
    get_pilot_pipeline_template,
    recommend_pilot_pipeline_templates,
)
from studio.skill_registry import list_skills
from studio.views.common import (
    STUDIO_FEATURE_MCP,
    STUDIO_FEATURE_SKILLS,
    _user_has_feature,
)
from studio.views.mcp_views import _mcp_read_queryset_for_user
from studio.views.pipeline_assistant_preview import apply_pipeline_assistant_patch, pipeline_assistant_risk
from studio.views.skill_helpers import _can_read_skill, _skill_access_map, _skill_to_summary_dict

CLOSED_DRAFT_STATUSES = {
    PipelineDraftSession.STATUS_APPLIED,
    PipelineDraftSession.STATUS_DISCARDED,
}


def draft_queryset_for_user(user):
    qs = PipelineDraftSession.objects.select_related("owner", "source_pipeline", "applied_pipeline").prefetch_related(
        "revisions"
    )
    if getattr(user, "is_staff", False):
        return qs.order_by("-updated_at", "-id")
    return qs.filter(owner=user).order_by("-updated_at", "-id")


def get_draft_for_user(user, draft_id: int) -> PipelineDraftSession | None:
    return draft_queryset_for_user(user).filter(pk=draft_id).first()


def assistant_status(response: dict) -> str:
    if response.get("validation", {}).get("ok") is False:
        return PipelineDraftSession.STATUS_INVALID
    if response.get("risk", {}).get("level") == "dangerous":
        return PipelineDraftSession.STATUS_BLOCKED
    if response.get("questions"):
        return PipelineDraftSession.STATUS_NEEDS_INPUT
    return PipelineDraftSession.STATUS_READY


def revision_from_response(
    *,
    session: PipelineDraftSession,
    user_message: str,
    response: dict,
    preview_nodes: list[dict],
    preview_edges: list[dict],
) -> PipelineDraftRevision:
    response, preview_nodes = sanitize_pipeline_draft_response_for_user(
        session.owner,
        response,
        preview_nodes,
    )
    revision = PipelineDraftRevision.objects.create(
        session=session,
        user_message=user_message,
        assistant_reply=str(response.get("reply") or ""),
        target_node_id=str(response.get("target_node_id") or ""),
        node_patch=response.get("node_patch") if isinstance(response.get("node_patch"), dict) else {},
        graph_patch=response.get("graph_patch") if isinstance(response.get("graph_patch"), dict) else {},
        preview_nodes=preview_nodes,
        preview_edges=preview_edges,
        validation=response.get("validation") if isinstance(response.get("validation"), dict) else {},
        risk=response.get("risk") if isinstance(response.get("risk"), dict) else {},
        requirements=response.get("requirements") if isinstance(response.get("requirements"), list) else [],
        assumptions=response.get("assumptions") if isinstance(response.get("assumptions"), list) else [],
        questions=response.get("questions") if isinstance(response.get("questions"), list) else [],
        resource_plan=response.get("resource_plan") if isinstance(response.get("resource_plan"), dict) else {},
        node_explanations=response.get("node_explanations")
        if isinstance(response.get("node_explanations"), dict)
        else {},
        warnings=response.get("warnings") if isinstance(response.get("warnings"), list) else [],
        patch_summary=str(response.get("patch_summary") or ""),
        suggested_next_actions=(
            response.get("suggested_next_actions") if isinstance(response.get("suggested_next_actions"), list) else []
        ),
        confidence=response.get("confidence") if isinstance(response.get("confidence"), (int, float)) else None,
        response_payload=response,
    )
    session.status = assistant_status(response)
    session.save(update_fields=["status", "updated_at"])
    return revision


def latest_revision_graph(session: PipelineDraftSession) -> tuple[list, list]:
    latest = session.latest_revision()
    if latest:
        return latest.preview_nodes or [], latest.preview_edges or []
    snapshot = session.current_graph_snapshot if isinstance(session.current_graph_snapshot, dict) else {}
    return snapshot.get("nodes") or [], snapshot.get("edges") or []


def source_snapshot_graph(session: PipelineDraftSession) -> tuple[list, list]:
    snapshot = session.current_graph_snapshot if isinstance(session.current_graph_snapshot, dict) else {}
    return snapshot.get("nodes") or [], snapshot.get("edges") or []


def draft_validation_owner(draft: PipelineDraftSession):
    if draft.source_pipeline_id and draft.source_pipeline:
        return draft.source_pipeline.owner
    return draft.owner


def template_binding_context(draft: PipelineDraftSession) -> dict:
    owner = draft_validation_owner(draft)
    mcps = []
    if _user_has_feature(owner, STUDIO_FEATURE_MCP):
        mcps = [
            {
                "id": mcp.pk,
                "name": mcp.name,
                "description": mcp.description,
                "transport": mcp.transport,
                "last_test_ok": mcp.last_test_ok,
                "owner_id": mcp.owner_id,
            }
            for mcp in _mcp_read_queryset_for_user(owner)
        ]

    available_skills = []
    if _user_has_feature(owner, STUDIO_FEATURE_SKILLS):
        all_skills = list_skills()
        access_map = _skill_access_map([skill.slug for skill in all_skills])
        available_skills = [
            _skill_to_summary_dict(skill, owner, access_map.get(skill.slug.lower()))
            for skill in all_skills
            if _can_read_skill(owner, access_map.get(skill.slug.lower()))
        ]

    return {
        "available_servers": list_owned_server_payloads(owner),
        "available_mcp_servers": mcps,
        "available_skills": available_skills,
        "binding_query": f"{draft.title} {draft.user_goal}".strip(),
        "pipeline_name": draft.title,
        "user_message": draft.user_goal,
        "current_user_id": owner.id,
    }


def validate_latest_draft_revision(draft: PipelineDraftSession, latest: PipelineDraftRevision) -> dict:
    nodes = latest.preview_nodes or []
    edges = latest.preview_edges or []
    validation_errors = validate_pipeline_definition(
        nodes=nodes,
        edges=edges,
        owner=draft_validation_owner(draft),
        graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
    )
    validation = {"ok": not validation_errors, "errors": validation_errors, "warnings": []}
    risk = pipeline_assistant_risk(nodes, edges)
    dry_run = {
        "ok": validation["ok"] and risk.get("level") != "dangerous",
        "executed": False,
        "mode": "validate_only",
        "checks": ["graph_contract", "references", "risk_review"],
        "message": (
            "Dry-run validation checked graph structure, references and risk. "
            "It did not execute MCP tools, SSH commands, OPS actions or notifications."
        ),
    }

    response = dict(latest.response_payload or {})
    warnings = list(response.get("warnings") if isinstance(response.get("warnings"), list) else latest.warnings or [])
    dry_run_warning = "Dry-run validation completed without executing runtime actions."
    if dry_run_warning not in warnings:
        warnings.append(dry_run_warning)
    response["validation"] = validation
    response["risk"] = risk
    response["dry_run"] = dry_run
    response["warnings"] = warnings

    latest.validation = validation
    latest.risk = risk
    latest.warnings = warnings
    latest.response_payload = response
    latest.save(update_fields=["validation", "risk", "warnings", "response_payload"])

    draft.status = assistant_status(response)
    draft.save(update_fields=["status", "updated_at"])
    return {"validation": validation, "risk": risk, "dry_run": dry_run}


def template_revision_response(
    *,
    draft: PipelineDraftSession,
    template_slug: str,
) -> tuple[dict | None, list[dict], list[dict], str | None]:
    template = get_pilot_pipeline_template(template_slug)
    if template is None:
        return None, [], [], "Unknown pilot template"

    base_nodes, base_edges = source_snapshot_graph(draft)
    recommendations = recommend_pilot_pipeline_templates(
        user_message=draft.user_goal,
        pipeline_name=draft.title,
        limit=5,
    )
    if not any(item.get("slug") == template_slug for item in recommendations):
        manual_template = {
            "slug": template.get("slug"),
            "name": template.get("name"),
            "description": template.get("description"),
            "category": template.get("category"),
            "tags": template.get("tags") or [],
            "match_score": 0,
            "matched_terms": [],
            "node_types": list(
                dict.fromkeys(
                    str(node.get("type") or "")
                    for node in (template.get("nodes") or [])
                    if isinstance(node, dict) and str(node.get("type") or "")
                )
            ),
        }
        recommendations = [manual_template, *recommendations]

    binding_context = template_binding_context(draft)
    graph_patch = build_template_graph_patch(template, assistant_context=binding_context)
    preview_nodes, preview_edges = apply_pipeline_assistant_patch(base_nodes, base_edges, {"graph_patch": graph_patch})
    owner = draft_validation_owner(draft)
    validation_errors = validate_pipeline_definition(
        nodes=preview_nodes,
        edges=preview_edges,
        owner=owner,
        graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
    )
    validation = {"ok": not validation_errors, "errors": validation_errors, "warnings": []}
    risk = pipeline_assistant_risk(preview_nodes, preview_edges)
    template_name = str(template.get("name") or template.get("slug") or "Pilot template")
    response = {
        "reply": f"Selected `{template_name}` as the draft skeleton. Review resources and arguments before applying.",
        "selected_template": {
            "slug": template.get("slug"),
            "name": template_name,
            "source": "manual_template_switch",
        },
        "template_recommendations": recommendations,
        "requirements": [draft.user_goal] if draft.user_goal else [],
        "assumptions": [
            f"Pilot template selected manually: {template.get('slug')}.",
            "Approval, verification and report branches were preserved from the template.",
        ],
        "questions": [],
        "resource_plan": build_template_resource_plan(template, assistant_context=binding_context),
        "target_node_id": None,
        "node_patch": {},
        "graph_patch": graph_patch,
        "node_explanations": {
            str(node.get("ref")): "Step copied from the selected pilot template skeleton."
            for node in graph_patch.get("nodes", [])
            if isinstance(node, dict) and str(node.get("ref") or "")
        },
        "confidence": 0.68,
        "warnings": [],
        "patch_summary": f"Pilot template skeleton: {template_name}",
        "suggested_next_actions": ["Review resources", "Validate / dry-run", "Apply the draft"],
        "validation": validation,
        "risk": risk,
    }
    return response, preview_nodes, preview_edges, None
