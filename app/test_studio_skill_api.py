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
    assert any(item["slug"] == "gitlab-ops" for item in payload)
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


@pytest.mark.django_db
def test_skill_detail_update_rewrites_skill_metadata(settings):
    temp_root = _make_workspace_temp_dir(settings, "skill_update")
    try:
        settings.STUDIO_SKILLS_DIRS = [temp_root / "skills"]
        user = User.objects.create_user(username="skill-update-admin", password="x", is_staff=True)
        client = Client()
        client.force_login(user)

        create_response = client.post(
            "/api/studio/skills/scaffold/",
            data=json.dumps(
                {
                    "name": "Docker Ops",
                    "description": "Safe Docker operational workflow with discovery and verification.",
                    "with_references": True,
                }
            ),
            content_type="application/json",
        )
        assert create_response.status_code == 201
        slug = create_response.json()["skill"]["slug"]

        update_response = client.put(
            f"/api/studio/skills/{slug}/",
            data=json.dumps(
                {
                    "name": "Docker Recovery Ops",
                    "description": "Updated safe Docker recovery workflow with discovery and verification.",
                    "service": "docker",
                    "category": "server_ops",
                    "safety_level": "high",
                    "ui_hint": "Use for Docker incident recovery.",
                    "tags": ["docker", "recovery"],
                    "guardrail_summary": ["Resolve exact container first"],
                    "recommended_tools": ["read_console", "ssh_execute", "report"],
                    "runtime_policy": {"pinned_arguments": {"profile": "prod"}},
                }
            ),
            content_type="application/json",
        )

        assert update_response.status_code == 200
        payload = update_response.json()
        assert payload["name"] == "Docker Recovery Ops"
        assert payload["service"] == "docker"
        assert payload["tags"] == ["docker", "recovery"]
        assert payload["runtime_policy"]["pinned_arguments"]["profile"] == "prod"

        skill_text = (temp_root / "skills" / slug / "SKILL.md").read_text(encoding="utf-8")
        assert "name: Docker Recovery Ops" in skill_text
        assert "service: docker" in skill_text
        assert 'runtime_policy: {"pinned_arguments":{"profile":"prod"}}' in skill_text
        assert "## Mandatory workflow" in skill_text
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
