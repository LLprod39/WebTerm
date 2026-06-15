from __future__ import annotations

from io import StringIO

from django.core.management import call_command

from studio.executor.registry import registry
from studio.management.commands.check_node_manifest_consistency import collect_node_manifest_consistency_errors
from studio.node_manifest import KNOWN_NODE_TYPES, NODE_MANIFESTS, TRIGGER_NODE_TYPES, node_manifest_payload


def test_node_manifest_consistency_sources_match():
    assert collect_node_manifest_consistency_errors() == []


def test_executor_registry_covers_every_non_trigger_node():
    assert set(registry.list_types()) == set(KNOWN_NODE_TYPES) - set(TRIGGER_NODE_TYPES)


def test_every_node_manifest_exposes_input_and_output_schemas():
    payload = node_manifest_payload()

    assert {item["type"] for item in payload} == set(KNOWN_NODE_TYPES)
    for node_type, manifest in NODE_MANIFESTS.items():
        assert manifest.input_schema["type"] == "object", node_type
        assert manifest.output_schema["type"] == "object", node_type
        assert isinstance(manifest.input_schema.get("properties"), dict), node_type
        assert isinstance(manifest.output_schema.get("properties"), dict), node_type


def test_check_node_manifest_consistency_command_reports_success():
    out = StringIO()

    call_command("check_node_manifest_consistency", stdout=out)

    assert "Node manifest consistency OK" in out.getvalue()
