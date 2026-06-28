from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Q

from core_ui.access import feature_allowed_for_user
from plugin_marketplace.services.install_service import enabled_plugin_ids_for_user
from studio.models import MCPServerPool, StudioSkillAccess
from studio.node_manifest import node_manifest_payload
from studio.pilot_capability_packs import list_pilot_capability_packs
from studio.skill_registry import list_skills


@dataclass(frozen=True, slots=True)
class TaskFamily:
    slug: str
    name: str
    description: str
    keywords: tuple[str, ...]
    service_hints: tuple[str, ...]
    preferred_nodes: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    pilot_prompt: str


TASK_FAMILIES: tuple[TaskFamily, ...] = (
    TaskFamily(
        slug="identity_access",
        name="Identity and access administration",
        description="Users, groups, roles, clients and access changes in services like Keycloak.",
        keywords=("keycloak", "iam", "identity", "user", "users", "group", "groups", "role", "roles", "realm", "client"),
        service_hints=("keycloak", "iam", "identity"),
        preferred_nodes=("trigger/manual", "agent/mcp_call", "logic/human_approval", "agent/mcp_call", "output/report"),
        required_capabilities=("mcp", "skill"),
        pilot_prompt="Create a Keycloak workflow: preflight user/group/role lookup, approval, role/group change, verification, report.",
    ),
    TaskFamily(
        slug="runtime_ops",
        name="Runtime operations",
        description="Linux/systemd/Docker package, disk, backup, process, restart, log collection and health verification workflows.",
        keywords=("linux", "systemd", "service", "docker", "container", "process", "logs", "restart", "health", "package", "packages", "apt", "yum", "dnf", "disk", "cleanup", "tmp", "backup", "restore"),
        service_hints=("linux", "docker", "systemd"),
        preferred_nodes=("trigger/manual", "ops/server_snapshot", "logic/human_approval", "ops/service_action", "ops/package_action", "ops/disk_cleanup", "ops/backup_restore_check", "ops/http_check", "output/report"),
        required_capabilities=("server", "node"),
        pilot_prompt="Create a safe Linux runtime workflow: snapshot, package/disk/backup/service action, approval when mutating, verification, report.",
    ),
    TaskFamily(
        slug="kubernetes_ops",
        name="Kubernetes operations",
        description="Kubernetes diagnostics and controlled workload actions through a Kubernetes MCP/skill pack.",
        keywords=("kubernetes", "k8s", "kubectl", "pod", "deployment", "namespace", "ingress", "helm"),
        service_hints=("kubernetes", "k8s", "kubectl", "helm"),
        preferred_nodes=("trigger/manual", "agent/mcp_call", "agent/llm_query", "logic/human_approval", "agent/mcp_call", "output/report"),
        required_capabilities=("mcp", "skill"),
        pilot_prompt="Create a Kubernetes diagnosis workflow: inspect namespace, summarize risk, request approval for a safe action, verify.",
    ),
    TaskFamily(
        slug="database_ops",
        name="Database operations",
        description="Database checks, read-only diagnostics and approved maintenance through DB MCP/skills.",
        keywords=("postgres", "postgresql", "mysql", "database", "db", "sql", "query", "migration", "backup"),
        service_hints=("postgres", "postgresql", "mysql", "database", "sql"),
        preferred_nodes=("trigger/manual", "agent/mcp_call", "agent/llm_query", "logic/human_approval", "agent/mcp_call", "output/report"),
        required_capabilities=("mcp", "skill"),
        pilot_prompt="Create a database triage workflow: read-only checks, summarize findings, approval before maintenance, verification.",
    ),
    TaskFamily(
        slug="code_delivery",
        name="Code delivery and repository automation",
        description="Repository, CI/CD, pull request and deployment-support workflows through Git providers and skills.",
        keywords=("github", "gitlab", "repo", "repository", "pull request", "merge request", "ci", "cd", "pipeline", "deploy"),
        service_hints=("github", "gitlab", "git", "ci", "deploy"),
        preferred_nodes=("trigger/webhook", "agent/mcp_call", "agent/llm_query", "logic/human_approval", "agent/mcp_call", "output/report"),
        required_capabilities=("mcp", "skill"),
        pilot_prompt="Create a CI/CD support workflow: inspect failed run, summarize cause, propose fix path, report.",
    ),
    TaskFamily(
        slug="incident_response",
        name="Incident response",
        description="Alert-triggered diagnosis, evidence collection, approval, incident/ticket update, verification and stakeholder notification.",
        keywords=("incident", "alert", "monitoring", "prometheus", "grafana", "sentry", "oncall", "outage"),
        service_hints=("monitoring", "observability", "prometheus", "grafana", "loki", "sentry", "pagerduty", "jira", "alert"),
        preferred_nodes=("trigger/monitoring", "agent/mcp_call", "agent/llm_query", "logic/human_approval", "agent/mcp_call", "output/report"),
        required_capabilities=("mcp", "skill"),
        pilot_prompt="Create an incident workflow: start from alert, collect observability evidence, propose action, approval, update incident ticket, verify and report.",
    ),
)


def _search_blob(item: dict[str, Any], fields: tuple[str, ...]) -> str:
    values: list[str] = []
    for field in fields:
        value = item.get(field)
        if isinstance(value, (list, tuple)):
            values.extend(str(part) for part in value)
        elif isinstance(value, dict):
            values.extend(f"{key} {part}" for key, part in value.items())
        elif value not in (None, ""):
            values.append(str(value))
    return " ".join(values).lower()


def _matches_keywords(blob: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in blob for keyword in keywords)


def _is_admin(user) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False))


def _mcp_read_queryset_for_user(user):
    qs = MCPServerPool.objects.select_related("owner").prefetch_related("shared_with")
    if _is_admin(user):
        return qs.order_by("name")
    return qs.filter(Q(owner=user) | Q(is_shared=True) | Q(shared_with=user)).distinct().order_by("name")


def _skill_access_map(slugs: list[str]) -> dict[str, StudioSkillAccess]:
    if not slugs:
        return {}
    rows = (
        StudioSkillAccess.objects.filter(slug__in=slugs)
        .select_related("owner")
        .prefetch_related("shared_with")
    )
    return {row.slug.lower(): row for row in rows}


def _can_read_skill(user, access: StudioSkillAccess | None) -> bool:
    if _is_admin(user):
        return True
    if access is None or not user or not getattr(user, "is_authenticated", False):
        return False
    if access.owner_id == user.id or access.is_shared:
        return True
    return any(shared_user.id == user.id for shared_user in access.shared_with.all())


def _skill_summary(skill) -> dict[str, Any]:
    return skill.to_summary_dict()


def _visible_mcp_payloads(user) -> list[dict[str, Any]]:
    if not feature_allowed_for_user(user, "studio_mcp"):
        return []
    return [
        {
            "id": mcp.pk,
            "name": mcp.name,
            "description": mcp.description,
            "transport": mcp.transport,
            "url": mcp.url,
            "command": mcp.command,
            "args": list(mcp.args or []),
            "last_test_ok": mcp.last_test_ok,
            "owner_id": mcp.owner_id,
        }
        for mcp in _mcp_read_queryset_for_user(user)
    ]


def _visible_skill_payloads(user) -> list[dict[str, Any]]:
    if not feature_allowed_for_user(user, "studio_skills"):
        return []
    skills = list_skills()
    access_map = _skill_access_map([skill.slug for skill in skills])
    return [
        _skill_summary(skill)
        for skill in skills
        if _can_read_skill(user, access_map.get(skill.slug.lower()))
    ]


def _family_readiness(
    family: TaskFamily,
    *,
    mcp_matches: list[dict[str, Any]],
    skill_matches: list[dict[str, Any]],
    server_count: int | None,
) -> str:
    missing = set()
    if "mcp" in family.required_capabilities and not mcp_matches:
        missing.add("mcp")
    if "skill" in family.required_capabilities and not skill_matches:
        missing.add("skill")
    if "server" in family.required_capabilities and not server_count:
        missing.add("server")
    if not missing:
        return "ready"
    if len(missing) < len(family.required_capabilities):
        return "partial"
    return "missing"


def build_studio_capability_registry(user, *, server_count: int | None = None) -> dict[str, Any]:
    mcp_servers = _visible_mcp_payloads(user)
    skills = _visible_skill_payloads(user)
    node_manifests = node_manifest_payload(enabled_plugin_ids_for_user(user))
    capability_packs = list_pilot_capability_packs()
    mcp_blobs = [
        (mcp, _search_blob(mcp, ("name", "description", "transport", "url", "command", "args")))
        for mcp in mcp_servers
    ]
    skill_blobs = [
        (
            skill,
            _search_blob(
                skill,
                ("slug", "name", "description", "service", "category", "tags", "recommended_tools", "guardrail_summary"),
            ),
        )
        for skill in skills
    ]

    task_families: list[dict[str, Any]] = []
    for family in TASK_FAMILIES:
        mcp_matches = [mcp for mcp, blob in mcp_blobs if _matches_keywords(blob, family.keywords + family.service_hints)]
        skill_matches = [skill for skill, blob in skill_blobs if _matches_keywords(blob, family.keywords + family.service_hints)]
        readiness = _family_readiness(
            family,
            mcp_matches=mcp_matches,
            skill_matches=skill_matches,
            server_count=server_count,
        )
        missing = [
            capability
            for capability in family.required_capabilities
            if (capability == "mcp" and not mcp_matches)
            or (capability == "skill" and not skill_matches)
            or (capability == "server" and not server_count)
        ]
        task_families.append(
            {
                "slug": family.slug,
                "name": family.name,
                "description": family.description,
                "readiness": readiness,
                "missing": missing,
                "preferred_nodes": list(family.preferred_nodes),
                "required_capabilities": list(family.required_capabilities),
                "matching_mcp_servers": [
                    {
                        "id": mcp["id"],
                        "name": mcp["name"],
                        "transport": mcp["transport"],
                        "last_test_ok": mcp["last_test_ok"],
                    }
                    for mcp in mcp_matches[:6]
                ],
                "matching_skills": [
                    {
                        "slug": skill["slug"],
                        "name": skill["name"],
                        "service": skill.get("service", ""),
                        "safety_level": skill.get("safety_level", ""),
                    }
                    for skill in skill_matches[:6]
                ],
                "pilot_prompt": family.pilot_prompt,
                "capability_packs": [
                    {
                        "slug": pack["slug"],
                        "name": pack["name"],
                        "service": pack["service"],
                        "mcp_server_name": pack["mcp_server_name"],
                        "tool_names": [tool["tool_name"] for tool in pack["tools"]],
                        "skill_slugs": pack["skill_slugs"],
                    }
                    for pack in capability_packs
                    if pack["task_family"] == family.slug
                ],
            }
        )

    return {
        "strategy": {
            "mode": "minimal_universal_nodes",
            "service_specific_work": "mcp_plus_skills",
            "default_execution_node": "agent/mcp_call",
            "approval_node": "logic/human_approval",
            "verification_nodes": ["ops/http_check", "output/report", "agent/mcp_call"],
        },
        "nodes": node_manifests,
        "resources": {
            "mcp_servers": [
                {
                    "id": mcp["id"],
                    "name": mcp["name"],
                    "description": mcp["description"],
                    "transport": mcp["transport"],
                    "last_test_ok": mcp["last_test_ok"],
                }
                for mcp in mcp_servers
            ],
            "skills": [
                {
                    "slug": skill["slug"],
                    "name": skill["name"],
                    "description": skill["description"],
                    "service": skill.get("service", ""),
                    "category": skill.get("category", ""),
                    "safety_level": skill.get("safety_level", ""),
                }
                for skill in skills
            ],
            "server_count": server_count,
        },
        "capability_packs": capability_packs,
        "task_families": task_families,
    }
