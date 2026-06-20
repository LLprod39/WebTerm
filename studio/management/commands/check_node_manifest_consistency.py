from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from studio.executor import nodes as _registered_executor_nodes  # noqa: F401
from studio.executor.registry import registry
from studio.node_manifest import (
    KNOWN_NODE_TYPES,
    NODE_MANIFESTS,
    TRIGGER_NODE_TYPES,
    allowed_source_handles,
    assistant_node_catalog,
)
from studio.services.pipeline_assistant import NODE_TYPE_ALIASES, NODE_TYPE_CATALOG

NODE_TYPE_REF_RE = re.compile(r'"((?:trigger|agent|ops|logic|output)/[A-Za-z0-9_]+)"')


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _slice_between(content: str, start_marker: str, end_marker: str) -> str:
    start = content.find(start_marker)
    if start == -1:
        return ""
    end = content.find(end_marker, start)
    if end == -1:
        return content[start:]
    return content[start:end]


def _node_type_refs(content: str) -> set[str]:
    return set(NODE_TYPE_REF_RE.findall(content))


def _compare_sets(errors: list[str], *, label: str, actual: set[str], expected: set[str]) -> None:
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{label} missing node types: {missing}")
    if extra:
        errors.append(f"{label} has unknown node types: {extra}")


def collect_node_manifest_consistency_errors(repo_root: Path | None = None) -> list[str]:
    root = Path(repo_root or settings.BASE_DIR)
    expected = set(KNOWN_NODE_TYPES)
    errors: list[str] = []

    _compare_sets(errors, label="NODE_MANIFESTS", actual=set(NODE_MANIFESTS), expected=expected)

    expected_runtime = expected - set(TRIGGER_NODE_TYPES)
    _compare_sets(errors, label="executor registry", actual=set(registry.list_types()), expected=expected_runtime)

    catalog = assistant_node_catalog()
    _compare_sets(errors, label="assistant_node_catalog()", actual=set(catalog), expected=expected)
    _compare_sets(errors, label="pipeline_assistant.NODE_TYPE_CATALOG", actual=set(NODE_TYPE_CATALOG), expected=expected)

    for node_type, manifest in NODE_MANIFESTS.items():
        if not isinstance(manifest.input_schema, dict) or manifest.input_schema.get("type") != "object":
            errors.append(f"{node_type} input_schema must be a JSON object schema")
        if not isinstance(manifest.output_schema, dict) or manifest.output_schema.get("type") != "object":
            errors.append(f"{node_type} output_schema must be a JSON object schema")
        handles = set(allowed_source_handles(node_type))
        expected_handles = set(manifest.source_handles)
        if handles != expected_handles:
            errors.append(f"{node_type} handles mismatch: manifest={sorted(expected_handles)} validation={sorted(handles)}")
        catalog_item = catalog.get(node_type) or {}
        if set(catalog_item.get("source_handles") or []) != expected_handles:
            errors.append(f"{node_type} assistant catalog handles mismatch")

    alias_targets = {target for target in NODE_TYPE_ALIASES.values() if isinstance(target, str)}
    invalid_alias_targets = sorted(alias_targets - expected)
    if invalid_alias_targets:
        errors.append(f"pipeline assistant aliases point to unknown node types: {invalid_alias_targets}")

    frontend_index = _read_text(root / "frontend" / "src" / "components" / "pipeline" / "nodes" / "index.ts")
    node_types_block = _slice_between(frontend_index, "export const NODE_TYPES", "} as const;")
    palette_block = _slice_between(frontend_index, "export const NODE_PALETTE", "];")
    _compare_sets(errors, label="frontend NODE_TYPES", actual=_node_type_refs(node_types_block), expected=expected)
    _compare_sets(errors, label="frontend NODE_PALETTE", actual=_node_type_refs(palette_block), expected=expected)

    node_meta = _read_text(root / "frontend" / "src" / "components" / "pipeline" / "nodes" / "nodeMeta.tsx")
    type_meta_block = _slice_between(node_meta, "export const NODE_TYPE_META", "export const NODE_TYPE_GUIDANCE_META")
    _compare_sets(errors, label="frontend NODE_TYPE_META", actual=_node_type_refs(type_meta_block), expected=expected)

    node_guidance_meta = _read_text(
        root / "frontend" / "src" / "components" / "pipeline" / "nodes" / "nodeGuidanceMeta.ts"
    )
    _compare_sets(errors, label="frontend NODE_TYPE_GUIDANCE_META", actual=_node_type_refs(node_guidance_meta), expected=expected)

    docs = _read_text(root / "docs" / "PIPELINE_NODES_SPEC.md")
    missing_in_docs = sorted(node_type for node_type in expected if f"`{node_type}`" not in docs)
    if missing_in_docs:
        errors.append(f"docs/PIPELINE_NODES_SPEC.md missing node types: {missing_in_docs}")

    return errors


class Command(BaseCommand):
    help = "Verify Studio node manifests match validation, assistant catalog, frontend palette/metadata and docs."

    def handle(self, *args, **options):
        errors = collect_node_manifest_consistency_errors()
        if errors:
            for error in errors:
                self.stderr.write(error)
            raise CommandError(f"Node manifest consistency check failed with {len(errors)} issue(s).")
        self.stdout.write(self.style.SUCCESS(f"Node manifest consistency OK ({len(KNOWN_NODE_TYPES)} node types)."))
