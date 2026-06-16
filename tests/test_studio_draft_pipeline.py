from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from core_ui.models import UserAppPermission

pytestmark = pytest.mark.django_db


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


def test_empty_pipeline_draft_trigger_starts_inactive_and_out_of_active_readiness():
    user = User.objects.create_user(username="draft-inactive-user", password="x")
    _grant_feature(user, "studio", "studio_pipelines", "studio_runs")
    client = Client()
    client.force_login(user)

    response = client.post(
        "/api/studio/pipelines/",
        data=_json({"name": "Draft Pipeline", "nodes": [], "edges": []}),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["nodes"][0]["id"] == "manual_start"
    assert payload["nodes"][0]["data"]["is_active"] is False
    assert payload["triggers"][0]["is_active"] is False
    assert payload["trigger_summary"]["active_total"] == 0

    readiness = client.get("/api/studio/readiness/?active_only=true")
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "ready"
    assert readiness.json()["summary"]["pipeline_count"] == 0
