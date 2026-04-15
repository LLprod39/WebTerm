import shutil
import uuid
from io import StringIO
from pathlib import Path

from django.core.management import call_command

from studio.skill_authoring import (
    build_runtime_policy,
    scaffold_skill,
    validate_skill_dir,
)


def _make_workspace_temp_dir(settings, name: str) -> Path:
    root = Path(settings.BASE_DIR) / ".tmp_skill_tests" / f"{name}_{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    return root

def test_scaffold_skill_creates_corporate_template(settings):
    temp_root = _make_workspace_temp_dir(settings, "scaffold")
    try:
        settings.STUDIO_SKILLS_DIRS = [temp_root / "skills"]

        skill_dir = scaffold_skill(
            name="Keycloak Test Workflow",
            description="Safe workflow for Keycloak TEST tasks with preflight and verification.",
            service="keycloak",
            category="Identity and Access",
            safety_level="high",
            ui_hint="Attach this to Keycloak TEST bots.",
            tags=["keycloak", "iam", "test"],
            guardrail_summary=["Requires preflight", "Pins profile=test"],
            recommended_tools=["report", "ask_user", "analyze_output"],
            runtime_policy=build_runtime_policy(
                applicable_tool_patterns=["^keycloak_"],
                mutating_tool_patterns=["^keycloak_create_"],
                required_preflight_tools=["keycloak_current_environment"],
                pinned_arguments={"profile": "test"},
            ),
            with_references=True,
            with_scripts=True,
        )

        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

        assert skill_dir.name == "keycloak-test-workflow"
        assert "## When to use" in text
        assert "## Mandatory workflow" in text
        assert "## Hard rules" in text
        assert "## Reporting" in text
        assert 'runtime_policy: {"applicable_tool_patterns":["^keycloak_"]' in text
        assert (skill_dir / "references").is_dir()
        assert (skill_dir / "scripts").is_dir()

        validation = validate_skill_dir(skill_dir)
        assert validation.errors == []
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_validate_skill_dir_reports_malformed_runtime_policy(settings):
    temp_root = _make_workspace_temp_dir(settings, "invalid")
    try:
        skill_dir = temp_root / "skills" / "BrokenSkill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: Broken Skill
description: short
runtime_policy: not-json
---
# Broken Skill

## When to use

- Example
""",
            encoding="utf-8",
        )

        validation = validate_skill_dir(skill_dir)

        assert any("Directory name must use lowercase letters" in item for item in validation.errors)
        assert any("runtime_policy" in item for item in validation.errors)
        assert any("Description is very short" in item for item in validation.warnings)
        assert any("Recommended section missing: ## Mandatory workflow" in item for item in validation.warnings)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_management_commands_scaffold_and_validate_skill(settings):
    temp_root = _make_workspace_temp_dir(settings, "commands")
    try:
        settings.STUDIO_SKILLS_DIRS = [temp_root / "skills"]

        scaffold_out = StringIO()
        call_command(
            "scaffold_skill",
            "GitLab Ops Workflow",
            description="Workflow for safe GitLab project administration with discovery and verification.",
            service="gitlab",
            category="Developer Platform",
            safety_level="high",
            tags="gitlab, scm, ops",
            recommended_tools="report,ask_user",
            guardrail_summary="Requires discovery before mutations",
            applicable_tool_pattern="^gitlab_",
            mutating_tool_pattern="^gitlab_create_",
            required_preflight_tool="gitlab_current_context",
            stdout=scaffold_out,
        )

        validate_out = StringIO()
        call_command("validate_skills", "gitlab-ops-workflow", stdout=validate_out)

        assert "Created skill scaffold" in scaffold_out.getvalue()
        assert "[OK] gitlab-ops-workflow" in validate_out.getvalue()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
