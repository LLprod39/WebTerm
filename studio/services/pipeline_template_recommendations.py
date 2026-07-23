from __future__ import annotations

import re
from typing import Any

from studio.pilot_capability_packs import enrich_mcp_node_data_with_pilot_spec
from studio.services.pipeline_template_argument_bindings import _extract_template_argument_bindings
from studio.services.pipeline_template_placeholders import (
    _replace_bound_placeholders,
    _unresolved_operational_placeholders,
)
from studio.services.pipeline_template_recommendation_data import (
    PILOT_TEMPLATE_KEYWORDS,
    PILOT_TEMPLATE_SLUGS,
)
from studio.services.pipeline_template_text import _contains_term, _normalise_query, _text
from studio.templates_data import PIPELINE_TEMPLATES


def _pilot_templates() -> list[dict[str, Any]]:
    return [template for template in PIPELINE_TEMPLATES if template.get("slug") in PILOT_TEMPLATE_SLUGS]


def _template_label(node: dict[str, Any]) -> str:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    return _text(data.get("label") or node.get("label") or node.get("id"))


def _compact_template_node(node: dict[str, Any]) -> dict[str, Any]:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    payload: dict[str, Any] = {
        "id": _text(node.get("id")),
        "type": _text(node.get("type")),
        "label": _template_label(node),
    }
    for field in (
        "mcp_server_name",
        "tool_name",
        "permission_mode",
        "capability_pack",
        "operation_kind",
        "risk_level",
        "action",
        "packages",
        "service",
        "sections",
        "expected_status",
        "manual_link_only",
    ):
        value = data.get(field)
        if value not in (None, "", []):
            payload[field] = value
    return payload


def _compact_template_edge(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": _text(edge.get("source")),
        "target": _text(edge.get("target")),
        "source_handle": _text(edge.get("source_handle") or edge.get("sourceHandle") or "out"),
        "label": _text(edge.get("label")) or None,
    }


def _score_template(template: dict[str, Any], query: str) -> tuple[int, list[str]]:
    slug = _text(template.get("slug"))
    matched: list[str] = []
    score = 0
    for term in PILOT_TEMPLATE_KEYWORDS.get(slug, ()):
        if not _contains_term(query, term):
            continue
        matched.append(term)
        score += 3 if " " in term or "/" in term else 1
    if slug and _contains_term(query, slug):
        score += 5
        matched.append(slug)
    return score, list(dict.fromkeys(matched))


def recommend_pilot_pipeline_templates(
    *,
    user_message: str,
    pipeline_name: str = "",
    limit: int = 3,
) -> list[dict[str, Any]]:
    query = _normalise_query(f"{pipeline_name} {user_message}")
    recommendations: list[dict[str, Any]] = []
    for template in _pilot_templates():
        score, matched_terms = _score_template(template, query)
        if score <= 0:
            continue
        nodes = [node for node in template.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in template.get("edges", []) if isinstance(edge, dict)]
        recommendations.append(
            {
                "slug": _text(template.get("slug")),
                "name": _text(template.get("name")),
                "description": _text(template.get("description")),
                "category": _text(template.get("category")),
                "tags": [str(tag) for tag in (template.get("tags") or []) if str(tag).strip()],
                "match_score": score,
                "matched_terms": matched_terms[:8],
                "node_types": list(dict.fromkeys(_text(node.get("type")) for node in nodes if _text(node.get("type")))),
                "skeleton": {
                    "nodes": [_compact_template_node(node) for node in nodes],
                    "edges": [_compact_template_edge(edge) for edge in edges],
                },
            }
        )
    recommendations.sort(key=lambda item: (-int(item["match_score"]), item["slug"]))
    return recommendations[: max(0, limit)]


def get_pilot_pipeline_template(slug: str) -> dict[str, Any] | None:
    normalized = _text(slug)
    for template in _pilot_templates():
        if template.get("slug") == normalized:
            return template
    return None


def _safe_ref(raw_value: str, *, fallback: str, used_refs: set[str]) -> str:
    ref = re.sub(r"[^a-zA-Z0-9_]+", "_", _text(raw_value).lower()).strip("_") or fallback
    if not re.match(r"^[a-zA-Z_]", ref):
        ref = f"{fallback}_{ref}"
    ref = ref[:48].strip("_") or fallback
    candidate = ref
    counter = 2
    while candidate in used_refs:
        candidate = f"{ref}_{counter}"
        counter += 1
    used_refs.add(candidate)
    return candidate


def _match_context_mcp(expected_name: str, assistant_context: dict[str, Any]) -> dict[str, Any] | None:
    expected = _normalise_query(expected_name)
    if not expected:
        return None
    expected_tokens = [token for token in re.split(r"[^a-z0-9]+", expected) if token and token != "mcp"]
    candidates = assistant_context.get("available_mcp_servers")
    if not isinstance(candidates, list):
        return None
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        haystack = _normalise_query(
            " ".join(_text(item.get(field)) for field in ("name", "description", "transport", "url"))
        )
        score = sum(1 for token in expected_tokens if _contains_term(haystack, token))
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], _text(pair[1].get("name"))))
    return scored[0][1] if scored else None


def _match_context_server(assistant_context: dict[str, Any]) -> dict[str, Any] | None:
    candidates = assistant_context.get("available_servers")
    if not isinstance(candidates, list):
        return None
    servers = [item for item in candidates if isinstance(item, dict) and item.get("id") is not None]
    if not servers:
        return None

    query = _normalise_query(
        " ".join(_text(assistant_context.get(field)) for field in ("binding_query", "pipeline_name", "user_message"))
    )
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in servers:
        name = _normalise_query(_text(item.get("name")))
        host = _normalise_query(_text(item.get("host")))
        score = 0
        if query and name and _contains_term(query, name):
            score += 6
        if query and host and _contains_term(query, host):
            score += 4
        for token in re.split(r"[^a-z0-9]+", name):
            if len(token) >= 4 and _contains_term(query, token):
                score += 1
        if score:
            scored.append((score, item))

    scored.sort(key=lambda pair: (-pair[0], _text(pair[1].get("name"))))
    if scored:
        return scored[0][1]
    if len(servers) == 1:
        return servers[0]
    return None


def _skill_slug_map(assistant_context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    skills = assistant_context.get("available_skills")
    if not isinstance(skills, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in skills:
        if not isinstance(item, dict):
            continue
        slug = _text(item.get("slug"))
        if slug:
            result[slug.lower()] = item
    return result


def _matching_context_skills(
    *,
    expected_name: str,
    existing_slugs: object,
    assistant_context: dict[str, Any],
) -> list[str]:
    available = _skill_slug_map(assistant_context)
    existing = [slug for slug in existing_slugs or [] if _text(slug)]
    selected = [_text(slug) for slug in existing if _text(slug).lower() in available]

    expected = _normalise_query(expected_name)
    tokens = [token for token in re.split(r"[^a-z0-9]+", expected) if len(token) >= 4 and token != "mcp"]
    if not tokens:
        return selected

    for item in available.values():
        slug = _text(item.get("slug"))
        if not slug or slug in selected:
            continue
        haystack = _normalise_query(
            " ".join(_text(item.get(field)) for field in ("slug", "name", "service", "category"))
        )
        if any(_contains_term(haystack, token) for token in tokens):
            selected.append(slug)
        if len(selected) >= 4:
            break
    return selected


def _bind_template_node_data(
    data: dict[str, Any],
    assistant_context: dict[str, Any],
    *,
    argument_bindings: dict[str, str],
) -> dict[str, Any]:
    next_data = enrich_mcp_node_data_with_pilot_spec(data)
    expected_mcp = _text(next_data.get("mcp_server_name"))
    if _text(next_data.get("mcp_server_id")) == "" and expected_mcp:
        matched_mcp = _match_context_mcp(expected_mcp, assistant_context)
        if matched_mcp and matched_mcp.get("id") is not None:
            next_data["mcp_server_id"] = matched_mcp.get("id")

    if "server_id" in next_data and _text(next_data.get("server_id")) == "":
        matched_server = _match_context_server(assistant_context)
        if matched_server and matched_server.get("id") is not None:
            next_data["server_id"] = matched_server.get("id")

    bound_skills = _matching_context_skills(
        expected_name=expected_mcp,
        existing_slugs=next_data.get("skill_slugs"),
        assistant_context=assistant_context,
    )
    if bound_skills or "skill_slugs" in next_data:
        next_data["skill_slugs"] = bound_skills
    if argument_bindings:
        next_data = _replace_bound_placeholders(next_data, argument_bindings)
    return next_data


def build_template_graph_patch(
    template: dict[str, Any],
    *,
    assistant_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = assistant_context or {}
    argument_bindings = _extract_template_argument_bindings(_text(template.get("slug")), context)
    used_refs: set[str] = set()
    id_to_ref: dict[str, str] = {}
    graph_nodes: list[dict[str, Any]] = []

    for index, node in enumerate(template.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        node_id = _text(node.get("id")) or f"node_{index + 1}"
        ref = _safe_ref(node_id, fallback=f"node_{index + 1}", used_refs=used_refs)
        id_to_ref[node_id] = ref
        data = _bind_template_node_data(
            node.get("data") if isinstance(node.get("data"), dict) else {},
            context,
            argument_bindings=argument_bindings,
        )
        position = node.get("position") if isinstance(node.get("position"), dict) else {}
        graph_nodes.append(
            {
                "ref": ref,
                "type": _text(node.get("type")),
                "label": _template_label(node),
                "data": data,
                "x_offset": position.get("x") if isinstance(position.get("x"), (int, float)) else None,
                "y_offset": position.get("y") if isinstance(position.get("y"), (int, float)) else None,
            }
        )

    graph_edges: list[dict[str, Any]] = []
    for edge in template.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source = id_to_ref.get(_text(edge.get("source")), _text(edge.get("source")))
        target = id_to_ref.get(_text(edge.get("target")), _text(edge.get("target")))
        if not source or not target:
            continue
        graph_edges.append(
            {
                "source": source,
                "target": target,
                "source_handle": _text(edge.get("source_handle") or edge.get("sourceHandle") or "out"),
                "target_handle": _text(edge.get("target_handle") or edge.get("targetHandle")) or None,
                "label": _text(edge.get("label")) or None,
            }
        )

    return {
        "anchor_node_id": None,
        "nodes": graph_nodes,
        "edges": graph_edges,
        "update_nodes": [],
        "remove_node_ids": [],
        "remove_edge_ids": [],
    }


def build_template_resource_plan(
    template: dict[str, Any],
    *,
    assistant_context: dict[str, Any],
) -> dict[str, Any]:
    selected_mcp: list[dict[str, Any]] = []
    selected_servers: list[dict[str, Any]] = []
    selected_skills: list[dict[str, Any]] = []
    missing: list[str] = []
    notes: list[str] = []
    available_skills = _skill_slug_map(assistant_context)
    argument_bindings = _extract_template_argument_bindings(_text(template.get("slug")), assistant_context)
    if argument_bindings:
        notes.append("Bound prompt arguments: " + ", ".join(sorted(argument_bindings)))
    expected_mcp_names = list(
        dict.fromkeys(
            _text((node.get("data") or {}).get("mcp_server_name"))
            for node in template.get("nodes", [])
            if isinstance(node, dict)
            and isinstance(node.get("data"), dict)
            and _text(node["data"].get("mcp_server_name"))
        )
    )
    for expected_name in expected_mcp_names:
        matched = _match_context_mcp(expected_name, assistant_context)
        if matched:
            selected_mcp.append(matched)
            notes.append(f"Matched {expected_name} to MCP server #{matched.get('id')}.")
        else:
            missing.append(expected_name)

    needs_server = any(
        isinstance(node, dict) and isinstance(node.get("data"), dict) and "server_id" in node["data"]
        for node in template.get("nodes", [])
    )
    if needs_server:
        matched_server = _match_context_server(assistant_context)
        if matched_server:
            selected_servers.append(matched_server)
            notes.append(f"Matched target server #{matched_server.get('id')}.")
        else:
            missing.append("Target server for OPS nodes")

    for node in template.get("nodes", []):
        if not isinstance(node, dict) or not isinstance(node.get("data"), dict):
            continue
        data = enrich_mcp_node_data_with_pilot_spec(node["data"])
        expected_name = _text(data.get("mcp_server_name"))
        expected_skill_slugs = [_text(slug) for slug in data.get("skill_slugs") or [] if _text(slug)]
        for slug in expected_skill_slugs:
            if available_skills and slug.lower() in available_skills:
                continue
            missing_label = f"Skill: {slug}"
            if missing_label not in missing:
                missing.append(missing_label)
        for slug in _matching_context_skills(
            expected_name=expected_name,
            existing_slugs=data.get("skill_slugs"),
            assistant_context=assistant_context,
        ):
            skill = available_skills.get(slug.lower())
            if skill and skill not in selected_skills:
                selected_skills.append(skill)
            elif not skill and slug not in missing:
                missing.append(f"Skill: {slug}")

    unresolved_inputs, runtime_inputs = _unresolved_operational_placeholders(template, bindings=argument_bindings)
    for placeholder in unresolved_inputs:
        missing.append(f"Argument: {placeholder}")
    if runtime_inputs:
        notes.append("Runtime arguments expected from webhook or previous nodes: " + ", ".join(runtime_inputs) + ".")

    return {
        "servers": selected_servers,
        "agents": [],
        "mcp_servers": selected_mcp,
        "skills": selected_skills,
        "missing": list(dict.fromkeys(missing)),
        "notes": notes or [f"Review resources for template '{template.get('slug')}' before applying."],
    }
