"""Pilot pipeline templates for database, incident and package operations."""


PILOT_OPERATIONS_TEMPLATES = [
{
        "slug": "pilot-database-diagnostics-maintenance",
        "name": "Pilot: Database Diagnostics And Maintenance",
        "description": "Read-only DB diagnostics, maintenance risk summary, approval, guarded DB MCP maintenance action and verification.",
        "icon": "DB",
        "category": "Pilot OPS",
        "tags": ["pilot", "database", "mcp", "diagnostics", "approval"],
        "nodes": [
            {"id": "manual", "type": "trigger/manual", "position": {"x": 120, "y": 80}, "data": {"label": "Start DB diagnostics"}},
            {
                "id": "diagnose",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 220},
                "data": {
                    "label": "Run read-only DB diagnostics",
                    "mcp_server_id": "",
                    "mcp_server_name": "Database MCP",
                    "tool_name": "database_readonly_diagnostics",
                    "arguments": {"database": "{database}", "schema": "{schema}", "checks": ["locks", "slow_queries", "replication", "capacity"]},
                    "permission_mode": "READ_ONLY",
                    "on_failure": "abort",
                },
            },
            {
                "id": "plan",
                "type": "agent/llm_query",
                "position": {"x": 120, "y": 370},
                "data": {
                    "label": "Prepare maintenance plan",
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "system_prompt": "You are a database reliability reviewer. Never propose destructive maintenance without explicit break-glass.",
                    "prompt": (
                        "Review DB diagnostics and produce a safe maintenance plan.\n\n"
                        "{diagnose_output}\n\n"
                        "Classify risk, list read-only findings, propose only reversible/guarded actions, and define verification."
                    ),
                    "include_all_outputs": False,
                },
            },
            {
                "id": "approval",
                "type": "logic/human_approval",
                "position": {"x": 120, "y": 520},
                "data": {
                    "label": "Approve DB maintenance",
                    "manual_link_only": True,
                    "timeout_minutes": 120,
                    "message": "Database maintenance requires approval.\n\n{plan_output}\n\nApprove: {approve_url}\nReject: {reject_url}",
                },
            },
            {
                "id": "maintenance",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 690},
                "data": {
                    "label": "Apply guarded maintenance",
                    "mcp_server_id": "",
                    "mcp_server_name": "Database MCP",
                    "tool_name": "database_apply_guarded_maintenance",
                    "arguments": {"database": "{database}", "plan": "{plan_output}", "approval": "{approval_output}"},
                    "permission_mode": "ASSISTED",
                    "on_failure": "abort",
                },
            },
            {
                "id": "verify",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 850},
                "data": {
                    "label": "Verify database health",
                    "mcp_server_id": "",
                    "mcp_server_name": "Database MCP",
                    "tool_name": "database_verify_health",
                    "arguments": {"database": "{database}", "checks": ["locks", "replication", "capacity"]},
                    "permission_mode": "READ_ONLY",
                    "on_failure": "continue",
                },
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 120, "y": 1010},
                "data": {
                    "label": "DB maintenance report",
                    "template": "# Database maintenance report\n\n## Diagnostics\n{diagnose_output}\n\n## Plan\n{plan_output}\n\n## Approval\n{approval_output}\n\n## Maintenance\n{maintenance_output}\n\n## Verification\n{verify_output}",
                },
            },
            {"id": "rejected", "type": "output/report", "position": {"x": 520, "y": 690}, "data": {"label": "DB maintenance rejected", "template": "# Database maintenance rejected\n\n{approval_error}\n\n## Plan\n{plan_output}"}},
            {"id": "timed_out", "type": "output/report", "position": {"x": 520, "y": 850}, "data": {"label": "DB approval timed out", "template": "# Database maintenance timed out\n\nNo approval was received.\n\n## Plan\n{plan_output}"}},
        ],
        "edges": [
            {"id": "e-manual-diagnose", "source": "manual", "target": "diagnose", "sourceHandle": "out", "animated": True},
            {"id": "e-diagnose-plan", "source": "diagnose", "target": "plan", "sourceHandle": "success", "animated": True},
            {"id": "e-plan-approval", "source": "plan", "target": "approval", "sourceHandle": "success", "animated": True},
            {"id": "e-approval-maintenance", "source": "approval", "target": "maintenance", "sourceHandle": "approved", "label": "approved"},
            {"id": "e-approval-rejected", "source": "approval", "target": "rejected", "sourceHandle": "rejected", "label": "rejected"},
            {"id": "e-approval-timeout", "source": "approval", "target": "timed_out", "sourceHandle": "timeout", "label": "timeout"},
            {"id": "e-maintenance-verify", "source": "maintenance", "target": "verify", "sourceHandle": "success", "animated": True},
            {"id": "e-verify-report", "source": "verify", "target": "report", "sourceHandle": "out", "animated": True},
        ],
    },
{
        "slug": "pilot-observability-incident-response",
        "name": "Pilot: Observability Incident Response",
        "description": "Monitoring alert triage, observability evidence collection, risk summary, approval, incident ticket update and acknowledgement verification through MCP.",
        "icon": "IR",
        "category": "Pilot OPS",
        "tags": ["pilot", "observability", "incident", "mcp", "approval"],
        "nodes": [
            {
                "id": "monitoring",
                "type": "trigger/monitoring",
                "position": {"x": 120, "y": 80},
                "data": {
                    "label": "Monitoring alert trigger",
                    "is_active": True,
                    "monitoring_filters": {"severities": ["critical", "warning"], "alert_types": ["service", "slo", "error_rate"]},
                },
            },
            {
                "id": "alert_context",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 220},
                "data": {
                    "label": "Read alert context",
                    "mcp_server_id": "",
                    "mcp_server_name": "Observability MCP",
                    "tool_name": "observability_get_alert_context",
                    "arguments": {
                        "alert_id": "{alert_id}",
                        "alert_source": "{alert_source}",
                        "service": "{service_name}",
                        "severity": "{alert_severity}",
                        "time_range_minutes": 60,
                    },
                    "permission_mode": "READ_ONLY",
                    "on_failure": "abort",
                },
            },
            {
                "id": "evidence",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 370},
                "data": {
                    "label": "Query metrics and logs",
                    "mcp_server_id": "",
                    "mcp_server_name": "Observability MCP",
                    "tool_name": "observability_query_metrics_logs",
                    "arguments": {
                        "service": "{service_name}",
                        "query": "errors OR saturation OR latency OR failed requests",
                        "time_range_minutes": 60,
                    },
                    "permission_mode": "READ_ONLY",
                    "on_failure": "abort",
                },
            },
            {
                "id": "plan",
                "type": "agent/llm_query",
                "position": {"x": 120, "y": 520},
                "data": {
                    "label": "Summarize incident risk",
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "system_prompt": "You are an incident commander. Use evidence first, avoid unapproved remediation and write concise operator-ready summaries.",
                    "prompt": (
                        "Review alert context and observability evidence.\n\n"
                        "Alert context:\n{alert_context_output}\n\n"
                        "Evidence:\n{evidence_output}\n\n"
                        "Return severity, likely cause, blast radius, recommended operator action, escalation/ticket text and verification checklist."
                    ),
                    "include_all_outputs": False,
                },
            },
            {
                "id": "approval",
                "type": "logic/human_approval",
                "position": {"x": 120, "y": 690},
                "data": {
                    "label": "Approve incident update",
                    "manual_link_only": True,
                    "timeout_minutes": 30,
                    "message": "Incident ticket/update requires approval.\n\n{plan_output}\n\nApprove: {approve_url}\nReject: {reject_url}",
                },
            },
            {
                "id": "ticket",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 860},
                "data": {
                    "label": "Create or update incident ticket",
                    "mcp_server_id": "",
                    "mcp_server_name": "Observability MCP",
                    "tool_name": "incident_create_or_update_ticket",
                    "arguments": {
                        "summary": "{plan_output}",
                        "severity": "{alert_severity}",
                        "evidence": "{evidence_output}",
                        "approval": "{approval_output}",
                    },
                    "permission_mode": "ASSISTED",
                    "on_failure": "abort",
                },
            },
            {
                "id": "verify",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 1020},
                "data": {
                    "label": "Verify incident acknowledgement",
                    "mcp_server_id": "",
                    "mcp_server_name": "Observability MCP",
                    "tool_name": "incident_verify_acknowledgement",
                    "arguments": {"ticket_ref": "{ticket_output}"},
                    "permission_mode": "READ_ONLY",
                    "on_failure": "continue",
                },
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 120, "y": 1180},
                "data": {
                    "label": "Incident response report",
                    "template": "# Incident response report\n\n## Alert context\n{alert_context_output}\n\n## Evidence\n{evidence_output}\n\n## Plan\n{plan_output}\n\n## Approval\n{approval_output}\n\n## Ticket/update\n{ticket_output}\n\n## Verification\n{verify_output}",
                },
            },
            {"id": "rejected", "type": "output/report", "position": {"x": 520, "y": 860}, "data": {"label": "Incident update rejected", "template": "# Incident update rejected\n\n{approval_error}\n\n## Proposed plan\n{plan_output}"}},
            {"id": "timed_out", "type": "output/report", "position": {"x": 520, "y": 1020}, "data": {"label": "Incident approval timed out", "template": "# Incident approval timed out\n\nNo approval was received.\n\n## Proposed plan\n{plan_output}"}},
        ],
        "edges": [
            {"id": "e-monitoring-context", "source": "monitoring", "target": "alert_context", "sourceHandle": "out", "animated": True},
            {"id": "e-context-evidence", "source": "alert_context", "target": "evidence", "sourceHandle": "success", "animated": True},
            {"id": "e-evidence-plan", "source": "evidence", "target": "plan", "sourceHandle": "success", "animated": True},
            {"id": "e-plan-approval", "source": "plan", "target": "approval", "sourceHandle": "success", "animated": True},
            {"id": "e-approval-ticket", "source": "approval", "target": "ticket", "sourceHandle": "approved", "label": "approved"},
            {"id": "e-approval-rejected", "source": "approval", "target": "rejected", "sourceHandle": "rejected", "label": "rejected"},
            {"id": "e-approval-timeout", "source": "approval", "target": "timed_out", "sourceHandle": "timeout", "label": "timeout"},
            {"id": "e-ticket-verify", "source": "ticket", "target": "verify", "sourceHandle": "success", "animated": True},
            {"id": "e-verify-report", "source": "verify", "target": "report", "sourceHandle": "out", "animated": True},
        ],
    },
{
        "slug": "pilot-linux-package-maintenance",
        "name": "Pilot: Linux Package Maintenance",
        "description": "Check package update state, review risk, update explicit package list after approval, verify packages and report.",
        "icon": "PKG",
        "category": "Pilot OPS",
        "tags": ["pilot", "linux", "packages", "maintenance", "approval"],
        "nodes": [
            {"id": "manual", "type": "trigger/manual", "position": {"x": 120, "y": 80}, "data": {"label": "Start package maintenance"}},
            {
                "id": "package_snapshot",
                "type": "ops/server_snapshot",
                "position": {"x": 120, "y": 220},
                "data": {
                    "label": "Read package state",
                    "server_id": "",
                    "sections": ["overview", "packages", "services", "disk"],
                    "on_failure": "abort",
                },
            },
            {
                "id": "review",
                "type": "agent/llm_query",
                "position": {"x": 120, "y": 370},
                "data": {
                    "label": "Review package update risk",
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "system_prompt": "You are a Linux maintenance reviewer. Require approval before package changes and avoid full system upgrades.",
                    "prompt": (
                        "Review package maintenance evidence and the explicit package request.\n\n"
                        "Requested packages: {packages}\n\n"
                        "Package/server state:\n{package_snapshot_output}\n\n"
                        "Return risk, service impact, exact package action, rollback note and post-update verification checklist."
                    ),
                    "include_all_outputs": False,
                },
            },
            {
                "id": "approval",
                "type": "logic/human_approval",
                "position": {"x": 120, "y": 520},
                "data": {
                    "label": "Approve package update",
                    "manual_link_only": True,
                    "timeout_minutes": 120,
                    "message": "Linux package update requires approval.\n\n{review_output}\n\nApprove: {approve_url}\nReject: {reject_url}",
                },
            },
            {
                "id": "apply_updates",
                "type": "ops/package_action",
                "position": {"x": 120, "y": 690},
                "data": {
                    "label": "Update explicit packages",
                    "server_id": "",
                    "action": "update",
                    "packages": "{packages}",
                    "verify": True,
                    "on_failure": "abort",
                },
            },
            {
                "id": "verify_packages",
                "type": "ops/package_action",
                "position": {"x": 120, "y": 850},
                "data": {
                    "label": "Verify package state",
                    "server_id": "",
                    "action": "list_updates",
                    "verify": False,
                    "on_failure": "continue",
                },
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 120, "y": 1010},
                "data": {
                    "label": "Package maintenance report",
                    "template": "# Linux package maintenance report\n\n## Package state\n{package_snapshot_output}\n\n## Review\n{review_output}\n\n## Approval\n{approval_output}\n\n## Update\n{apply_updates_output}\n\n## Verification\n{verify_packages_output}",
                },
            },
            {"id": "rejected", "type": "output/report", "position": {"x": 520, "y": 690}, "data": {"label": "Package update rejected", "template": "# Package update rejected\n\n{approval_error}\n\n## Review\n{review_output}"}},
            {"id": "timed_out", "type": "output/report", "position": {"x": 520, "y": 850}, "data": {"label": "Package update timed out", "template": "# Package update timed out\n\nNo approval was received.\n\n## Review\n{review_output}"}},
        ],
        "edges": [
            {"id": "e-manual-snapshot", "source": "manual", "target": "package_snapshot", "sourceHandle": "out", "animated": True},
            {"id": "e-snapshot-review", "source": "package_snapshot", "target": "review", "sourceHandle": "success", "animated": True},
            {"id": "e-review-approval", "source": "review", "target": "approval", "sourceHandle": "success", "animated": True},
            {"id": "e-approval-update", "source": "approval", "target": "apply_updates", "sourceHandle": "approved", "label": "approved"},
            {"id": "e-approval-rejected", "source": "approval", "target": "rejected", "sourceHandle": "rejected", "label": "rejected"},
            {"id": "e-approval-timeout", "source": "approval", "target": "timed_out", "sourceHandle": "timeout", "label": "timeout"},
            {"id": "e-update-verify", "source": "apply_updates", "target": "verify_packages", "sourceHandle": "success", "animated": True},
            {"id": "e-verify-report", "source": "verify_packages", "target": "report", "sourceHandle": "out", "animated": True},
        ],
    },
]
