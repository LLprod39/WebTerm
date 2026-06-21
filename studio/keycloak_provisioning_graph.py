from __future__ import annotations

from django.conf import settings

from .keycloak_provisioning_config import (
    KEYCLOAK_IDENTITY_EXECUTION_TOOLS,
    KEYCLOAK_IDENTITY_VERIFY_TOOLS,
    KEYCLOAK_PLATFORM_EXECUTION_TOOLS,
    KEYCLOAK_PLATFORM_VERIFY_TOOLS,
    WEBHOOK_CONTEXT_MAP,
    _json_payload,
    _merge_tools,
)


def build_keycloak_nodes(mcp_server_id: int) -> list[dict]:
    return [
        {
            "id": "start_manual",
            "type": "trigger/manual",
            "position": {"x": 340, "y": 40},
            "data": {
                "label": "Run Provisioning",
                "is_active": True,
                "description": "Manual run expects JSON context via the pipeline run API.",
            },
        },
        {
            "id": "start_webhook",
            "type": "trigger/webhook",
            "position": {"x": 820, "y": 40},
            "data": {
                "label": "Webhook Provisioning",
                "is_active": True,
                "webhook_payload_map": WEBHOOK_CONTEXT_MAP,
            },
        },
        {
            "id": "entry_join",
            "type": "logic/merge",
            "position": {"x": 580, "y": 120},
            "data": {
                "label": "Selected Trigger Entry",
                "mode": "any",
            },
        },
        {
            "id": "environment_preflight",
            "type": "agent/mcp_call",
            "position": {"x": 190, "y": 210},
            "data": {
                "label": "MCP: Environment Preflight",
                "mcp_server_id": mcp_server_id,
                "tool_name": "keycloak_current_environment",
                "arguments_text": _json_payload({"profile": "{profile}"}),
                "on_failure": "continue",
            },
        },
        {
            "id": "existing_user_lookup",
            "type": "agent/mcp_call",
            "position": {"x": 640, "y": 210},
            "data": {
                "label": "MCP: Existing User Lookup",
                "mcp_server_id": mcp_server_id,
                "tool_name": "keycloak_find_user",
                "arguments_text": _json_payload({"login": "{username}", "profile": "{profile}"}),
                "on_failure": "continue",
            },
        },
        {
            "id": "preflight_merge",
            "type": "logic/merge",
            "position": {"x": 430, "y": 320},
            "data": {
                "label": "Preflight Ready",
                "mode": "all",
            },
        },
        {
            "id": "normalize_request",
            "type": "agent/llm_query",
            "position": {"x": 430, "y": 430},
            "data": {
                "label": "Model: Build Provisioning Plan",
                "provider": "openai",
                "model": "gpt-5-mini",
                "system_prompt": (
                    "You are a careful IAM provisioning planner for Keycloak. "
                    "Normalize the request, surface risks, and produce strict machine-readable JSON."
                ),
                "prompt": (
                    "You are preparing a provisioning plan for a Keycloak MCP pipeline.\n\n"
                    "## Incoming request context\n"
                    "- profile: {profile}\n"
                    "- base_url: {base_url}\n"
                    "- realm: {realm}\n"
                    "- token_realm: {token_realm}\n"
                    "- client_id: {client_id}\n"
                    "- username: {username}\n"
                    "- email: {email}\n"
                    "- first_name: {first_name}\n"
                    "- last_name: {last_name}\n"
                    "- temporary_password: {temporary_password}\n"
                    "- realm_roles: {realm_roles}\n"
                    "- client_roles: {client_roles}\n"
                    "- groups: {groups}\n"
                    "- attributes: {attributes}\n"
                    "- required_actions: {required_actions}\n"
                    "- allow_existing_user: {allow_existing_user}\n\n"
                    "## Read-only preflight\n"
                    "Current environment:\n{environment_preflight_output}\n\n"
                    "Existing user lookup:\n{existing_user_lookup_output}\n\n"
                    "## Task\n"
                    "Return STRICT JSON only. No markdown fences.\n"
                    "Schema:\n"
                    "{\n"
                    '  "request_valid": true,\n'
                    '  "missing_fields": [],\n'
                    '  "profile": "prod",\n'
                    '  "auth": {"base_url": "", "realm": "", "token_realm": "", "client_id": ""},\n'
                    '  "user": {\n'
                    '    "username": "", "email": "", "first_name": "", "last_name": "",\n'
                    '    "temporary_password": "", "attributes": {}, "required_actions": []\n'
                    "  },\n"
                    '  "allow_existing_user": false,\n'
                    '  "realm_roles": [],\n'
                    '  "client_roles": {},\n'
                    '  "groups": [],\n'
                    '  "risk_summary": [],\n'
                    '  "approval_summary": "short human summary",\n'
                    '  "existing_user_found": false\n'
                    "}\n\n"
                    "Rules:\n"
                    "- Keep arrays/objects valid JSON.\n"
                    "- If something required is missing, set request_valid=false and list missing_fields.\n"
                    "- If existing_user_lookup found a user, set existing_user_found=true.\n"
                    "- Do not invent roles, groups, or clients that were not provided."
                ),
                "include_all_outputs": False,
                "on_failure": "abort",
            },
        },
        {
            "id": "await_approval",
            "type": "logic/human_approval",
            "position": {"x": 430, "y": 650},
            "data": {
                "label": "Await Approval",
                "to_email": "",
                "email_subject": "Keycloak provisioning approval required (run #{run_id})",
                "email_body": (
                    "A Keycloak provisioning request is waiting for your decision.\n\n"
                    "## Planned request\n"
                    "{normalize_request_output}\n\n"
                    "## Existing user lookup\n"
                    "{existing_user_lookup_output}\n\n"
                    "## Environment\n"
                    "{environment_preflight_output}\n\n"
                    "APPROVE:\n{approve_url}\n\n"
                    "REJECT:\n{reject_url}\n\n"
                    "Link lifetime: {timeout_minutes} minutes."
                ),
                "tg_bot_token": "",
                "tg_chat_id": "",
                "base_url": getattr(settings, "SITE_URL", "http://localhost:8000") or "http://localhost:8000",
                "timeout_minutes": 240,
                "message": (
                    "Keycloak provisioning approval required.\n\n"
                    "{normalize_request_output}\n\n"
                    "APPROVE: {approve_url}\n\n"
                    "REJECT: {reject_url}"
                ),
                "smtp_host": "",
                "smtp_user": "",
                "smtp_password": "",
                "from_email": "",
            },
        },
        {
            "id": "execute_keycloak_plan",
            "type": "agent/react",
            "position": {"x": 430, "y": 900},
            "data": {
                "label": "Agent: Execute Keycloak Provisioning",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 18,
                "allowed_tools": _merge_tools(
                    KEYCLOAK_IDENTITY_EXECUTION_TOOLS,
                    KEYCLOAK_PLATFORM_EXECUTION_TOOLS,
                    KEYCLOAK_IDENTITY_VERIFY_TOOLS,
                    KEYCLOAK_PLATFORM_VERIFY_TOOLS,
                ),
                "system_prompt": (
                    "You are a Keycloak IAM operator. Execute only via attached MCP tools. "
                    "Be deterministic, do not guess missing values, and prefer exact identifiers over fuzzy matches."
                ),
                "goal": (
                    "You are executing a Keycloak provisioning request.\n\n"
                    "Approval result:\n{await_approval_output}\n\n"
                    "Normalized request JSON:\n{normalize_request_output}\n\n"
                    "Existing user lookup:\n{existing_user_lookup_output}\n\n"
                    "Current environment:\n{environment_preflight_output}\n\n"
                    "Rules:\n"
                    "1. If approval does not clearly contain APPROVED, do not perform mutations. Return a short report saying no changes were made.\n"
                    "2. Parse the normalized JSON request. If request_valid is false or missing_fields is non-empty, stop and report the validation failure.\n"
                    "3. Use the attached Keycloak MCP tools only.\n"
                    "4. First determine whether the target user already exists. Reuse exact user_id when possible.\n"
                    "5. If the user exists and allow_existing_user is false, stop and report without changing anything.\n"
                    "6. If the user does not exist, create the user with the provided profile/auth settings and temporary password if present.\n"
                    "7. Assign realm roles, then client roles, then groups. Only apply items explicitly listed in the normalized request.\n"
                    "8. After mutations, verify the final state using read tools for realm roles, client roles, and groups.\n"
                    "9. Never use allow_fuzzy_user_match unless you first verified the exact target from read-only lookup output.\n"
                    "10. Return a final Markdown report with sections: Summary, Actions Performed, Skipped, Verification, Errors."
                ),
                "on_failure": "abort",
            },
        },
        {
            "id": "report_gate",
            "type": "logic/merge",
            "position": {"x": 430, "y": 1030},
            "data": {
                "label": "Report Gate",
                "mode": "any",
            },
        },
        {
            "id": "final_report",
            "type": "output/report",
            "position": {"x": 430, "y": 1150},
            "data": {
                "label": "Provisioning Report",
                "template": (
                    "# Keycloak Provisioning Report\n\n"
                    "## Input\n"
                    "- profile: {profile}\n"
                    "- username: {username}\n"
                    "- email: {email}\n"
                    "- realm_roles: {realm_roles}\n"
                    "- client_roles: {client_roles}\n"
                    "- groups: {groups}\n"
                    "- allow_existing_user: {allow_existing_user}\n\n"
                    "## Environment Preflight\n"
                    "{environment_preflight_output}\n\n"
                    "## Existing User Lookup\n"
                    "{existing_user_lookup_output}\n\n"
                    "## Normalized Plan\n"
                    "{normalize_request_output}\n\n"
                    "## Approval\n"
                    "- status: {await_approval_status}\n"
                    "- output: {await_approval_output}\n"
                    "- error: {await_approval_error}\n\n"
                    "## Execution Agent\n"
                    "- status: {execute_keycloak_plan_status}\n"
                    "- error: {execute_keycloak_plan_error}\n\n"
                    "{execute_keycloak_plan_output}\n"
                ),
            },
        },
    ]


def build_keycloak_edges() -> list[dict]:
    return [
        {"id": "e1", "source": "start_manual", "target": "entry_join", "sourceHandle": "out", "animated": True},
        {"id": "e2", "source": "start_webhook", "target": "entry_join", "sourceHandle": "out", "animated": True},
        {"id": "e3", "source": "entry_join", "target": "environment_preflight", "sourceHandle": "out", "animated": True},
        {"id": "e4", "source": "entry_join", "target": "existing_user_lookup", "sourceHandle": "out", "animated": True},
        {"id": "e5", "source": "environment_preflight", "target": "preflight_merge", "sourceHandle": "success", "animated": True},
        {"id": "e6", "source": "environment_preflight", "target": "preflight_merge", "sourceHandle": "error", "animated": True},
        {"id": "e7", "source": "existing_user_lookup", "target": "preflight_merge", "sourceHandle": "success", "animated": True},
        {"id": "e8", "source": "existing_user_lookup", "target": "preflight_merge", "sourceHandle": "error", "animated": True},
        {"id": "e9", "source": "preflight_merge", "target": "normalize_request", "sourceHandle": "out", "animated": True},
        {"id": "e10", "source": "normalize_request", "target": "await_approval", "sourceHandle": "success", "animated": True},
        {"id": "e11", "source": "await_approval", "target": "execute_keycloak_plan", "sourceHandle": "approved", "animated": True},
        {"id": "e12", "source": "await_approval", "target": "report_gate", "sourceHandle": "rejected", "animated": True},
        {"id": "e13", "source": "await_approval", "target": "report_gate", "sourceHandle": "timeout", "animated": True},
        {"id": "e14", "source": "execute_keycloak_plan", "target": "report_gate", "sourceHandle": "success", "animated": True},
        {"id": "e15", "source": "execute_keycloak_plan", "target": "report_gate", "sourceHandle": "error", "animated": True},
        {"id": "e16", "source": "report_gate", "target": "final_report", "sourceHandle": "out", "animated": True},
    ]
