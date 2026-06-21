from __future__ import annotations

import json
import os

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
