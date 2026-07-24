"""Read/inspect Studio assistant actions (pipelines, runs, MCP, skills)."""

from __future__ import annotations

from typing import Any

from app.assistant_actions import AssistantActionContext, AssistantActionError
from studio.assistant_actions_common import _int_payload, _pipeline_for_user
from studio.capability_registry import build_studio_capability_registry
from studio.skill_authoring import validate_skills
from studio.skill_registry import SkillNotFoundError, get_skill, list_skills, normalise_skill_slugs
from studio.views.mcp_views import _mcp_read_queryset_for_user, _mcp_to_dict
from studio.views.pipeline_draft_helpers import draft_queryset_for_user
from studio.views.pipeline_helpers import _pipeline_queryset_for_user
from studio.views.run_views import _run_queryset_for_user
from studio.views.skill_helpers import (
    _can_read_skill,
    _get_skill_access,
    _skill_access_map,
    _skill_to_detail_dict,
    _skill_to_summary_dict,
)


def list_pipelines(ctx: AssistantActionContext) -> dict[str, Any]:
    query = str(ctx.input_payload.get("q") or "").strip()
    qs = _pipeline_queryset_for_user(ctx.user)
    if query:
        qs = qs.filter(name__icontains=query)
    items = [pipeline.to_list_dict() for pipeline in qs[:25]]
    return {"pipelines": items, "count": len(items), "target_url": "/studio"}


def list_runs(ctx: AssistantActionContext) -> dict[str, Any]:
    runs = [_run.to_dict() for _run in _run_queryset_for_user(ctx.user)[:25]]
    return {"runs": runs, "count": len(runs), "target_url": "/studio/runs"}


def capability_registry(ctx: AssistantActionContext) -> dict[str, Any]:
    server_count = ctx.input_payload.get("server_count")
    try:
        parsed_server_count = int(server_count) if server_count not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise AssistantActionError("server_count must be an integer") from exc
    return {
        "capability_registry": build_studio_capability_registry(ctx.user, server_count=parsed_server_count),
        "target_url": "/studio",
    }


def list_mcp_servers(ctx: AssistantActionContext) -> dict[str, Any]:
    query = str(ctx.input_payload.get("q") or "").strip().lower()
    items = []
    for mcp in _mcp_read_queryset_for_user(ctx.user)[:50]:
        payload = _mcp_to_dict(mcp, ctx.user)
        blob = " ".join(
            str(payload.get(key) or "") for key in ("name", "description", "transport", "url", "command")
        ).lower()
        if query and query not in blob:
            continue
        items.append(payload)
    return {"mcp_servers": items[:25], "count": len(items), "target_url": "/studio/mcp"}


def list_studio_skills(ctx: AssistantActionContext) -> dict[str, Any]:
    query = str(ctx.input_payload.get("q") or "").strip().lower()
    skills = list_skills()
    access_map = _skill_access_map([skill.slug for skill in skills])
    items = []
    for skill in skills:
        access = access_map.get(skill.slug.lower())
        if not _can_read_skill(ctx.user, access):
            continue
        payload = _skill_to_summary_dict(skill, ctx.user, access)
        blob = " ".join(
            str(payload.get(key) or "")
            for key in ("slug", "name", "description", "service", "category", "safety_level")
        ).lower()
        if query and query not in blob:
            continue
        items.append(payload)
    return {"skills": items[:50], "count": len(items), "target_url": "/studio/skills"}


def validate_studio_skills(ctx: AssistantActionContext) -> dict[str, Any]:
    raw_slugs = ctx.input_payload.get("slugs")
    if isinstance(raw_slugs, str):
        raw_slugs = [raw_slugs]
    slugs = normalise_skill_slugs(raw_slugs if isinstance(raw_slugs, list) else [])
    strict = bool(ctx.input_payload.get("strict"))
    if slugs:
        access_map = _skill_access_map(slugs)
        denied = [slug for slug in slugs if not _can_read_skill(ctx.user, access_map.get(slug.lower()))]
        if denied:
            raise AssistantActionError(f"Skills not accessible: {', '.join(denied)}", status=403)
        results = validate_skills(slugs)
    else:
        skills = list_skills()
        access_map = _skill_access_map([skill.slug for skill in skills])
        visible_slugs = [
            skill.slug for skill in skills if _can_read_skill(ctx.user, access_map.get(skill.slug.lower()))
        ]
        results = validate_skills(visible_slugs) if visible_slugs else []
    error_count = sum(len(item.errors) for item in results)
    warning_count = sum(len(item.warnings) for item in results)
    return {
        "results": [item.to_dict() for item in results],
        "summary": {
            "skills": len(results),
            "errors": error_count,
            "warnings": warning_count,
            "is_valid": error_count == 0 and (warning_count == 0 if strict else True),
            "strict": strict,
        },
        "target_url": "/studio/skills",
    }


def get_pipeline(ctx: AssistantActionContext) -> dict[str, Any]:
    pipeline = _pipeline_for_user(ctx.user, _int_payload(ctx, "pipeline_id"))
    detail = pipeline.to_detail_dict() if hasattr(pipeline, "to_detail_dict") else pipeline.to_list_dict()
    # Keep graph readable for the model without flooding context
    nodes = list(pipeline.nodes or [])
    edges = list(pipeline.edges or [])
    return {
        "pipeline": detail,
        "graph_summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_types": sorted(
                {
                    str((n or {}).get("type") or (n or {}).get("data", {}).get("type") or "unknown")
                    for n in nodes
                    if isinstance(n, dict)
                }
            )[:30],
            "node_ids": [str((n or {}).get("id") or "") for n in nodes if isinstance(n, dict)][:40],
        },
        "target_url": f"/studio/pipeline/{pipeline.pk}",
    }


def list_pipeline_drafts(ctx: AssistantActionContext) -> dict[str, Any]:
    drafts = list(draft_queryset_for_user(ctx.user)[:25])
    items = [d.to_dict(include_latest=True) for d in drafts]
    return {"drafts": items, "count": len(items), "target_url": "/studio/drafts"}


def get_studio_skill(ctx: AssistantActionContext) -> dict[str, Any]:
    slug = str(ctx.input_payload.get("slug") or "").strip()
    if not slug:
        raise AssistantActionError("slug is required")
    try:
        skill = get_skill(slug)
    except SkillNotFoundError as exc:
        raise AssistantActionError("Skill not found", status=404) from exc
    access = _get_skill_access(skill.slug)
    if not _can_read_skill(ctx.user, access):
        raise AssistantActionError("Skill not found", status=404)
    detail = _skill_to_detail_dict(skill, ctx.user, access)
    # Truncate body for tool context
    content = str(detail.get("content") or skill.content or "")
    if len(content) > 6000:
        detail["content"] = content[:6000] + "\n…[truncated]"
    return {"skill": detail, "target_url": f"/studio/skills/{skill.slug}"}
