from __future__ import annotations

import json
import os

from django.conf import settings

from .models import CURRENT_PIPELINE_GRAPH_VERSION, MCPServerPool, Pipeline

KEYCLOAK_MCP_NAME = "Keycloak Admin"
KEYCLOAK_MCP_URL = os.getenv("STUDIO_KEYCLOAK_MCP_URL", "http://127.0.0.1:8766/mcp")
KEYCLOAK_PIPELINE_NAME = "Keycloak Provisioning with Approval"
KEYCLOAK_PIPELINE_DESCRIPTION = (
    "Human-approved Keycloak provisioning flow for Studio. It accepts manual or webhook context, "
    "runs a read-only preflight against Keycloak, asks for approval, then lets an MCP-enabled agent "
    "create the user, assign realm roles, assign client roles, add groups, and verify the final state."
)
KEYCLOAK_OPS_PIPELINE_SPECS = {
    "test": {
        "name": "Keycloak Ops TEST",
        "description": (
            "Universal Keycloak operator pipeline for the TEST environment. "
            "Accepts broad free-form Keycloak requests, uses the fixed 'test' MCP profile, "
            "performs visible discovery and planning steps, and sends no email or Telegram messages."
        ),
        "label": "TEST",
    },
    "prod": {
        "name": "Keycloak Ops PROD",
        "description": (
            "Universal Keycloak operator pipeline for the PROD environment. "
            "Accepts broad free-form Keycloak requests, uses the fixed 'prod' MCP profile, "
            "performs visible discovery and planning steps, and sends no email or Telegram messages."
        ),
        "label": "PROD",
    },
}

SAMPLE_MANUAL_CONTEXT = {
    "profile": "prod",
    "username": "ivan.petrov",
    "email": "ivan.petrov@example.com",
    "first_name": "Ivan",
    "last_name": "Petrov",
    "temporary_password": "Temp12345!",
    "realm_roles": ["offline_access"],
    "client_roles": {"crm-app": ["read", "write"]},
    "groups": ["/sales", "/crm-users"],
    "attributes": {"department": ["sales"]},
    "required_actions": ["UPDATE_PASSWORD"],
    "allow_existing_user": False,
}
SAMPLE_TASK_CONTEXT = {
    "task": "Создай пользователя ivan.petrov, выдай роли crm-app: read, write и добавь в группы /sales и /crm-users",
    "requester": "Service Desk",
    "ticket_id": "IAM-1001",
    "username": "ivan.petrov",
    "email": "ivan.petrov@example.com",
    "first_name": "Ivan",
    "last_name": "Petrov",
    "temporary_password": "Temp12345!",
    "realm_roles": ["offline_access"],
    "client_roles": {"crm-app": ["read", "write"]},
    "groups": ["/sales", "/crm-users"],
    "attributes": {"department": ["sales"]},
    "required_actions": ["UPDATE_PASSWORD"],
    "allow_existing_user": False,
}
SAMPLE_BULK_TASK_CONTEXT = {
    "task": (
        "Просим присвоить роль в Keycloak SALESERG_MANAGER на портале SalesMarket. "
        "Сотрудникам KAZ Minerals: Манкеев Галым galym.mankeyev@kazminerals.com; "
        "Бухтояров Владимир vladimir.bukhtoyarov@kazminerals.com; "
        "Жумадилов Айлан ailan.zhumadilov@kazminerals.com."
    ),
    "requester": "SalesMarket Service Desk",
    "ticket_id": "IAM-2007",
    "client_roles": {"SalesMarket": ["SALESERG_MANAGER"]},
    "allow_existing_user": True,
}

WEBHOOK_CONTEXT_MAP = {
    "profile": "profile",
    "base_url": "base_url",
    "realm": "realm",
    "token_realm": "token_realm",
    "client_id": "client_id",
    "admin_user": "admin_user",
    "admin_password_env": "admin_password_env",
    "client_secret_env": "client_secret_env",
    "username": "username",
    "email": "email",
    "first_name": "first_name",
    "last_name": "last_name",
    "temporary_password": "temporary_password",
    "realm_roles": "realm_roles",
    "client_roles": "client_roles",
    "groups": "groups",
    "attributes": "attributes",
    "required_actions": "required_actions",
    "allow_existing_user": "allow_existing_user",
}
TASK_WEBHOOK_CONTEXT_MAP = {
    "task": "task",
    "requester": "requester",
    "ticket_id": "ticket_id",
    "username": "username",
    "email": "email",
    "first_name": "first_name",
    "last_name": "last_name",
    "temporary_password": "temporary_password",
    "realm_roles": "realm_roles",
    "client_roles": "client_roles",
    "groups": "groups",
    "attributes": "attributes",
    "required_actions": "required_actions",
    "allow_existing_user": "allow_existing_user",
}


def _keycloak_mcp(tool_name: str) -> str:
    return f"mcp_keycloak_admin_{tool_name}"


def _keycloak_tools(*tool_names: str) -> list[str]:
    return [_keycloak_mcp(name) for name in tool_names]


def _merge_tools(*tool_groups: list[str]) -> list[str]:
    return list(dict.fromkeys(tool for group in tool_groups for tool in group))


KEYCLOAK_CLIENT_DISCOVERY_TOOLS = _keycloak_tools(
    "keycloak_current_environment",
    "keycloak_list_clients",
    "keycloak_find_clients_with_role",
    "keycloak_list_client_roles",
)
KEYCLOAK_USER_DISCOVERY_TOOLS = _keycloak_tools(
    "keycloak_current_environment",
    "keycloak_search_users",
    "keycloak_find_user",
    "keycloak_get_user_roles",
    "keycloak_get_user_realm_roles",
    "keycloak_get_user_groups",
)
KEYCLOAK_GROUP_ROLE_DISCOVERY_TOOLS = _keycloak_tools(
    "keycloak_current_environment",
    "keycloak_list_groups",
    "keycloak_get_realm_roles",
)
KEYCLOAK_PROTOCOL_MAPPER_DISCOVERY_TOOLS = _keycloak_tools(
    "keycloak_current_environment",
    "keycloak_list_clients",
    "keycloak_list_protocol_mappers",
)
KEYCLOAK_IDENTITY_EXECUTION_TOOLS = _keycloak_tools(
    "keycloak_current_environment",
    "keycloak_search_users",
    "keycloak_find_user",
    "keycloak_create_user",
    "keycloak_assign_roles",
    "keycloak_assign_realm_roles",
    "keycloak_add_user_to_groups",
    "keycloak_get_user_roles",
    "keycloak_get_user_realm_roles",
    "keycloak_get_user_groups",
)
KEYCLOAK_PLATFORM_EXECUTION_TOOLS = _keycloak_tools(
    "keycloak_current_environment",
    "keycloak_list_clients",
    "keycloak_list_client_roles",
    "keycloak_list_groups",
    "keycloak_get_realm_roles",
    "keycloak_list_protocol_mappers",
    "keycloak_create_group",
    "keycloak_create_client",
    "keycloak_create_client_role",
    "keycloak_create_realm_role",
    "keycloak_add_protocol_mapper",
    "keycloak_assign_service_account_roles",
)
KEYCLOAK_IDENTITY_VERIFY_TOOLS = _keycloak_tools(
    "keycloak_current_environment",
    "keycloak_search_users",
    "keycloak_find_user",
    "keycloak_get_user_roles",
    "keycloak_get_user_realm_roles",
    "keycloak_get_user_groups",
)
KEYCLOAK_PLATFORM_VERIFY_TOOLS = _keycloak_tools(
    "keycloak_current_environment",
    "keycloak_list_clients",
    "keycloak_list_client_roles",
    "keycloak_list_groups",
    "keycloak_get_realm_roles",
    "keycloak_list_protocol_mappers",
)


def _json_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _normalize_prompt(fixed_profile: str, environment_label: str) -> str:
    return (
        f"You are preparing a strict execution brief for the {environment_label} Keycloak operator pipeline.\n"
        f"The MCP profile is FIXED to '{fixed_profile}'. Never change it.\n\n"
        "## Inputs\n"
        "- task: {task}\n"
        "- requester: {requester}\n"
        "- allow_existing_user: {allow_existing_user}\n"
        "- environment_preflight_output: {environment_preflight_output}\n\n"
        "Return STRICT JSON only. No markdown fences.\n"
        "Schema:\n"
        "{\n"
        f'  "profile": "{fixed_profile}",\n'
        '  "request_valid": true,\n'
        '  "requested_mode": "read_only|mutating",\n'
        '  "intent": "user_access|bulk_role_assignment|realm_role_assignment|group_management|user_creation|client_admin|role_admin|audit|mixed|unsupported",\n'
        '  "summary": "",\n'
        '  "target_count": 0,\n'
        '  "task_text": "",\n'
        '  "client_hints": [],\n'
        '  "role_hints": [],\n'
        '  "group_hints": [],\n'
        '  "mapper_hints": [\n'
        "    {\n"
        '      "client_hint": "",\n'
        '      "mapper_name": "",\n'
        '      "user_attribute": "",\n'
        '      "token_claim": "",\n'
        '      "add_to_id_token": true,\n'
        '      "add_to_access_token": true\n'
        "    }\n"
        "  ],\n"
        '  "service_account_role_hints": [{"client_hint": "", "roles": []}],\n'
        '  "users": [\n'
        "    {\n"
        '      "input_text": "",\n'
        '      "full_name": "",\n'
        '      "email": "",\n'
        '      "username": "",\n'
        '      "company": "",\n'
        '      "attributes": {},\n'
        '      "required_actions": []\n'
        "    }\n"
        "  ],\n"
        '  "new_clients": [{"client_id": "", "name": "", "description": ""}],\n'
        '  "new_client_roles": [{"client_hint": "", "role_name": "", "description": ""}],\n'
        '  "new_realm_roles": [{"role_name": "", "description": ""}],\n'
        '  "new_groups": [{"group_name": "", "parent_group": ""}],\n'
        '  "allow_existing_user": true,\n'
        '  "assumptions": [],\n'
        '  "warnings": [],\n'
        '  "blocking_issues": []\n'
        "}\n\n"
        "Rules:\n"
        "- requester is optional metadata and must not make request_valid=false.\n"
        "- Treat free-form lists, tables, and messy service-desk text as valid input.\n"
        "- Emails are valid target identifiers. Username is optional when email exists.\n"
        "- If one client/portal and one role are stated once and then multiple people follow, apply that same access to all parsed users.\n"
        "- If multiple clients are stated once and then multiple protocol-mapper lines follow, apply those mapper definitions to all listed clients unless the text says otherwise.\n"
        "- If the task mentions a portal or client name, put it into client_hints.\n"
        "- If the task mentions role names, put them into role_hints.\n"
        "- If the task requests protocol mappers or user attribute mappings, fill mapper_hints with concrete client_hint, mapper_name, user_attribute, and token_claim values.\n"
        "- For requests phrased like 'Поле USER_REPO_ID (User Attribute) в поле userId', treat USER_REPO_ID as user_attribute and userId as token_claim. If mapper_name is not explicitly given, use token_claim as mapper_name.\n"
        "- If the task requests service-account access, fill service_account_role_hints.\n"
        "- If the task is about creating a client, client role, realm role, user, group, protocol mapper, or service-account role assignment, classify accordingly.\n"
        "- request_valid=false only when the intended action or the targets are genuinely ambiguous.\n"
        "- Do not invent users, clients, roles, groups, passwords, or attributes.\n"
        "- Keep arrays and objects valid JSON."
    )


def _discovery_clients_goal(fixed_profile: str, environment_label: str) -> str:
    return (
        f"You are a read-only Keycloak client and client-role discovery agent for the fixed '{fixed_profile}' profile ({environment_label}).\n\n"
        "Environment preflight:\n{environment_preflight_output}\n\n"
        "Normalized brief JSON:\n{normalize_request_output}\n\n"
        "Original task:\n{task}\n\n"
        "Rules:\n"
        f"1. Use ONLY attached Keycloak MCP tools and ALWAYS pass profile='{fixed_profile}'.\n"
        "2. Perform READ-ONLY actions only. Never mutate Keycloak in this node.\n"
        "3. Discover concrete clients and client roles from the normalized brief.\n"
        "4. For client hints, first use keycloak_list_clients with safe candidate variants such as original case, lowercase, hyphenated, underscored, punctuation-stripped forms, and meaningful word fragments from the hint.\n"
        "5. If role_hints exist, use keycloak_find_clients_with_role to find which candidate clients actually contain the requested client role. Do not stop at the first client candidate; evaluate all credible candidates until the role check resolves the ambiguity.\n"
        "6. Only after candidate discovery, use keycloak_list_client_roles to verify exact role hits on the best candidate clients.\n"
        "7. Also inspect new_client_roles hints and determine whether the target client already exists.\n"
        "8. Return STRICT JSON only with this schema:\n"
        "{\n"
        '  "profile": "' + fixed_profile + '",\n'
        '  "client_checks": [{"hint": "", "candidates": [{"client_id": "", "status": "verified|not_found|ambiguous", "role_hits": [], "notes": []}]}],\n'
        '  "client_role_checks": [{"client_id": "", "requested_roles": [], "existing_roles": [], "missing_roles": [], "notes": []}],\n'
        '  "client_creation_checks": [{"client_id": "", "status": "exists|missing|ambiguous", "notes": []}],\n'
        '  "blocking_issues": [],\n'
        '  "warnings": []\n'
        "}\n"
        "9. Output JSON only."
    )


def _discovery_users_goal(fixed_profile: str, environment_label: str) -> str:
    return (
        f"You are a read-only Keycloak user discovery agent for the fixed '{fixed_profile}' profile ({environment_label}).\n\n"
        "Environment preflight:\n{environment_preflight_output}\n\n"
        "Normalized brief JSON:\n{normalize_request_output}\n\n"
        "Rules:\n"
        f"1. Use ONLY attached Keycloak MCP tools and ALWAYS pass profile='{fixed_profile}'.\n"
        "2. Perform READ-ONLY actions only. Never mutate Keycloak in this node.\n"
        "3. For each user target, use exact search first.\n"
        "4. If exact search returns zero, you MUST call keycloak_find_user for ranked candidates.\n"
        "5. Prefer exact email matches. Strong ranked candidates may be recorded, but must be marked as unverified if ambiguity remains.\n"
        "6. Return STRICT JSON only with this schema:\n"
        "{\n"
        '  "profile": "' + fixed_profile + '",\n'
        '  "user_checks": [{"input_text": "", "email": "", "username": "", "status": "exact|strong_candidate|ambiguous|not_found", "resolved_user": {"id": "", "username": "", "email": "", "enabled": true}, "candidates": [], "notes": []}],\n'
        '  "blocking_issues": [],\n'
        '  "warnings": []\n'
        "}\n"
        "7. Output JSON only."
    )


def _discovery_groups_roles_goal(fixed_profile: str, environment_label: str) -> str:
    return (
        f"You are a read-only Keycloak group and realm-role discovery agent for the fixed '{fixed_profile}' profile ({environment_label}).\n\n"
        "Environment preflight:\n{environment_preflight_output}\n\n"
        "Normalized brief JSON:\n{normalize_request_output}\n\n"
        "Rules:\n"
        f"1. Use ONLY attached Keycloak MCP tools and ALWAYS pass profile='{fixed_profile}'.\n"
        "2. Perform READ-ONLY actions only. Never mutate Keycloak in this node.\n"
        "3. Verify group hints and new_groups using list/read group tools.\n"
        "4. Verify realm role hints and new_realm_roles using realm role read tools.\n"
        "5. Return STRICT JSON only with this schema:\n"
        "{\n"
        '  "profile": "' + fixed_profile + '",\n'
        '  "group_checks": [{"group": "", "status": "verified|not_found|ambiguous", "matched_path": "", "notes": []}],\n'
        '  "realm_role_checks": [{"role": "", "status": "verified|not_found|ambiguous", "notes": []}],\n'
        '  "group_creation_checks": [{"group_name": "", "parent_group": "", "status": "exists|missing|ambiguous", "notes": []}],\n'
        '  "blocking_issues": [],\n'
        '  "warnings": []\n'
        "}\n"
        "6. Output JSON only."
    )


def _discovery_protocol_mappers_goal(fixed_profile: str, environment_label: str) -> str:
    return (
        f"You are a read-only Keycloak protocol-mapper discovery agent for the fixed '{fixed_profile}' profile ({environment_label}).\n\n"
        "Environment preflight:\n{environment_preflight_output}\n\n"
        "Normalized brief JSON:\n{normalize_request_output}\n\n"
        "Client discovery JSON:\n{discover_clients_roles_output}\n\n"
        "Rules:\n"
        f"1. Use ONLY attached Keycloak MCP tools and ALWAYS pass profile='{fixed_profile}'.\n"
        "2. Perform READ-ONLY actions only. Never mutate Keycloak in this node.\n"
        "3. For each mapper hint, resolve the client from client discovery and then inspect existing protocol mappers on that client.\n"
        "4. Mark each requested mapper as exists, missing, ambiguous_client, or client_not_found.\n"
        "5. Return STRICT JSON only with this schema:\n"
        "{\n"
        '  "profile": "' + fixed_profile + '",\n'
        '  "protocol_mapper_checks": [{"client_hint": "", "resolved_client_id": "", "requested_mappers": [{"mapper_name": "", "user_attribute": "", "token_claim": "", "status": "exists|missing|ambiguous_client|client_not_found", "notes": []}], "existing_mappers": []}],\n'
        '  "blocking_issues": [],\n'
        '  "warnings": []\n'
        "}\n"
        "6. Output JSON only."
    )


def _plan_prompt(fixed_profile: str, environment_label: str) -> str:
    return (
        f"You are building a safe execution plan for the {environment_label} Keycloak operator pipeline.\n"
        f"The profile is fixed to '{fixed_profile}'.\n\n"
        "Inputs:\n"
        "- Original task: {task}\n"
        "- Normalized brief: {normalize_request_output}\n"
        "- Client/role discovery: {discover_clients_roles_output}\n"
        "- User discovery: {discover_users_output}\n"
        "- Group/realm-role discovery: {discover_groups_roles_output}\n"
        "- Protocol mapper discovery: {discover_protocol_mappers_output}\n\n"
        "Return STRICT JSON only. No markdown fences.\n"
        "Schema:\n"
        "{\n"
        f'  "profile": "{fixed_profile}",\n'
        '  "ready_to_execute": true,\n'
        '  "requested_mode": "read_only|mutating",\n'
        '  "intent": "",\n'
        '  "client_role_assignments": [{"client_id": "", "roles": [], "targets": [{"user_id": "", "login": "", "email": "", "resolution": "exact|strong_candidate"}]}],\n'
        '  "realm_role_assignments": [{"roles": [], "targets": [{"user_id": "", "login": "", "email": "", "resolution": "exact|strong_candidate"}]}],\n'
        '  "group_additions": [{"groups": [], "targets": [{"user_id": "", "login": "", "email": "", "resolution": "exact|strong_candidate"}]}],\n'
        '  "create_users": [{"username": "", "email": "", "first_name": "", "last_name": "", "temporary_password": "", "attributes": {}, "required_actions": []}],\n'
        '  "create_groups": [{"group_name": "", "parent_group": ""}],\n'
        '  "create_clients": [{"client_id": "", "name": "", "description": ""}],\n'
        '  "create_client_roles": [{"client_id": "", "role_name": "", "description": ""}],\n'
        '  "create_realm_roles": [{"role_name": "", "description": ""}],\n'
        '  "protocol_mappers": [{"client_id": "", "mapper_name": "", "user_attribute": "", "token_claim": "", "add_to_id_token": true, "add_to_access_token": true}],\n'
        '  "service_account_role_assignments": [{"client_id": "", "roles": []}],\n'
        '  "verification_targets": {"users": [], "clients": [], "groups": [], "protocol_mappers": []},\n'
        '  "blocking_issues": [],\n'
        '  "warnings": []\n'
        "}\n\n"
        "Rules:\n"
        "- ready_to_execute=true when there is at least one safe concrete action to perform, even if some targets remain ambiguous.\n"
        "- Use exact user matches whenever available. Strong candidates may be included only when they are unique and well-justified.\n"
        "- Omit ambiguous or unsafe targets from assignment lists instead of blocking the whole plan.\n"
        "- Put skipped or unresolved targets into warnings or blocking_issues, but still plan safe partial execution when possible.\n"
        "- Do not require requester or ticket metadata.\n"
        "- If the task is read-only, produce no mutating actions.\n"
        "- Use protocol_mappers for user-attribute mapper creation tasks.\n"
        "- Use create_groups for group creation tasks and service_account_role_assignments for service-account role tasks.\n"
        "- Keep ready_to_execute=false only when there are zero safe actions to perform or the client/role/group targets are fundamentally unresolved.\n"
        "- Output JSON only."
    )


def _identity_execution_goal(fixed_profile: str, environment_label: str) -> str:
    return (
        f"You are executing identity-level Keycloak actions against the fixed '{fixed_profile}' profile ({environment_label}).\n\n"
        "Environment preflight:\n{environment_preflight_output}\n\n"
        "Normalized brief JSON:\n{normalize_request_output}\n\n"
        "User discovery JSON:\n{discover_users_output}\n\n"
        "Client/role discovery JSON:\n{discover_clients_roles_output}\n\n"
        "Group/realm-role discovery JSON:\n{discover_groups_roles_output}\n\n"
        "Execution plan JSON:\n{build_execution_plan_output}\n\n"
        "Original task:\n{task}\n\n"
        "Rules:\n"
        f"1. Use ONLY the attached Keycloak MCP tools and ALWAYS pass profile='{fixed_profile}' in MCP calls.\n"
        "2. Never use ask_user. If the plan is not safe enough, stop and write a blocking report instead of asking.\n"
        "3. If ready_to_execute=false, do not mutate anything.\n"
        "4. Execute ONLY these action types from the plan: create_users, client_role_assignments, realm_role_assignments, group_additions.\n"
        "5. Execute safe partial plans. If some targets are omitted from the plan because they were ambiguous, leave them skipped and continue with the verified ones.\n"
        "6. For mutating tasks, prefer exact user ids. Use strong candidates only when the plan explicitly approved them.\n"
        "7. Process targets independently. If one target fails, continue with others and record the failure.\n"
        "8. Search/read first when needed, then mutate, then record what changed.\n"
        "9. Do not create clients, roles, groups, or protocol mappers in this node.\n"
        "10. Do not change auth configuration, do not switch profile, and do not send external notifications.\n"
        "11. Return a final Markdown report with sections: Summary, Actions Performed, Skipped, Errors, Per-Target Results."
    )


def _platform_execution_goal(fixed_profile: str, environment_label: str) -> str:
    return (
        f"You are executing platform-level Keycloak actions against the fixed '{fixed_profile}' profile ({environment_label}).\n\n"
        "Environment preflight:\n{environment_preflight_output}\n\n"
        "Client/role discovery JSON:\n{discover_clients_roles_output}\n\n"
        "Group/realm-role discovery JSON:\n{discover_groups_roles_output}\n\n"
        "Protocol mapper discovery JSON:\n{discover_protocol_mappers_output}\n\n"
        "Execution plan JSON:\n{build_execution_plan_output}\n\n"
        "Original task:\n{task}\n\n"
        "Rules:\n"
        f"1. Use ONLY the attached Keycloak MCP tools and ALWAYS pass profile='{fixed_profile}' in MCP calls.\n"
        "2. Never use ask_user. If the plan is not safe enough, stop and write a blocking report instead of asking.\n"
        "3. If ready_to_execute=false, do not mutate anything.\n"
        "4. Execute ONLY these action types from the plan: create_groups, create_clients, create_client_roles, create_realm_roles, protocol_mappers, service_account_role_assignments.\n"
        "5. Follow the plan strictly. Do not invent new clients, groups, roles, or protocol mappers.\n"
        "6. For protocol_mappers, skip items whose client is ambiguous or unresolved.\n"
        "7. Process targets independently. If one target fails, continue with others and record the failure.\n"
        "8. Perform prerequisite creation first: groups/clients/roles before dependent mapper or service-account actions.\n"
        "9. Do not create or change end-user assignments in this node.\n"
        "10. Return a final Markdown report with sections: Summary, Actions Performed, Skipped, Errors, Per-Target Results."
    )


def _identity_verification_goal(fixed_profile: str, environment_label: str) -> str:
    return (
        f"You are a read-only Keycloak identity verification agent for the fixed '{fixed_profile}' profile ({environment_label}).\n\n"
        "Execution plan JSON:\n{build_execution_plan_output}\n\n"
        "Identity execution report:\n{execute_identity_actions_output}\n\n"
        "Rules:\n"
        f"1. Use ONLY attached Keycloak MCP tools and ALWAYS pass profile='{fixed_profile}'.\n"
        "2. Perform read-only verification only.\n"
        "3. Verify the final state for identity-level items the execution report claims were changed or inspected.\n"
        "4. For role assignments, verify using user role read tools where possible.\n"
        "5. For groups, verify using user group read tools where possible.\n"
        "6. For created users, verify using user search/read tools where possible.\n"
        "7. Return a final Markdown report with sections: Verified, Not Verified, Skipped, Errors."
    )


def _platform_verification_goal(fixed_profile: str, environment_label: str) -> str:
    return (
        f"You are a read-only Keycloak platform verification agent for the fixed '{fixed_profile}' profile ({environment_label}).\n\n"
        "Execution plan JSON:\n{build_execution_plan_output}\n\n"
        "Platform execution report:\n{execute_platform_actions_output}\n\n"
        "Rules:\n"
        f"1. Use ONLY attached Keycloak MCP tools and ALWAYS pass profile='{fixed_profile}'.\n"
        "2. Perform read-only verification only.\n"
        "3. Verify created clients, client roles, realm roles, groups, protocol mappers, and service-account role assignments where possible.\n"
        "4. For protocol mappers, verify using protocol mapper list tools.\n"
        "5. For clients and client roles, verify using client list/read tools.\n"
        "6. For groups, verify using group list/read tools.\n"
        "7. Return a final Markdown report with sections: Verified, Not Verified, Skipped, Errors."
    )


def ensure_keycloak_mcp_server(user) -> MCPServerPool:
    server, _ = MCPServerPool.objects.update_or_create(
        owner=user,
        name=KEYCLOAK_MCP_NAME,
        defaults={
            "description": (
                "URL-based Keycloak admin MCP for user, role, client, and group provisioning. "
                "Recommended to run as docker-compose service mcp-keycloak."
            ),
            "transport": MCPServerPool.TRANSPORT_SSE,
            "command": "",
            "args": [],
            "env": {},
            "url": KEYCLOAK_MCP_URL,
            "is_shared": False,
        },
    )
    return server


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


def ensure_keycloak_pipeline(user, mcp_server: MCPServerPool) -> Pipeline:
    pipeline, _ = Pipeline.objects.update_or_create(
        owner=user,
        name=KEYCLOAK_PIPELINE_NAME,
        defaults={
            "description": KEYCLOAK_PIPELINE_DESCRIPTION,
            "icon": "KEY",
            "tags": ["mcp", "keycloak", "iam", "approval", "provisioning", "studio"],
            "nodes": build_keycloak_nodes(mcp_server.id),
            "edges": build_keycloak_edges(),
            "graph_version": CURRENT_PIPELINE_GRAPH_VERSION,
            "is_shared": False,
        },
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline


def build_keycloak_ops_nodes(mcp_server_id: int, *, fixed_profile: str, environment_label: str) -> list[dict]:
    return [
        {
            "id": "start_manual",
            "type": "trigger/manual",
            "position": {"x": 340, "y": 40},
            "data": {
                "label": f"Run {environment_label} Keycloak Task",
                "is_active": True,
                "description": (
                    "Universal manual Keycloak flow. Paste any free-form Keycloak request into the Run dialog, "
                    "and the pipeline will normalize, discover, plan, execute, and verify."
                ),
            },
        },
        {
            "id": "start_webhook",
            "type": "trigger/webhook",
            "position": {"x": 820, "y": 40},
            "data": {
                "label": f"Webhook {environment_label} Keycloak Task",
                "is_active": True,
                "webhook_payload_map": TASK_WEBHOOK_CONTEXT_MAP,
            },
        },
        {
            "id": "entry_join",
            "type": "logic/merge",
            "position": {"x": 580, "y": 110},
            "data": {
                "label": "Selected Trigger Entry",
                "mode": "any",
            },
        },
        {
            "id": "environment_preflight",
            "type": "agent/mcp_call",
            "position": {"x": 480, "y": 180},
            "data": {
                "label": "1. Environment Preflight",
                "mcp_server_id": mcp_server_id,
                "tool_name": "keycloak_current_environment",
                "arguments_text": _json_payload({"profile": fixed_profile}),
                "on_failure": "abort",
            },
        },
        {
            "id": "normalize_request",
            "type": "agent/llm_query",
            "position": {"x": 480, "y": 360},
            "data": {
                "label": "2. Normalize Request",
                "provider": "openai",
                "model": "gpt-5-mini",
                "system_prompt": (
                    "You are a careful Keycloak operations planner. "
                    "Turn broad free-form Keycloak requests into strict execution briefs without inventing missing values."
                ),
                "prompt": _normalize_prompt(fixed_profile, environment_label),
                "include_all_outputs": False,
                "on_failure": "abort",
            },
        },
        {
            "id": "discovery_split",
            "type": "logic/parallel",
            "position": {"x": 480, "y": 470},
            "data": {
                "label": "Discovery Fan-Out",
            },
        },
        {
            "id": "discover_clients_roles",
            "type": "agent/react",
            "position": {"x": 100, "y": 580},
            "data": {
                "label": "3. Discover Clients & Client Roles",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 24,
                "allowed_tools": KEYCLOAK_CLIENT_DISCOVERY_TOOLS,
                "system_prompt": (
                    "You are a cautious Keycloak client discovery agent. "
                    "Prefer read-only checks, deterministic reasoning, and structured outputs."
                ),
                "goal": _discovery_clients_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "discover_users",
            "type": "agent/react",
            "position": {"x": 360, "y": 580},
            "data": {
                "label": "4. Discover Users",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 24,
                "allowed_tools": KEYCLOAK_USER_DISCOVERY_TOOLS,
                "system_prompt": (
                    "You are a cautious Keycloak user discovery agent. "
                    "Prefer read-only checks, deterministic reasoning, and structured outputs."
                ),
                "goal": _discovery_users_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "discover_groups_roles",
            "type": "agent/react",
            "position": {"x": 620, "y": 580},
            "data": {
                "label": "5. Discover Groups & Realm Roles",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 24,
                "allowed_tools": KEYCLOAK_GROUP_ROLE_DISCOVERY_TOOLS,
                "system_prompt": (
                    "You are a cautious Keycloak group and realm-role discovery agent. "
                    "Prefer read-only checks, deterministic reasoning, and structured outputs."
                ),
                "goal": _discovery_groups_roles_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "discover_protocol_mappers",
            "type": "agent/react",
            "position": {"x": 880, "y": 580},
            "data": {
                "label": "6. Discover Protocol Mappers",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 24,
                "allowed_tools": KEYCLOAK_PROTOCOL_MAPPER_DISCOVERY_TOOLS,
                "system_prompt": (
                    "You are a cautious Keycloak protocol-mapper discovery agent. "
                    "Prefer read-only checks, deterministic reasoning, and structured outputs."
                ),
                "goal": _discovery_protocol_mappers_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "discoveries_ready",
            "type": "logic/merge",
            "position": {"x": 480, "y": 720},
            "data": {
                "label": "Discoveries Ready",
                "mode": "all",
            },
        },
        {
            "id": "build_execution_plan",
            "type": "agent/llm_query",
            "position": {"x": 480, "y": 840},
            "data": {
                "label": "7. Build Safe Execution Plan",
                "provider": "openai",
                "model": "gpt-5-mini",
                "system_prompt": (
                    "You are a careful IAM planner. "
                    "Convert normalized and discovered Keycloak state into a safe execution plan."
                ),
                "prompt": _plan_prompt(fixed_profile, environment_label),
                "include_all_outputs": False,
                "on_failure": "abort",
            },
        },
        {
            "id": "execution_split",
            "type": "logic/parallel",
            "position": {"x": 480, "y": 960},
            "data": {
                "label": "Execution Fan-Out",
            },
        },
        {
            "id": "execute_identity_actions",
            "type": "agent/react",
            "position": {"x": 240, "y": 1080},
            "data": {
                "label": "8. Execute Identity Actions",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 60,
                "allowed_tools": KEYCLOAK_IDENTITY_EXECUTION_TOOLS,
                "system_prompt": (
                    "You are a Keycloak identity operator. Work only through attached MCP tools. "
                    "Be strict, deterministic, and stop instead of guessing."
                ),
                "goal": _identity_execution_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "execute_platform_actions",
            "type": "agent/react",
            "position": {"x": 720, "y": 1080},
            "data": {
                "label": "9. Execute Platform Actions",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 60,
                "allowed_tools": KEYCLOAK_PLATFORM_EXECUTION_TOOLS,
                "system_prompt": (
                    "You are a Keycloak platform operator. Work only through attached MCP tools. "
                    "Be strict, deterministic, and stop instead of guessing."
                ),
                "goal": _platform_execution_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "verify_identity_state",
            "type": "agent/react",
            "position": {"x": 240, "y": 1320},
            "data": {
                "label": "10. Verify Identity State",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 24,
                "allowed_tools": KEYCLOAK_IDENTITY_VERIFY_TOOLS,
                "system_prompt": (
                    "You are a read-only Keycloak identity verification agent. "
                    "Check the final state and do not mutate anything."
                ),
                "goal": _identity_verification_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "verify_platform_state",
            "type": "agent/react",
            "position": {"x": 720, "y": 1320},
            "data": {
                "label": "11. Verify Platform State",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 24,
                "allowed_tools": KEYCLOAK_PLATFORM_VERIFY_TOOLS,
                "system_prompt": (
                    "You are a read-only Keycloak platform verification agent. "
                    "Check the final state and do not mutate anything."
                ),
                "goal": _platform_verification_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "verification_merge",
            "type": "logic/merge",
            "position": {"x": 480, "y": 1460},
            "data": {
                "label": "Verification Ready",
                "mode": "all",
            },
        },
        {
            "id": "final_report",
            "type": "output/report",
            "position": {"x": 480, "y": 1580},
            "data": {
                "label": "12. Final Report",
                "template": (
                    f"# Keycloak {environment_label} Execution Report\n\n"
                    f"- fixed_profile: {fixed_profile}\n"
                    "- requester: {requester}\n"
                    "- task: {task}\n"
                    "- allow_existing_user: {allow_existing_user}\n\n"
                    "## Environment Preflight\n"
                    "{environment_preflight_output}\n\n"
                    "## Normalized Brief\n"
                    "{normalize_request_output}\n\n"
                    "## Discovery: Clients & Client Roles\n"
                    "- status: {discover_clients_roles_status}\n"
                    "- error: {discover_clients_roles_error}\n\n"
                    "{discover_clients_roles_output}\n\n"
                    "## Discovery: Users\n"
                    "- status: {discover_users_status}\n"
                    "- error: {discover_users_error}\n\n"
                    "{discover_users_output}\n\n"
                    "## Discovery: Groups & Realm Roles\n"
                    "- status: {discover_groups_roles_status}\n"
                    "- error: {discover_groups_roles_error}\n\n"
                    "{discover_groups_roles_output}\n\n"
                    "## Discovery: Protocol Mappers\n"
                    "- status: {discover_protocol_mappers_status}\n"
                    "- error: {discover_protocol_mappers_error}\n\n"
                    "{discover_protocol_mappers_output}\n\n"
                    "## Execution Plan\n"
                    "{build_execution_plan_output}\n\n"
                    "## Execution: Identity Actions\n"
                    "- status: {execute_identity_actions_status}\n"
                    "- error: {execute_identity_actions_error}\n\n"
                    "{execute_identity_actions_output}\n\n"
                    "## Execution: Platform Actions\n"
                    "- status: {execute_platform_actions_status}\n"
                    "- error: {execute_platform_actions_error}\n\n"
                    "{execute_platform_actions_output}\n\n"
                    "## Verification: Identity State\n"
                    "- status: {verify_identity_state_status}\n"
                    "- error: {verify_identity_state_error}\n\n"
                    "{verify_identity_state_output}\n\n"
                    "## Verification: Platform State\n"
                    "- status: {verify_platform_state_status}\n"
                    "- error: {verify_platform_state_error}\n\n"
                    "{verify_platform_state_output}\n"
                ),
            },
        },
    ]


def build_keycloak_ops_edges() -> list[dict]:
    return [
        {"id": "e1", "source": "start_manual", "target": "entry_join", "sourceHandle": "out", "animated": True},
        {"id": "e2", "source": "start_webhook", "target": "entry_join", "sourceHandle": "out", "animated": True},
        {"id": "e3", "source": "entry_join", "target": "environment_preflight", "sourceHandle": "out", "animated": True},
        {"id": "e4", "source": "environment_preflight", "target": "normalize_request", "sourceHandle": "success", "animated": True},
        {"id": "e5", "source": "normalize_request", "target": "discovery_split", "sourceHandle": "success", "animated": True},
        {"id": "e6", "source": "discovery_split", "target": "discover_clients_roles", "sourceHandle": "out", "animated": True},
        {"id": "e7", "source": "discovery_split", "target": "discover_users", "sourceHandle": "out", "animated": True},
        {"id": "e8", "source": "discovery_split", "target": "discover_groups_roles", "sourceHandle": "out", "animated": True},
        {"id": "e9", "source": "discover_clients_roles", "target": "discover_protocol_mappers", "sourceHandle": "success", "animated": True},
        {"id": "e10", "source": "discover_clients_roles", "target": "discoveries_ready", "sourceHandle": "success", "animated": True},
        {"id": "e11", "source": "discover_clients_roles", "target": "discoveries_ready", "sourceHandle": "error", "animated": True},
        {"id": "e12", "source": "discover_users", "target": "discoveries_ready", "sourceHandle": "success", "animated": True},
        {"id": "e13", "source": "discover_users", "target": "discoveries_ready", "sourceHandle": "error", "animated": True},
        {"id": "e14", "source": "discover_groups_roles", "target": "discoveries_ready", "sourceHandle": "success", "animated": True},
        {"id": "e15", "source": "discover_groups_roles", "target": "discoveries_ready", "sourceHandle": "error", "animated": True},
        {"id": "e16", "source": "discover_protocol_mappers", "target": "discoveries_ready", "sourceHandle": "success", "animated": True},
        {"id": "e17", "source": "discover_protocol_mappers", "target": "discoveries_ready", "sourceHandle": "error", "animated": True},
        {"id": "e18", "source": "discoveries_ready", "target": "build_execution_plan", "sourceHandle": "out", "animated": True},
        {"id": "e19", "source": "build_execution_plan", "target": "execution_split", "sourceHandle": "success", "animated": True},
        {"id": "e20", "source": "execution_split", "target": "execute_identity_actions", "sourceHandle": "out", "animated": True},
        {"id": "e21", "source": "execution_split", "target": "execute_platform_actions", "sourceHandle": "out", "animated": True},
        {"id": "e22", "source": "execute_identity_actions", "target": "verify_identity_state", "sourceHandle": "success", "animated": True},
        {"id": "e23", "source": "execute_platform_actions", "target": "verify_platform_state", "sourceHandle": "success", "animated": True},
        {"id": "e24", "source": "verify_identity_state", "target": "verification_merge", "sourceHandle": "success", "animated": True},
        {"id": "e25", "source": "verify_identity_state", "target": "verification_merge", "sourceHandle": "error", "animated": True},
        {"id": "e26", "source": "verify_platform_state", "target": "verification_merge", "sourceHandle": "success", "animated": True},
        {"id": "e27", "source": "verify_platform_state", "target": "verification_merge", "sourceHandle": "error", "animated": True},
        {"id": "e28", "source": "verification_merge", "target": "final_report", "sourceHandle": "out", "animated": True},
    ]


def ensure_keycloak_ops_pipeline(user, mcp_server: MCPServerPool, *, profile_name: str) -> Pipeline:
    spec = KEYCLOAK_OPS_PIPELINE_SPECS[profile_name]
    pipeline, _ = Pipeline.objects.update_or_create(
        owner=user,
        name=spec["name"],
        defaults={
            "description": spec["description"],
            "icon": "KEY",
            "tags": ["mcp", "keycloak", "iam", "direct", "studio", profile_name],
            "nodes": build_keycloak_ops_nodes(
                mcp_server.id,
                fixed_profile=profile_name,
                environment_label=spec["label"],
            ),
            "edges": build_keycloak_ops_edges(),
            "graph_version": CURRENT_PIPELINE_GRAPH_VERSION,
            "is_shared": False,
        },
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline


def ensure_keycloak_ops_pipelines(user, mcp_server: MCPServerPool) -> dict[str, Pipeline]:
    return {
        profile_name: ensure_keycloak_ops_pipeline(user, mcp_server, profile_name=profile_name)
        for profile_name in KEYCLOAK_OPS_PIPELINE_SPECS
    }
