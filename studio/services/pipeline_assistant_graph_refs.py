from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from studio.node_manifest import KNOWN_NODE_TYPES
from studio.services.pipeline_assistant_catalog import (
    EDGE_PLACEHOLDER_TYPES,
    HANDLE_ALIASES,
    NODE_TYPE_ALIASES,
    NODE_TYPE_CATALOG,
)


def _warn(warnings: list[str] | None, message: str) -> None:
    if warnings is not None and message not in warnings:
        warnings.append(message)


def _humanize_ref(ref: str) -> str:
    return re.sub(r"[_\-]+", " ", str(ref or "").strip()).strip().title() or "AI Node"


def _canonical_node_type(raw_type: Any, *, ref: str, warnings: list[str] | None) -> str | None:
    node_type = str(raw_type or "").strip()
    lowered = node_type.lower()
    if lowered in KNOWN_NODE_TYPES:
        return lowered
    if lowered in NODE_TYPE_ALIASES:
        canonical = NODE_TYPE_ALIASES[lowered]
        _warn(warnings, f"AI node '{ref}' used type '{node_type}', normalized to '{canonical}'.")
        return canonical
    if lowered in EDGE_PLACEHOLDER_TYPES:
        _warn(warnings, f"AI node '{ref}' described an edge placeholder; it was converted to an edge or dropped.")
        return None
    _warn(warnings, f"AI node '{ref}' used unknown type '{node_type}' and was dropped.")
    return None


def _infer_structural_node_type(ref: str) -> str | None:
    value = str(ref or "").lower()
    if "parallel" in value or "fanout" in value or "fan_out" in value:
        return "logic/parallel"
    if "merge" in value or "join" in value:
        return "logic/merge"
    if "approval" in value or "approve" in value:
        return "logic/human_approval"
    if "telegram_input" in value or "operator_reply" in value:
        return "logic/telegram_input"
    if "wait" in value:
        return "logic/wait"
    return None


def _ref_tokens(ref: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", str(ref or "").lower()) if part and part not in {"node", "step"}}


def _compact_ref(ref: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(ref or "").lower())


def _ref_digits(ref: str) -> set[str]:
    return set(re.findall(r"\d+", str(ref or "")))


def _resolve_graph_ref(raw_ref: str, known_refs: set[str]) -> str | None:
    ref = str(raw_ref or "").strip()
    if not ref:
        return None
    if ref in known_refs:
        return ref
    if not known_refs:
        return None

    ref_compact = _compact_ref(ref)
    compact_matches = [candidate for candidate in known_refs if _compact_ref(candidate) == ref_compact]
    if len(compact_matches) == 1:
        return compact_matches[0]

    tokens = _ref_tokens(ref)
    digits = _ref_digits(ref)
    scored: list[tuple[float, str]] = []
    for candidate in known_refs:
        candidate_tokens = _ref_tokens(candidate)
        candidate_digits = _ref_digits(candidate)
        token_score = len(tokens & candidate_tokens) / max(len(tokens), 1)
        digit_score = 0.25 if digits and digits <= candidate_digits else 0.0
        substring_score = 0.2 if ref_compact and ref_compact in _compact_ref(candidate) else 0.0
        similarity = SequenceMatcher(None, ref_compact, _compact_ref(candidate)).ratio()
        score = max(similarity, token_score + digit_score + substring_score)
        if score >= 0.72:
            scored.append((score, candidate))

    scored.sort(reverse=True)
    if len(scored) == 1:
        return scored[0][1]
    if len(scored) >= 2 and scored[0][0] - scored[1][0] >= 0.12:
        return scored[0][1]
    return None


def _allowed_source_handles(node_type: str) -> set[str]:
    catalog_item = NODE_TYPE_CATALOG.get(node_type)
    if catalog_item:
        return set(catalog_item["source_handles"])
    return {"out"}


def _default_source_handle(node_type: str) -> str:
    if node_type == "logic/condition":
        return "true"
    if node_type == "logic/human_approval":
        return "approved"
    if node_type == "logic/telegram_input":
        return "received"
    if node_type == "logic/wait":
        return "done"
    return "out"


def _normalize_source_handle(
    raw_handle: Any,
    *,
    source: str,
    source_type: str,
    warnings: list[str] | None,
) -> str:
    allowed = _allowed_source_handles(source_type)
    value = str(raw_handle or "").strip()
    if not value:
        return _default_source_handle(source_type)
    if value in allowed:
        return value
    alias = HANDLE_ALIASES.get(value.lower())
    if alias in allowed:
        _warn(warnings, f"AI edge from '{source}' used source_handle '{value}', normalized to '{alias}'.")
        return alias
    fallback = _default_source_handle(source_type)
    _warn(
        warnings,
        (
            f"AI edge from '{source}' used invalid source_handle '{value}' "
            f"for '{source_type or 'unknown'}', normalized to '{fallback}'."
        ),
    )
    return fallback


def _edge_from_placeholder_node(item: dict[str, Any]) -> dict[str, Any] | None:
    data = item.get("data") if isinstance(item.get("data"), dict) else {}
    ref = str(item.get("ref") or item.get("id") or "").strip()
    source = str(item.get("source") or data.get("source") or "").strip()
    target = str(item.get("target") or data.get("target") or "").strip()
    if not source and not target and "_to_" in ref:
        source, target = [part.strip() for part in ref.split("_to_", 1)]
    if not source or not target:
        return None
    return {
        "source": source,
        "target": target,
        "label": str(item.get("label") or data.get("label") or "").strip() or None,
        "source_handle": str(item.get("source_handle") or data.get("source_handle") or "").strip() or None,
        "target_handle": str(item.get("target_handle") or data.get("target_handle") or "").strip() or None,
    }


def _edge_path_exists(edges: list[dict[str, Any]], *, start: str, goal: str) -> bool:
    if not start or not goal:
        return False
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        if source and target:
            adjacency.setdefault(source, []).append(target)

    stack = [start]
    visited: set[str] = set()
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node in visited:
            continue
        visited.add(node)
        stack.extend(adjacency.get(node, []))
    return False
