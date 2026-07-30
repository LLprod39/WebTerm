from __future__ import annotations

import importlib

import pytest
from django.contrib.auth.models import User

from studio.pipeline.pipeline_validation import validate_pipeline_definition
from tests.studio_pipeline_v2_harness import disable_activity_logging, report_node


def test_legacy_pipeline_modules_alias_domain_implementations():
    for module_name in (
        "pipeline_agent_runtime",
        "pipeline_context",
        "pipeline_executor",
        "pipeline_runtime",
        "pipeline_secrets",
        "pipeline_validation",
    ):
        legacy = importlib.import_module(f"studio.{module_name}")
        current = importlib.import_module(f"studio.pipeline.{module_name}")
        assert legacy is current


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    disable_activity_logging(monkeypatch)


@pytest.mark.django_db
def test_validation_allows_merge_with_single_remaining_input():
    user = User.objects.create_user(username="merge-single-user", password="x")

    errors = validate_pipeline_definition(
        nodes=[
            {"id": "webhook", "type": "trigger/webhook", "position": {"x": 0, "y": 0}, "data": {"label": "Webhook"}},
            {"id": "merge", "type": "logic/merge", "position": {"x": 180, "y": 0}, "data": {"mode": "any"}},
            report_node("report"),
        ],
        edges=[
            {"id": "e1", "source": "webhook", "target": "merge", "sourceHandle": "out"},
            {"id": "e2", "source": "merge", "target": "report", "sourceHandle": "out"},
        ],
        owner=user,
        graph_version=2,
    )

    assert errors == []


@pytest.mark.django_db
def test_validation_rejects_invalid_output_webhook_options():
    user = User.objects.create_user(username="webhook-validation-user", password="x")

    errors = validate_pipeline_definition(
        nodes=[
            {"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}},
            {
                "id": "notify",
                "type": "output/webhook",
                "position": {"x": 120, "y": 0},
                "data": {
                    "url": "https://example.test/hook",
                    "timeout_seconds": 0,
                    "headers": ["X-Bad"],
                    "extra_payload": "not-json-object",
                },
            },
        ],
        edges=[{"id": "e1", "source": "manual", "target": "notify", "sourceHandle": "out"}],
        owner=user,
        graph_version=2,
    )

    assert any("field 'timeout_seconds' must be between 1 and 120" in error for error in errors)
    assert any("field 'headers' must be a JSON object" in error for error in errors)
    assert any("field 'extra_payload' must be a JSON object" in error for error in errors)
