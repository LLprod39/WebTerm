"""Pilot pipeline templates for access, rollout and CI/CD workflows."""


PILOT_DELIVERY_TEMPLATES = [
{
        "slug": "cert-expiry-check",
        "name": "Certificate Expiry Check",
        "description": "Checks SSL certificate expiry on configured domains, alerts if < 30 days.",
        "icon": "🔒",
        "category": "Security",
        "tags": ["ssl", "certificates", "monitoring"],
        "nodes": [
            {
                "id": "n1",
                "type": "trigger/schedule",
                "position": {"x": 300, "y": 50},
                "data": {"label": "Daily Check", "cron_expression": "0 8 * * *"},
            },
            {
                "id": "n2",
                "type": "agent/react",
                "position": {"x": 300, "y": 180},
                "data": {
                    "label": "Cert Check Agent",
                    "goal": "Check SSL certificate expiry: For each domain in {domains}: run 'echo | openssl s_client -connect {domain}:443 2>/dev/null | openssl x509 -noout -dates'. Calculate days until expiry. Flag any certificate expiring within 30 days.",
                    "system_prompt": "You are a certificate monitoring agent. Be precise with date calculations.",
                    "max_iterations": 10,
                    "on_failure": "continue",
                },
            },
            {
                "id": "n3",
                "type": "logic/condition",
                "position": {"x": 300, "y": 330},
                "data": {
                    "label": "Any Expiring Soon?",
                    "check_type": "contains",
                    "check_value": "EXPIRING SOON",
                },
            },
            {
                "id": "n4",
                "type": "output/webhook",
                "position": {"x": 150, "y": 470},
                "data": {
                    "label": "Alert Team",
                    "url": "",
                },
            },
            {
                "id": "n5",
                "type": "output/report",
                "position": {"x": 450, "y": 470},
                "data": {"label": "All OK Report"},
            },
        ],
        "edges": [
            {"id": "e1-2", "source": "n1", "target": "n2", "animated": True},
            {"id": "e2-3", "source": "n2", "target": "n3"},
            {"id": "e3-4", "source": "n3", "target": "n4", "sourceHandle": "true"},
            {"id": "e3-5", "source": "n3", "target": "n5", "sourceHandle": "false"},
        ],
    },
{
        "slug": "pilot-keycloak-access-change",
        "name": "Pilot: Keycloak Access Change",
        "description": "Preflight lookup, approval, Keycloak role/group change, verification and audit report through MCP.",
        "icon": "IAM",
        "category": "Pilot OPS",
        "tags": ["pilot", "keycloak", "iam", "mcp", "approval"],
        "nodes": [
            {
                "id": "manual",
                "type": "trigger/manual",
                "position": {"x": 120, "y": 80},
                "data": {"label": "Start access request"},
            },
            {
                "id": "preflight",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 220},
                "data": {
                    "label": "Read current Keycloak access",
                    "mcp_server_id": "",
                    "mcp_server_name": "Keycloak Admin",
                    "tool_name": "keycloak_lookup_subject_access",
                    "arguments": {
                        "realm": "{realm}",
                        "username": "{username}",
                        "group": "{group}",
                        "role": "{role}",
                    },
                    "permission_mode": "READ_ONLY",
                    "skill_slugs": ["keycloak-safety"],
                    "on_failure": "abort",
                },
            },
            {
                "id": "risk_review",
                "type": "agent/llm_query",
                "position": {"x": 120, "y": 370},
                "data": {
                    "label": "Summarize access risk",
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "system_prompt": "You are an IAM change reviewer. Do not approve changes yourself.",
                    "prompt": (
                        "Review the requested Keycloak access change and the current state.\n\n"
                        "Requested target:\n"
                        "- realm: {realm}\n"
                        "- username: {username}\n"
                        "- group: {group}\n"
                        "- role: {role}\n\n"
                        "Current access evidence:\n{preflight_output}\n\n"
                        "Return: risk level, exact proposed MCP action, verification expectation and rollback note."
                    ),
                    "include_all_outputs": False,
                },
            },
            {
                "id": "approval",
                "type": "logic/human_approval",
                "position": {"x": 120, "y": 520},
                "data": {
                    "label": "Approve IAM mutation",
                    "manual_link_only": True,
                    "timeout_minutes": 120,
                    "message": (
                        "Keycloak access change requires approval.\n\n"
                        "Risk review:\n{risk_review_output}\n\n"
                        "Approve: {approve_url}\nReject: {reject_url}"
                    ),
                },
            },
            {
                "id": "apply_change",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 690},
                "data": {
                    "label": "Apply Keycloak access change",
                    "mcp_server_id": "",
                    "mcp_server_name": "Keycloak Admin",
                    "tool_name": "keycloak_apply_access_change",
                    "arguments": {
                        "realm": "{realm}",
                        "username": "{username}",
                        "group": "{group}",
                        "role": "{role}",
                        "operation": "{operation}",
                        "approval": "{approval_output}",
                    },
                    "permission_mode": "ASSISTED",
                    "skill_slugs": ["keycloak-safety"],
                    "on_failure": "abort",
                },
            },
            {
                "id": "verify_change",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 850},
                "data": {
                    "label": "Verify effective access",
                    "mcp_server_id": "",
                    "mcp_server_name": "Keycloak Admin",
                    "tool_name": "keycloak_lookup_subject_access",
                    "arguments": {
                        "realm": "{realm}",
                        "username": "{username}",
                        "group": "{group}",
                        "role": "{role}",
                    },
                    "permission_mode": "READ_ONLY",
                    "skill_slugs": ["keycloak-safety"],
                    "on_failure": "continue",
                },
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 120, "y": 1010},
                "data": {
                    "label": "IAM audit report",
                    "template": (
                        "# Keycloak access change report\n\n"
                        "## Preflight\n{preflight_output}\n\n"
                        "## Risk review\n{risk_review_output}\n\n"
                        "## Approval\n{approval_output}\n\n"
                        "## Change result\n{apply_change_output}\n\n"
                        "## Verification\n{verify_change_output}"
                    ),
                },
            },
            {
                "id": "rejected",
                "type": "output/report",
                "position": {"x": 520, "y": 690},
                "data": {
                    "label": "Access change rejected",
                    "template": "# Keycloak access change rejected\n\n{approval_error}\n\n## Proposed change\n{risk_review_output}",
                },
            },
            {
                "id": "timed_out",
                "type": "output/report",
                "position": {"x": 520, "y": 850},
                "data": {
                    "label": "Access change timed out",
                    "template": "# Keycloak access change timed out\n\nNo approval was received.\n\n## Proposed change\n{risk_review_output}",
                },
            },
        ],
        "edges": [
            {"id": "e-manual-preflight", "source": "manual", "target": "preflight", "sourceHandle": "out", "animated": True},
            {"id": "e-preflight-risk", "source": "preflight", "target": "risk_review", "sourceHandle": "success", "animated": True},
            {"id": "e-risk-approval", "source": "risk_review", "target": "approval", "sourceHandle": "success", "animated": True},
            {"id": "e-approval-apply", "source": "approval", "target": "apply_change", "sourceHandle": "approved", "label": "approved"},
            {"id": "e-approval-rejected", "source": "approval", "target": "rejected", "sourceHandle": "rejected", "label": "rejected"},
            {"id": "e-approval-timeout", "source": "approval", "target": "timed_out", "sourceHandle": "timeout", "label": "timeout"},
            {"id": "e-apply-verify", "source": "apply_change", "target": "verify_change", "sourceHandle": "success", "animated": True},
            {"id": "e-verify-report", "source": "verify_change", "target": "report", "sourceHandle": "out", "animated": True},
        ],
    },
{
        "slug": "pilot-kubernetes-rollout",
        "name": "Pilot: Kubernetes Diagnose And Rollout",
        "description": "Read Kubernetes state through MCP, summarize risk, approve a rollout action, verify rollout status and report.",
        "icon": "K8S",
        "category": "Pilot OPS",
        "tags": ["pilot", "kubernetes", "mcp", "rollout", "approval"],
        "nodes": [
            {"id": "manual", "type": "trigger/manual", "position": {"x": 120, "y": 80}, "data": {"label": "Start Kubernetes workflow"}},
            {
                "id": "inspect",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 220},
                "data": {
                    "label": "Inspect workload",
                    "mcp_server_id": "",
                    "mcp_server_name": "Kubernetes MCP",
                    "tool_name": "kubernetes_describe_workload",
                    "arguments": {"cluster": "{cluster}", "namespace": "{namespace}", "kind": "{kind}", "name": "{workload_name}"},
                    "permission_mode": "READ_ONLY",
                    "on_failure": "abort",
                },
            },
            {
                "id": "plan",
                "type": "agent/llm_query",
                "position": {"x": 120, "y": 370},
                "data": {
                    "label": "Assess rollout risk",
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "system_prompt": "You are a Kubernetes SRE reviewer. Prefer read-only diagnosis unless a human approves mutation.",
                    "prompt": (
                        "Inspect this Kubernetes evidence and decide if rollout restart is justified.\n\n"
                        "{inspect_output}\n\n"
                        "Return risk, blast radius, exact action, rollback/verification plan and operator checklist."
                    ),
                    "include_all_outputs": False,
                },
            },
            {
                "id": "approval",
                "type": "logic/human_approval",
                "position": {"x": 120, "y": 520},
                "data": {
                    "label": "Approve rollout action",
                    "manual_link_only": True,
                    "timeout_minutes": 60,
                    "message": "Kubernetes rollout requires approval.\n\n{plan_output}\n\nApprove: {approve_url}\nReject: {reject_url}",
                },
            },
            {
                "id": "rollout",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 690},
                "data": {
                    "label": "Run approved rollout",
                    "mcp_server_id": "",
                    "mcp_server_name": "Kubernetes MCP",
                    "tool_name": "kubernetes_rollout_restart",
                    "arguments": {"cluster": "{cluster}", "namespace": "{namespace}", "kind": "{kind}", "name": "{workload_name}"},
                    "permission_mode": "ASSISTED",
                    "on_failure": "abort",
                },
            },
            {
                "id": "verify",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 850},
                "data": {
                    "label": "Verify rollout status",
                    "mcp_server_id": "",
                    "mcp_server_name": "Kubernetes MCP",
                    "tool_name": "kubernetes_rollout_status",
                    "arguments": {"cluster": "{cluster}", "namespace": "{namespace}", "kind": "{kind}", "name": "{workload_name}", "timeout_seconds": 300},
                    "permission_mode": "READ_ONLY",
                    "on_failure": "continue",
                },
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 120, "y": 1010},
                "data": {
                    "label": "Kubernetes rollout report",
                    "template": "# Kubernetes rollout report\n\n## Inspection\n{inspect_output}\n\n## Risk plan\n{plan_output}\n\n## Approval\n{approval_output}\n\n## Rollout\n{rollout_output}\n\n## Verification\n{verify_output}",
                },
            },
            {"id": "rejected", "type": "output/report", "position": {"x": 520, "y": 690}, "data": {"label": "Rollout rejected", "template": "# Kubernetes rollout rejected\n\n{approval_error}\n\n## Proposed plan\n{plan_output}"}},
            {"id": "timed_out", "type": "output/report", "position": {"x": 520, "y": 850}, "data": {"label": "Rollout approval timed out", "template": "# Kubernetes rollout timed out\n\nNo approval was received.\n\n## Proposed plan\n{plan_output}"}},
        ],
        "edges": [
            {"id": "e-manual-inspect", "source": "manual", "target": "inspect", "sourceHandle": "out", "animated": True},
            {"id": "e-inspect-plan", "source": "inspect", "target": "plan", "sourceHandle": "success", "animated": True},
            {"id": "e-plan-approval", "source": "plan", "target": "approval", "sourceHandle": "success", "animated": True},
            {"id": "e-approval-rollout", "source": "approval", "target": "rollout", "sourceHandle": "approved", "label": "approved"},
            {"id": "e-approval-rejected", "source": "approval", "target": "rejected", "sourceHandle": "rejected", "label": "rejected"},
            {"id": "e-approval-timeout", "source": "approval", "target": "timed_out", "sourceHandle": "timeout", "label": "timeout"},
            {"id": "e-rollout-verify", "source": "rollout", "target": "verify", "sourceHandle": "success", "animated": True},
            {"id": "e-verify-report", "source": "verify", "target": "report", "sourceHandle": "out", "animated": True},
        ],
    },
{
        "slug": "pilot-gitlab-failed-pipeline-mr",
        "name": "Pilot: GitLab Failed Pipeline To MR",
        "description": "Webhook-driven failed pipeline triage, fix proposal, approval, MR creation and pipeline verification through MCP.",
        "icon": "GL",
        "category": "Pilot OPS",
        "tags": ["pilot", "gitlab", "ci", "mcp", "approval"],
        "nodes": [
            {
                "id": "webhook",
                "type": "trigger/webhook",
                "position": {"x": 120, "y": 80},
                "data": {
                    "label": "GitLab pipeline webhook",
                    "webhook_payload_map": {
                        "project_id": "project.id",
                        "pipeline_id": "object_attributes.id",
                        "branch": "object_attributes.ref",
                        "commit_sha": "object_attributes.sha",
                    },
                },
            },
            {
                "id": "inspect",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 220},
                "data": {
                    "label": "Inspect failed pipeline",
                    "mcp_server_id": "",
                    "mcp_server_name": "GitLab MCP",
                    "tool_name": "gitlab_get_pipeline_failure",
                    "arguments": {"project_id": "{project_id}", "pipeline_id": "{pipeline_id}", "commit_sha": "{commit_sha}"},
                    "permission_mode": "READ_ONLY",
                    "on_failure": "abort",
                },
            },
            {
                "id": "proposal",
                "type": "agent/llm_query",
                "position": {"x": 120, "y": 370},
                "data": {
                    "label": "Propose fix path",
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "system_prompt": "You are a CI/CD support engineer. Prefer PR/MR-first fixes and never push directly to protected branches.",
                    "prompt": (
                        "Analyze the failed GitLab pipeline evidence and produce a proposed MR plan.\n\n"
                        "{inspect_output}\n\n"
                        "Return suspected cause, files likely involved, test command, MR title/body and risk."
                    ),
                    "include_all_outputs": False,
                },
            },
            {
                "id": "approval",
                "type": "logic/human_approval",
                "position": {"x": 120, "y": 520},
                "data": {
                    "label": "Approve MR creation",
                    "manual_link_only": True,
                    "timeout_minutes": 120,
                    "message": "GitLab MR creation requires approval.\n\n{proposal_output}\n\nApprove: {approve_url}\nReject: {reject_url}",
                },
            },
            {
                "id": "create_mr",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 690},
                "data": {
                    "label": "Create GitLab MR",
                    "mcp_server_id": "",
                    "mcp_server_name": "GitLab MCP",
                    "tool_name": "gitlab_create_fix_merge_request",
                    "arguments": {
                        "project_id": "{project_id}",
                        "source_branch": "ops-fix/{pipeline_id}",
                        "target_branch": "{branch}",
                        "commit_sha": "{commit_sha}",
                        "proposal": "{proposal_output}",
                    },
                    "permission_mode": "ASSISTED",
                    "on_failure": "abort",
                },
            },
            {
                "id": "verify",
                "type": "agent/mcp_call",
                "position": {"x": 120, "y": 850},
                "data": {
                    "label": "Verify MR pipeline",
                    "mcp_server_id": "",
                    "mcp_server_name": "GitLab MCP",
                    "tool_name": "gitlab_get_merge_request_pipeline",
                    "arguments": {"project_id": "{project_id}", "merge_request": "{create_mr_output}"},
                    "permission_mode": "READ_ONLY",
                    "on_failure": "continue",
                },
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 120, "y": 1010},
                "data": {
                    "label": "CI support report",
                    "template": "# GitLab CI support report\n\n## Failure evidence\n{inspect_output}\n\n## Proposal\n{proposal_output}\n\n## Approval\n{approval_output}\n\n## MR result\n{create_mr_output}\n\n## Verification\n{verify_output}",
                },
            },
            {"id": "rejected", "type": "output/report", "position": {"x": 520, "y": 690}, "data": {"label": "MR rejected", "template": "# GitLab MR rejected\n\n{approval_error}\n\n## Proposal\n{proposal_output}"}},
            {"id": "timed_out", "type": "output/report", "position": {"x": 520, "y": 850}, "data": {"label": "MR approval timed out", "template": "# GitLab MR approval timed out\n\nNo approval was received.\n\n## Proposal\n{proposal_output}"}},
        ],
        "edges": [
            {"id": "e-webhook-inspect", "source": "webhook", "target": "inspect", "sourceHandle": "out", "animated": True},
            {"id": "e-inspect-proposal", "source": "inspect", "target": "proposal", "sourceHandle": "success", "animated": True},
            {"id": "e-proposal-approval", "source": "proposal", "target": "approval", "sourceHandle": "success", "animated": True},
            {"id": "e-approval-mr", "source": "approval", "target": "create_mr", "sourceHandle": "approved", "label": "approved"},
            {"id": "e-approval-rejected", "source": "approval", "target": "rejected", "sourceHandle": "rejected", "label": "rejected"},
            {"id": "e-approval-timeout", "source": "approval", "target": "timed_out", "sourceHandle": "timeout", "label": "timeout"},
            {"id": "e-mr-verify", "source": "create_mr", "target": "verify", "sourceHandle": "success", "animated": True},
            {"id": "e-verify-report", "source": "verify", "target": "report", "sourceHandle": "out", "animated": True},
        ],
    },
]
