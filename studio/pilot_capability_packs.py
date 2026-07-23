from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

JsonSchema = dict[str, Any]


@dataclass(frozen=True, slots=True)
class PilotMCPToolSpec:
    pack_slug: str
    pack_name: str
    task_family: str
    service: str
    mcp_server_name: str
    tool_name: str
    description: str
    input_schema: JsonSchema
    permission_mode: str
    risk_level: str
    operation_kind: str
    mutates_state: bool = False
    requires_approval: bool = False
    skill_slugs: tuple[str, ...] = ()
    policy_tags: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "pack_slug": self.pack_slug,
            "pack_name": self.pack_name,
            "task_family": self.task_family,
            "service": self.service,
            "mcp_server_name": self.mcp_server_name,
            "tool_name": self.tool_name,
            "description": self.description,
            "input_schema": copy.deepcopy(self.input_schema),
            "permission_mode": self.permission_mode,
            "risk_level": self.risk_level,
            "operation_kind": self.operation_kind,
            "mutates_state": self.mutates_state,
            "requires_approval": self.requires_approval,
            "skill_slugs": list(self.skill_slugs),
            "policy_tags": list(self.policy_tags),
        }


def _schema(properties: dict[str, Any], *, required: tuple[str, ...] = ()) -> JsonSchema:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(required),
    }


PILOT_MCP_TOOL_SPECS: tuple[PilotMCPToolSpec, ...] = (
    PilotMCPToolSpec(
        pack_slug="kubernetes-operations",
        pack_name="Kubernetes Operations",
        task_family="kubernetes_ops",
        service="kubernetes",
        mcp_server_name="Kubernetes MCP",
        tool_name="kubernetes_describe_workload",
        description="Read workload status, pods, events and recent rollout evidence.",
        input_schema=_schema(
            {
                "cluster": {
                    "type": "string",
                    "description": "Cluster/context name, if the MCP supports multiple clusters.",
                },
                "namespace": {"type": "string", "description": "Kubernetes namespace."},
                "kind": {
                    "type": "string",
                    "enum": ["deployment", "statefulset", "daemonset", "pod"],
                    "description": "Workload kind.",
                },
                "name": {"type": "string", "description": "Workload name."},
            },
            required=("namespace", "kind", "name"),
        ),
        permission_mode="READ_ONLY",
        risk_level="read_only",
        operation_kind="kubernetes.workload.describe",
        skill_slugs=("kubernetes-safety",),
        policy_tags=("kubernetes", "preflight", "diagnostics"),
    ),
    PilotMCPToolSpec(
        pack_slug="kubernetes-operations",
        pack_name="Kubernetes Operations",
        task_family="kubernetes_ops",
        service="kubernetes",
        mcp_server_name="Kubernetes MCP",
        tool_name="kubernetes_rollout_restart",
        description="Run an approved rollout restart against a workload.",
        input_schema=_schema(
            {
                "cluster": {
                    "type": "string",
                    "description": "Cluster/context name, if the MCP supports multiple clusters.",
                },
                "namespace": {"type": "string", "description": "Kubernetes namespace."},
                "kind": {
                    "type": "string",
                    "enum": ["deployment", "statefulset", "daemonset"],
                    "description": "Restartable workload kind.",
                },
                "name": {"type": "string", "description": "Workload name."},
            },
            required=("namespace", "kind", "name"),
        ),
        permission_mode="ASSISTED",
        risk_level="high",
        operation_kind="kubernetes.rollout_restart",
        mutates_state=True,
        requires_approval=True,
        skill_slugs=("kubernetes-safety",),
        policy_tags=("kubernetes", "mutation", "approval-required", "rollout"),
    ),
    PilotMCPToolSpec(
        pack_slug="kubernetes-operations",
        pack_name="Kubernetes Operations",
        task_family="kubernetes_ops",
        service="kubernetes",
        mcp_server_name="Kubernetes MCP",
        tool_name="kubernetes_rollout_status",
        description="Verify rollout completion and final workload health.",
        input_schema=_schema(
            {
                "cluster": {
                    "type": "string",
                    "description": "Cluster/context name, if the MCP supports multiple clusters.",
                },
                "namespace": {"type": "string", "description": "Kubernetes namespace."},
                "kind": {
                    "type": "string",
                    "enum": ["deployment", "statefulset", "daemonset"],
                    "description": "Workload kind.",
                },
                "name": {"type": "string", "description": "Workload name."},
                "timeout_seconds": {"type": "integer", "description": "Maximum time to wait for a healthy rollout."},
            },
            required=("namespace", "kind", "name"),
        ),
        permission_mode="READ_ONLY",
        risk_level="read_only",
        operation_kind="kubernetes.rollout_status",
        skill_slugs=("kubernetes-safety",),
        policy_tags=("kubernetes", "verification"),
    ),
    PilotMCPToolSpec(
        pack_slug="gitlab-ci-support",
        pack_name="GitLab CI Support",
        task_family="code_delivery",
        service="gitlab",
        mcp_server_name="GitLab MCP",
        tool_name="gitlab_get_pipeline_failure",
        description="Read failed GitLab pipeline/job evidence without changing the repository.",
        input_schema=_schema(
            {
                "project_id": {"type": "string", "description": "GitLab project id or full path."},
                "pipeline_id": {"type": "string", "description": "Failed pipeline id."},
                "commit_sha": {"type": "string", "description": "Commit SHA associated with the pipeline."},
            },
            required=("project_id", "pipeline_id"),
        ),
        permission_mode="READ_ONLY",
        risk_level="read_only",
        operation_kind="gitlab.pipeline.failure.read",
        skill_slugs=("gitlab-ci-safety",),
        policy_tags=("gitlab", "ci", "preflight"),
    ),
    PilotMCPToolSpec(
        pack_slug="gitlab-ci-support",
        pack_name="GitLab CI Support",
        task_family="code_delivery",
        service="gitlab",
        mcp_server_name="GitLab MCP",
        tool_name="gitlab_create_fix_merge_request",
        description="Create a fix branch and merge request after human approval; never push directly to protected branches.",
        input_schema=_schema(
            {
                "project_id": {"type": "string", "description": "GitLab project id or full path."},
                "source_branch": {"type": "string", "description": "Temporary source branch for the proposed fix."},
                "target_branch": {"type": "string", "description": "Target branch for the MR."},
                "commit_sha": {"type": "string", "description": "Source commit SHA used as evidence."},
                "proposal": {"type": "string", "description": "Approved fix proposal from the analysis step."},
            },
            required=("project_id", "source_branch", "target_branch", "proposal"),
        ),
        permission_mode="ASSISTED",
        risk_level="medium",
        operation_kind="gitlab.merge_request.create",
        mutates_state=True,
        requires_approval=True,
        skill_slugs=("gitlab-ci-safety",),
        policy_tags=("gitlab", "mutation", "approval-required", "pr-first"),
    ),
    PilotMCPToolSpec(
        pack_slug="gitlab-ci-support",
        pack_name="GitLab CI Support",
        task_family="code_delivery",
        service="gitlab",
        mcp_server_name="GitLab MCP",
        tool_name="gitlab_get_merge_request_pipeline",
        description="Read the pipeline status for the created merge request.",
        input_schema=_schema(
            {
                "project_id": {"type": "string", "description": "GitLab project id or full path."},
                "merge_request": {"type": "string", "description": "MR id, iid, url or MCP result reference."},
            },
            required=("project_id", "merge_request"),
        ),
        permission_mode="READ_ONLY",
        risk_level="read_only",
        operation_kind="gitlab.merge_request.pipeline.read",
        skill_slugs=("gitlab-ci-safety",),
        policy_tags=("gitlab", "ci", "verification"),
    ),
    PilotMCPToolSpec(
        pack_slug="database-maintenance",
        pack_name="Database Maintenance",
        task_family="database_ops",
        service="database",
        mcp_server_name="Database MCP",
        tool_name="database_readonly_diagnostics",
        description="Run read-only database diagnostics for locks, slow queries, replication and capacity.",
        input_schema=_schema(
            {
                "database": {"type": "string", "description": "Database name or connection alias."},
                "schema": {"type": "string", "description": "Optional schema name."},
                "checks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Diagnostic checks to run.",
                },
            },
            required=("database", "checks"),
        ),
        permission_mode="READ_ONLY",
        risk_level="read_only",
        operation_kind="database.diagnostics.read",
        skill_slugs=("database-ops-safety",),
        policy_tags=("database", "diagnostics", "preflight"),
    ),
    PilotMCPToolSpec(
        pack_slug="database-maintenance",
        pack_name="Database Maintenance",
        task_family="database_ops",
        service="database",
        mcp_server_name="Database MCP",
        tool_name="database_apply_guarded_maintenance",
        description="Apply a guarded, approved database maintenance plan.",
        input_schema=_schema(
            {
                "database": {"type": "string", "description": "Database name or connection alias."},
                "plan": {"type": "string", "description": "Maintenance plan from the reviewer step."},
                "approval": {"type": "string", "description": "Human approval evidence from the approval node."},
            },
            required=("database", "plan", "approval"),
        ),
        permission_mode="ASSISTED",
        risk_level="high",
        operation_kind="database.maintenance.apply",
        mutates_state=True,
        requires_approval=True,
        skill_slugs=("database-ops-safety",),
        policy_tags=("database", "mutation", "approval-required", "guarded-maintenance"),
    ),
    PilotMCPToolSpec(
        pack_slug="database-maintenance",
        pack_name="Database Maintenance",
        task_family="database_ops",
        service="database",
        mcp_server_name="Database MCP",
        tool_name="database_verify_health",
        description="Verify database health after an approved maintenance action.",
        input_schema=_schema(
            {
                "database": {"type": "string", "description": "Database name or connection alias."},
                "checks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Verification checks to run.",
                },
            },
            required=("database", "checks"),
        ),
        permission_mode="READ_ONLY",
        risk_level="read_only",
        operation_kind="database.health.verify",
        skill_slugs=("database-ops-safety",),
        policy_tags=("database", "verification"),
    ),
    PilotMCPToolSpec(
        pack_slug="observability-incident",
        pack_name="Observability Incident",
        task_family="incident_response",
        service="observability",
        mcp_server_name="Observability MCP",
        tool_name="observability_get_alert_context",
        description="Read alert metadata, labels, current state and linked service context from an observability system.",
        input_schema=_schema(
            {
                "alert_id": {"type": "string", "description": "Alert id, fingerprint or incident source reference."},
                "alert_source": {
                    "type": "string",
                    "description": "Alert source such as Grafana, Prometheus, Sentry or PagerDuty.",
                },
                "service": {"type": "string", "description": "Impacted service or application name."},
                "severity": {
                    "type": "string",
                    "enum": ["critical", "warning", "info", "unknown"],
                    "description": "Alert severity normalized by the MCP or workflow.",
                },
                "time_range_minutes": {"type": "integer", "description": "Evidence window in minutes."},
            },
            required=("alert_id",),
        ),
        permission_mode="READ_ONLY",
        risk_level="read_only",
        operation_kind="observability.alert.context.read",
        skill_slugs=("incident-response-safety",),
        policy_tags=("observability", "incident", "preflight"),
    ),
    PilotMCPToolSpec(
        pack_slug="observability-incident",
        pack_name="Observability Incident",
        task_family="incident_response",
        service="observability",
        mcp_server_name="Observability MCP",
        tool_name="observability_query_metrics_logs",
        description="Query metrics, logs and traces around an alert without changing systems.",
        input_schema=_schema(
            {
                "service": {"type": "string", "description": "Service, workload or application to investigate."},
                "query": {"type": "string", "description": "Metrics/logs query or investigation hint."},
                "time_range_minutes": {"type": "integer", "description": "Evidence window in minutes."},
                "datasource": {
                    "type": "string",
                    "description": "Datasource hint such as Prometheus, Loki, Grafana or Sentry.",
                },
            },
            required=("service", "time_range_minutes"),
        ),
        permission_mode="READ_ONLY",
        risk_level="read_only",
        operation_kind="observability.evidence.query",
        skill_slugs=("incident-response-safety",),
        policy_tags=("observability", "incident", "diagnostics"),
    ),
    PilotMCPToolSpec(
        pack_slug="observability-incident",
        pack_name="Observability Incident",
        task_family="incident_response",
        service="observability",
        mcp_server_name="Observability MCP",
        tool_name="incident_create_or_update_ticket",
        description="Create or update an approved incident ticket/escalation record with evidence and operator approval.",
        input_schema=_schema(
            {
                "summary": {"type": "string", "description": "Incident summary or ticket title/body."},
                "severity": {
                    "type": "string",
                    "enum": ["critical", "warning", "info", "unknown"],
                    "description": "Incident severity.",
                },
                "evidence": {"type": "string", "description": "Evidence collected by read-only observability steps."},
                "approval": {"type": "string", "description": "Human approval evidence from the approval node."},
            },
            required=("summary", "severity", "evidence", "approval"),
        ),
        permission_mode="ASSISTED",
        risk_level="medium",
        operation_kind="incident.ticket.upsert",
        mutates_state=True,
        requires_approval=True,
        skill_slugs=("incident-response-safety",),
        policy_tags=("incident", "mutation", "approval-required", "external-notification"),
    ),
    PilotMCPToolSpec(
        pack_slug="observability-incident",
        pack_name="Observability Incident",
        task_family="incident_response",
        service="observability",
        mcp_server_name="Observability MCP",
        tool_name="incident_verify_acknowledgement",
        description="Verify that the incident ticket or escalation was created, updated or acknowledged.",
        input_schema=_schema(
            {
                "ticket_ref": {
                    "type": "string",
                    "description": "Ticket, incident, escalation or MCP result reference.",
                },
            },
            required=("ticket_ref",),
        ),
        permission_mode="READ_ONLY",
        risk_level="read_only",
        operation_kind="incident.ticket.verify",
        skill_slugs=("incident-response-safety",),
        policy_tags=("incident", "verification"),
    ),
)


_TOOL_BY_NAME = {spec.tool_name: spec for spec in PILOT_MCP_TOOL_SPECS}


def get_pilot_mcp_tool_spec(tool_name: str) -> PilotMCPToolSpec | None:
    return _TOOL_BY_NAME.get(str(tool_name or "").strip())


def list_pilot_capability_packs() -> list[dict[str, Any]]:
    packs: dict[str, dict[str, Any]] = {}
    for spec in PILOT_MCP_TOOL_SPECS:
        pack = packs.setdefault(
            spec.pack_slug,
            {
                "slug": spec.pack_slug,
                "name": spec.pack_name,
                "task_family": spec.task_family,
                "service": spec.service,
                "mcp_server_name": spec.mcp_server_name,
                "skill_slugs": [],
                "tools": [],
            },
        )
        for slug in spec.skill_slugs:
            if slug not in pack["skill_slugs"]:
                pack["skill_slugs"].append(slug)
        pack["tools"].append(spec.to_payload())
    return list(packs.values())


def enrich_mcp_node_data_with_pilot_spec(data: dict[str, Any]) -> dict[str, Any]:
    next_data = copy.deepcopy(data)
    spec = get_pilot_mcp_tool_spec(str(next_data.get("tool_name") or ""))
    if spec is None:
        return next_data

    next_data.setdefault("mcp_server_name", spec.mcp_server_name)
    next_data.setdefault("tool_description", spec.description)
    next_data.setdefault("input_schema", copy.deepcopy(spec.input_schema))
    next_data.setdefault("capability_pack", spec.pack_slug)
    next_data.setdefault("task_family", spec.task_family)
    next_data.setdefault("service", spec.service)
    next_data.setdefault("risk_level", spec.risk_level)
    next_data.setdefault("operation_kind", spec.operation_kind)
    next_data.setdefault("mutates_state", spec.mutates_state)
    next_data.setdefault("requires_approval", spec.requires_approval)
    next_data.setdefault("policy_tags", list(spec.policy_tags))
    if not str(next_data.get("permission_mode") or "").strip():
        next_data["permission_mode"] = spec.permission_mode

    existing_slugs = [str(slug) for slug in next_data.get("skill_slugs") or [] if str(slug).strip()]
    for slug in spec.skill_slugs:
        if slug not in existing_slugs:
            existing_slugs.append(slug)
    if existing_slugs:
        next_data["skill_slugs"] = existing_slugs
    return next_data
