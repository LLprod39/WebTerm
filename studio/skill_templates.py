from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .skill_authoring import build_runtime_policy


@dataclass(frozen=True, slots=True)
class SkillTemplateDefinition:
    slug: str
    name: str
    description: str
    summary: str
    defaults: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "summary": self.summary,
            "defaults": self.defaults,
        }


SKILL_TEMPLATES: tuple[SkillTemplateDefinition, ...] = (
    SkillTemplateDefinition(
        slug="gitlab-ops",
        name="GitLab Operations",
        description="Repository and platform workflow for GitLab MCP with project discovery, branch safety, and post-change verification.",
        summary="Use for project settings, membership, runners, variables, and repository operations.",
        defaults={
            "name": "GitLab Operations Workflow",
            "description": "Safe workflow for GitLab MCP tasks with context discovery, exact project resolution, branch safety, and verification after mutation.",
            "service": "gitlab",
            "category": "Developer Platform",
            "safety_level": "high",
            "ui_hint": "Attach this to GitLab bots so they discover group and project context before mutating settings.",
            "tags": ["gitlab", "scm", "platform", "mcp"],
            "recommended_tools": ["report", "ask_user", "analyze_output"],
            "guardrail_summary": [
                "Requires current context discovery before mutations",
                "Encourages explicit project and namespace resolution",
                "Prompts branch and environment verification",
            ],
            "runtime_policy": build_runtime_policy(
                applicable_tool_patterns=["^gitlab_"],
                mutating_tool_patterns=[
                    "^gitlab_create_",
                    "^gitlab_update_",
                    "^gitlab_delete_",
                    "^gitlab_add_",
                    "^gitlab_assign_",
                ],
                required_preflight_tools=["gitlab_current_context"],
            ),
        },
    ),
    SkillTemplateDefinition(
        slug="jira-ops",
        name="Jira Operations",
        description="Structured workflow for Jira MCP with issue discovery, explicit project scope, and safe workflow transitions.",
        summary="Use for issue updates, assignments, transitions, comments, and project-scoped automation.",
        defaults={
            "name": "Jira Operations Workflow",
            "description": "Safe workflow for Jira MCP tasks with project discovery, exact issue resolution, explicit transition handling, and verification after mutation.",
            "service": "jira",
            "category": "Work Management",
            "safety_level": "medium",
            "ui_hint": "Attach this to Jira bots so they confirm project and issue context before transitions or edits.",
            "tags": ["jira", "tickets", "workflow", "mcp"],
            "recommended_tools": ["report", "ask_user", "analyze_output"],
            "guardrail_summary": [
                "Requires project and issue discovery before updates",
                "Encourages explicit workflow transition checks",
                "Verifies final issue state after mutation",
            ],
            "runtime_policy": build_runtime_policy(
                applicable_tool_patterns=["^jira_"],
                mutating_tool_patterns=[
                    "^jira_create_",
                    "^jira_update_",
                    "^jira_delete_",
                    "^jira_transition_",
                    "^jira_assign_",
                ],
                required_preflight_tools=["jira_current_context"],
            ),
        },
    ),
    SkillTemplateDefinition(
        slug="kubernetes-ops",
        name="Kubernetes Operations",
        description="Cluster workflow for Kubernetes MCP with namespace scoping, workload discovery, and rollout verification.",
        summary="Use for deployments, config changes, restarts, scaling, and cluster diagnostics.",
        defaults={
            "name": "Kubernetes Operations Workflow",
            "description": "Safe workflow for Kubernetes MCP tasks with cluster and namespace discovery, explicit workload targeting, and rollout verification after changes.",
            "service": "kubernetes",
            "category": "Infrastructure",
            "safety_level": "high",
            "ui_hint": "Attach this to Kubernetes bots so they confirm cluster and namespace context before scaling or patching workloads.",
            "tags": ["kubernetes", "cluster", "ops", "mcp"],
            "recommended_tools": ["report", "ask_user", "analyze_output"],
            "guardrail_summary": [
                "Requires cluster and namespace discovery before mutation",
                "Encourages explicit workload targeting",
                "Verifies rollout and pod health after changes",
            ],
            "runtime_policy": build_runtime_policy(
                applicable_tool_patterns=["^kubernetes_"],
                mutating_tool_patterns=[
                    "^kubernetes_apply_",
                    "^kubernetes_patch_",
                    "^kubernetes_scale_",
                    "^kubernetes_delete_",
                    "^kubernetes_rollout_",
                ],
                required_preflight_tools=["kubernetes_current_context"],
            ),
        },
    ),
    SkillTemplateDefinition(
        slug="postgres-ops",
        name="PostgreSQL Operations",
        description="Database workflow for PostgreSQL MCP with database selection, read-first discovery, and careful change verification.",
        summary="Use for schema changes, role grants, maintenance, and operational database automation.",
        defaults={
            "name": "PostgreSQL Operations Workflow",
            "description": "Safe workflow for PostgreSQL MCP tasks with connection discovery, exact database selection, read-first analysis, and verification after any change.",
            "service": "postgres",
            "category": "Data Platform",
            "safety_level": "high",
            "ui_hint": "Attach this to PostgreSQL bots so they confirm database context and inspect objects before mutating schema or roles.",
            "tags": ["postgres", "database", "ops", "mcp"],
            "recommended_tools": ["report", "ask_user", "analyze_output"],
            "guardrail_summary": [
                "Requires current database context before mutation",
                "Encourages read-first inspection of schema and roles",
                "Verifies final schema or permission state after changes",
            ],
            "runtime_policy": build_runtime_policy(
                applicable_tool_patterns=["^postgres_"],
                mutating_tool_patterns=[
                    "^postgres_create_",
                    "^postgres_update_",
                    "^postgres_delete_",
                    "^postgres_grant_",
                    "^postgres_alter_",
                ],
                required_preflight_tools=["postgres_current_context"],
            ),
        },
    ),
)


def list_skill_templates() -> list[SkillTemplateDefinition]:
    return list(SKILL_TEMPLATES)


def get_skill_template(slug: str) -> SkillTemplateDefinition | None:
    needle = str(slug or "").strip().lower()
    if not needle:
        return None
    for item in SKILL_TEMPLATES:
        if item.slug.lower() == needle:
            return item
    return None
