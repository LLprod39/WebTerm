"""
Studio pipeline assistant endpoint.
"""

import asyncio

from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from studio.models import CURRENT_PIPELINE_GRAPH_VERSION
from studio.pipeline_validation import validate_pipeline_definition
from studio.services import (
    PipelineAssistantError,
    build_pipeline_assistant_response,
    get_pipeline_assistant_context,
    list_owned_server_payloads,
)
from studio.skill_registry import SkillNotFoundError, get_skill, list_skills, normalise_skill_slugs
from studio.views.agent_helpers import _agent_read_queryset_for_user
from studio.views.common import (
    STUDIO_FEATURE_AGENTS,
    STUDIO_FEATURE_MCP,
    STUDIO_FEATURE_PIPELINES,
    STUDIO_FEATURE_SKILLS,
    _err,
    _json_body,
    _ok,
    _user_has_feature,
)
from studio.views.mcp_views import _inspect_mcp_server, _mcp_read_queryset_for_user
from studio.views.pipeline_assistant_preview import (
    apply_pipeline_assistant_patch,
    assistant_patch_summary,
    compact_node_summary,
    compact_selected_node,
    pipeline_assistant_risk,
)
from studio.views.pipeline_helpers import _get_pipeline
from studio.views.skill_helpers import _can_read_skill, _skill_access_map, _skill_to_summary_dict


@require_feature(STUDIO_FEATURE_PIPELINES)
@require_http_methods(["POST"])
def api_pipeline_assistant(request):
    data = _json_body(request)
    user_message = str(data.get("user_message") or "").strip()
    pipeline_name = str(data.get("pipeline_name") or "").strip() or "Untitled pipeline"
    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    selected_node = data.get("selected_node")
    history = data.get("history") or []
    intent = str(data.get("intent") or ("create" if not nodes else "edit")).strip().lower()
    if intent not in {"create", "edit", "validate", "fix_run"}:
        intent = "edit"
    draft_mode = data.get("draft_mode", True) is not False
    raw_last_validation_errors = data.get("last_validation_errors") or []
    if not isinstance(raw_last_validation_errors, list):
        raw_last_validation_errors = []
    last_validation_errors = [str(item).strip()[:1000] for item in raw_last_validation_errors if str(item).strip()][:20]
    last_run_summary = data.get("last_run_summary") if isinstance(data.get("last_run_summary"), dict) else {}

    if not user_message:
        return _err("user_message is required")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return _err("nodes and edges must be arrays")
    if selected_node not in (None, "") and not isinstance(selected_node, dict):
        return _err("selected_node must be an object or null")
    if not isinstance(history, list):
        return _err("history must be an array")

    pipeline_id_raw = data.get("pipeline_id")
    assistant_pipeline = None
    if pipeline_id_raw not in (None, ""):
        try:
            pipeline_id = int(pipeline_id_raw)
        except (TypeError, ValueError):
            return _err("pipeline_id must be an integer")
        assistant_pipeline = _get_pipeline(request, pipeline_id)
        if assistant_pipeline is None:
            return _err("Pipeline not found", 404)

    selected_node_id = str((selected_node or {}).get("id") or "").strip()

    node_map = {
        str(item.get("id") or ""): item
        for item in nodes
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    if selected_node_id and selected_node_id not in node_map:
        node_map[selected_node_id] = selected_node
    current_node = node_map[selected_node_id] if selected_node_id and selected_node_id in node_map else None

    conversation_history = []
    for item in history[-10:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        conversation_history.append({"role": role, "content": content[:4000]})

    if current_node:
        incoming_ids = [
            str(edge.get("source") or "")
            for edge in edges
            if isinstance(edge, dict) and str(edge.get("target") or "") == selected_node_id
        ]
        outgoing_ids = [
            str(edge.get("target") or "")
            for edge in edges
            if isinstance(edge, dict) and str(edge.get("source") or "") == selected_node_id
        ]
        incoming_nodes = [compact_node_summary(node_map[node_id]) for node_id in incoming_ids if node_id in node_map]
        outgoing_nodes = [compact_node_summary(node_map[node_id]) for node_id in outgoing_ids if node_id in node_map]
    else:
        incoming_nodes = []
        outgoing_nodes = []

    agents = []
    if _user_has_feature(request.user, STUDIO_FEATURE_AGENTS):
        agents = [
            {
                "id": agent.pk,
                "name": agent.name,
                "description": agent.description,
                "mcp_server_ids": list(agent.mcp_servers.values_list("id", flat=True)),
                "skill_slugs": list(agent.skill_slugs or []),
                "server_scope_ids": list(agent.server_scope.values_list("id", flat=True)),
            }
            for agent in _agent_read_queryset_for_user(request.user).order_by("name")
        ]
    mcps = []
    if _user_has_feature(request.user, STUDIO_FEATURE_MCP):
        mcps = [
            {
                "id": mcp.pk,
                "name": mcp.name,
                "description": mcp.description,
                "transport": mcp.transport,
                "last_test_ok": mcp.last_test_ok,
            }
            for mcp in _mcp_read_queryset_for_user(request.user)
        ]

    servers = list_owned_server_payloads(request.user)
    available_skills = []
    if _user_has_feature(request.user, STUDIO_FEATURE_SKILLS):
        all_skills = list_skills()
        access_map = _skill_access_map([skill.slug for skill in all_skills])
        available_skills = [
            _skill_to_summary_dict(skill, request.user, access_map.get(skill.slug.lower()))
            for skill in all_skills
            if _can_read_skill(request.user, access_map.get(skill.slug.lower()))
        ]

    selected_data = current_node.get("data") if current_node and isinstance(current_node.get("data"), dict) else {}
    selected_skill_slugs = normalise_skill_slugs(selected_data.get("skill_slugs"))
    selected_skill_details = []
    for slug in selected_skill_slugs:
        try:
            skill = get_skill(slug)
        except SkillNotFoundError:
            continue
        selected_skill_details.append(
            {
                "slug": skill.slug,
                "name": skill.name,
                "guardrail_summary": list(skill.guardrail_summary),
                "runtime_policy": skill.runtime_policy,
                "content": skill.content[:5000],
            }
        )

    selected_mcp_tools = []
    selected_mcp_id_raw = selected_data.get("mcp_server_id")
    try:
        selected_mcp_id = int(selected_mcp_id_raw) if selected_mcp_id_raw not in (None, "") else None
    except (TypeError, ValueError):
        selected_mcp_id = None

    if selected_mcp_id:
        try:
            selected_mcp = _mcp_read_queryset_for_user(request.user).get(pk=selected_mcp_id)
            inspection = asyncio.run(_inspect_mcp_server(selected_mcp))
            selected_mcp_tools = [
                {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema") or {},
                }
                for tool in inspection.get("tools", [])[:30]
                if isinstance(tool, dict)
            ]
        except Exception:
            selected_mcp_tools = []

    graph_node_summaries = [compact_node_summary(item) for item in node_map.values()]
    graph_overview = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "trigger_nodes": [item for item in graph_node_summaries if str(item.get("type") or "").startswith("trigger/")],
        "agent_nodes": [item for item in graph_node_summaries if str(item.get("type") or "").startswith("agent/")],
        "logic_nodes": [item for item in graph_node_summaries if str(item.get("type") or "").startswith("logic/")],
        "output_nodes": [item for item in graph_node_summaries if str(item.get("type") or "").startswith("output/")],
    }

    assistant_context = get_pipeline_assistant_context(
        pipeline_name=pipeline_name,
        graph_overview=graph_overview,
        focus_node=compact_selected_node(current_node) if current_node else None,
        incoming_nodes=incoming_nodes,
        outgoing_nodes=outgoing_nodes,
        graph_nodes=graph_node_summaries,
        available_agents=agents,
        available_servers=servers,
        available_mcp_servers=mcps,
        selected_mcp_tools=selected_mcp_tools,
        available_skills=available_skills,
        selected_skill_details=selected_skill_details,
        intent=intent,
        last_validation_errors=last_validation_errors,
        last_run_summary=last_run_summary,
        draft_mode=draft_mode,
    )
    try:
        response = build_pipeline_assistant_response(
            user_message=user_message,
            conversation_history=conversation_history,
            assistant_context=assistant_context,
            known_node_ids=set(node_map.keys()),
            known_node_types={
                node_id: str(node.get("type") or "")
                for node_id, node in node_map.items()
                if isinstance(node, dict)
            },
            known_edges=[edge for edge in edges if isinstance(edge, dict)],
        )
    except PipelineAssistantError as exc:
        return _err(exc.message, exc.status)
    preview_nodes, preview_edges = apply_pipeline_assistant_patch(nodes, edges, response)
    validation_errors = validate_pipeline_definition(
        nodes=preview_nodes,
        edges=preview_edges,
        owner=assistant_pipeline.owner if assistant_pipeline is not None else request.user,
        graph_version=CURRENT_PIPELINE_GRAPH_VERSION,
    )
    response["patch_summary"] = response.get("patch_summary") or assistant_patch_summary(response)
    response["validation"] = {
        "ok": not validation_errors,
        "errors": validation_errors,
        "warnings": [],
    }
    response["risk"] = pipeline_assistant_risk(preview_nodes)
    if not response.get("suggested_next_actions"):
        response["suggested_next_actions"] = (
            ["Fix validation errors before applying the proposal"]
            if validation_errors
            else ["Review the diff", "Apply the draft", "Save the pipeline", "Run a manual test"]
        )
    return _ok(response)
