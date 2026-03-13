import json
import shutil
import uuid
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.test import Client


def _make_workspace_temp_dir(settings, name: str) -> Path:
    root = Path(settings.BASE_DIR) / ".tmp_skill_api_tests" / f"{name}_{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.mark.django_db
def test_skill_templates_endpoint_returns_built_in_templates():
    user = User.objects.create_user(username="skill-api-user", password="x", is_staff=True)
    client = Client()
    client.force_login(user)

    response = client.get("/api/studio/skills/templates/")

    assert response.status_code == 200
    payload = response.json()
    assert any(item["slug"] == "keycloak-ops" for item in payload)
    assert any(item["slug"] == "postgres-ops" for item in payload)


@pytest.mark.django_db
def test_skill_scaffold_and_validate_endpoints(settings):
    temp_root = _make_workspace_temp_dir(settings, "skill_api")
    try:
        settings.STUDIO_SKILLS_DIRS = [temp_root / "skills"]
        user = User.objects.create_user(username="skill-api-admin", password="x", is_staff=True)
        client = Client()
        client.force_login(user)

        response = client.post(
            "/api/studio/skills/scaffold/",
            data=json.dumps(
                {
                    "template_slug": "gitlab-ops",
                    "name": "GitLab Runner Access Workflow",
                    "description": "Workflow for safe GitLab runner and access administration with discovery and verification.",
                    "guardrail_summary": ["Requires project discovery", "Verifies final access state"],
                    "with_references": True,
                }
            ),
            content_type="application/json",
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["ok"] is True
        assert payload["skill"]["slug"] == "gitlab-runner-access-workflow"
        assert payload["validation"]["errors"] == []
        assert (temp_root / "skills" / "gitlab-runner-access-workflow" / "SKILL.md").exists()

        validate_response = client.post(
            "/api/studio/skills/validate/",
            data=json.dumps({"slugs": ["gitlab-runner-access-workflow"]}),
            content_type="application/json",
        )

        assert validate_response.status_code == 200
        validate_payload = validate_response.json()
        assert validate_payload["summary"]["errors"] == 0
        assert validate_payload["summary"]["is_valid"] is True
        assert validate_payload["results"][0]["slug"] == "gitlab-runner-access-workflow"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
