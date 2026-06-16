from __future__ import annotations

from typing import Any

PROFILE_PROPERTY = {
    "profile": {
        "type": "string",
        "description": "Optional profile name from config/keycloak_profiles.json. Safer than mutating process defaults on shared HTTP servers.",
    }
}
USER_REFERENCE_PROPERTIES = {
    "login": {"type": "string", "description": "Username or email. For write operations exact match is required by default."},
    "user_id": {"type": "string", "description": "Exact Keycloak user UUID. Preferred for write operations."},
    "allow_fuzzy_user_match": {
        "type": "boolean",
        "description": "Allow fuzzy login match. Use only after verifying the target user explicitly.",
    },
}


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def build_keycloak_tools(
    *,
    default_keycloak_url: str,
    default_realm: str,
    default_token_realm: str,
    default_client_id: str,
    default_verify_ssl: bool,
    max_search_results: int,
    default_group_page_size: int,
) -> list[dict[str, Any]]:
    return [
        _tool(
            "keycloak_configure",
            "Validate Keycloak connection settings and store them as the current process default. Prefer env defaults or profiles for shared HTTP deployment.",
            {
                "base_url": {"type": "string", "description": f"Keycloak base URL or host. Default: {default_keycloak_url or '(not set)'}"},
                "host": {"type": "string", "description": "Legacy alias for base_url."},
                "base_url_env": {"type": "string", "description": "Environment variable that contains Keycloak base_url"},
                "host_env": {"type": "string", "description": "Legacy alias for base_url_env."},
                "realm": {"type": "string", "description": f"Target realm. Default: {default_realm or '(not set)'}"},
                "realm_env": {"type": "string", "description": "Environment variable that contains target realm"},
                "token_realm": {"type": "string", "description": f"Realm used for token grant. Default: {default_token_realm or default_realm or '(not set)'}"},
                "token_realm_env": {"type": "string", "description": "Environment variable that contains token realm"},
                "client_id": {"type": "string", "description": f"Admin client_id. Default: {default_client_id}"},
                "client_id_env": {"type": "string", "description": "Environment variable that contains admin client_id"},
                "admin_user": {"type": "string", "description": "Keycloak admin username"},
                "admin_user_env": {"type": "string", "description": "Environment variable that contains Keycloak admin username"},
                "admin_password": {"type": "string", "description": "Keycloak admin password"},
                "admin_password_env": {"type": "string", "description": "Environment variable that contains Keycloak admin password"},
                "client_secret": {"type": "string", "description": "Optional client secret for confidential admin client"},
                "client_secret_env": {"type": "string", "description": "Environment variable that contains the client secret"},
                "verify_ssl": {"type": "boolean", "description": f"Verify TLS certificate. Default: {default_verify_ssl}"},
                "verify_ssl_env": {"type": "string", "description": "Environment variable that contains verify_ssl flag"},
                "profile": PROFILE_PROPERTY["profile"],
            },
            ["admin_user"],
        ),
        _tool("keycloak_use_profile", "Validate a named profile and make it the current process default.", {"profile": {"type": "string", "description": "Profile name from config/keycloak_profiles.json"}}, ["profile"]),
        _tool("keycloak_list_profiles", "List available Keycloak profiles without exposing secrets.", {}, []),
        _tool("keycloak_current_environment", "Show runtime default and environment-level Keycloak configuration.", {}, []),
        _tool(
            "keycloak_list_clients",
            "List or search Keycloak clients in the current realm.",
            {
                "search": {"type": "string", "description": "Optional free-text search against clientId, name, or description"},
                "max_results": {"type": "integer", "description": "Maximum number of clients to return. Default: 50"},
                **PROFILE_PROPERTY,
            },
            [],
        ),
        _tool(
            "keycloak_find_clients_with_role",
            "Find clients that contain a specific client role, optionally limited by a search hint.",
            {
                "role_name": {"type": "string", "description": "Exact client role name to look for"},
                "search": {"type": "string", "description": "Optional client search hint"},
                "max_results": {"type": "integer", "description": "Maximum number of candidate clients to inspect. Default: 50"},
                **PROFILE_PROPERTY,
            },
            ["role_name"],
        ),
        _tool(
            "keycloak_list_protocol_mappers",
            "List protocol mappers configured on a client.",
            {
                "client_id": {"type": "string", "description": "Target client_id"},
                **PROFILE_PROPERTY,
            },
            ["client_id"],
        ),
        _tool(
            "keycloak_search_users",
            "Search users in Keycloak by username, email, or free text.",
            {
                "query": {"type": "string", "description": "Search text"},
                "exact": {"type": "boolean", "description": "Prefer exact Keycloak search"},
                "max_results": {"type": "integer", "description": f"Maximum number of users. Default: {max_search_results}"},
                **PROFILE_PROPERTY,
            },
            ["query"],
        ),
        _tool("keycloak_find_user", "Find the best matching Keycloak user and return ranked candidates for verification.", {"login": {"type": "string", "description": "Username, email, or partial login"}, **PROFILE_PROPERTY}, ["login"]),
        _tool(
            "keycloak_create_user",
            "Create a Keycloak user. Returns the created user id.",
            {
                "username": {"type": "string", "description": "Login / username"},
                "email": {"type": "string", "description": "Email"},
                "first_name": {"type": "string", "description": "First name"},
                "last_name": {"type": "string", "description": "Last name"},
                "enabled": {"type": "boolean", "description": "Whether the user is enabled"},
                "temporary_password": {"type": "string", "description": "Temporary password to set after creation"},
                "attributes": {"type": "object", "description": "Optional Keycloak user attributes"},
                "required_actions": {"type": "array", "items": {"type": "string"}, "description": "Optional required actions such as UPDATE_PASSWORD"},
                **PROFILE_PROPERTY,
            },
            ["username", "email"],
        ),
        _tool("keycloak_list_client_roles", "List all roles for a client.", {"client_id": {"type": "string", "description": "Target client_id. Defaults to configured client."}, **PROFILE_PROPERTY}, []),
        _tool(
            "keycloak_assign_roles",
            "Assign client roles to a user. Exact user match is required unless allow_fuzzy_user_match=true.",
            {
                **USER_REFERENCE_PROPERTIES,
                "roles": {"type": "array", "items": {"type": "string"}, "description": "Client role names"},
                "client_id": {"type": "string", "description": "Target client_id. Defaults to configured client."},
                **PROFILE_PROPERTY,
            },
            ["roles"],
        ),
        _tool("keycloak_get_user_roles", "Get client roles assigned to a user.", {**USER_REFERENCE_PROPERTIES, "client_id": {"type": "string", "description": "Target client_id. Defaults to configured client."}, **PROFILE_PROPERTY}, []),
        _tool(
            "keycloak_bulk_assign_roles",
            "Bulk assign client roles to multiple users.",
            {
                "users": {
                    "type": "array",
                    "description": "List of users to update",
                    "items": {
                        "type": "object",
                        "properties": {
                            "login": {"type": "string"},
                            "user_id": {"type": "string"},
                            "allow_fuzzy_user_match": {"type": "boolean"},
                            "roles": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["roles"],
                        "additionalProperties": False,
                    },
                },
                "client_id": {"type": "string", "description": "Target client_id. Defaults to configured client."},
                **PROFILE_PROPERTY,
            },
            ["users"],
        ),
        _tool("keycloak_assign_roles_from_table", "Parse a markdown table '| Client | Role |' and assign listed roles to a user.", {**USER_REFERENCE_PROPERTIES, "roles_table": {"type": "string", "description": "Markdown table with client and role columns"}, **PROFILE_PROPERTY}, ["roles_table"]),
        _tool("keycloak_create_realm_role", "Create a realm role in the current realm.", {"role_name": {"type": "string", "description": "Realm role name"}, "description": {"type": "string", "description": "Optional role description"}, **PROFILE_PROPERTY}, ["role_name"]),
        _tool("keycloak_get_realm_roles", "List all realm roles.", PROFILE_PROPERTY, []),
        _tool("keycloak_assign_realm_roles", "Assign realm roles to a user.", {**USER_REFERENCE_PROPERTIES, "roles": {"type": "array", "items": {"type": "string"}, "description": "Realm role names"}, **PROFILE_PROPERTY}, ["roles"]),
        _tool("keycloak_get_user_realm_roles", "List realm roles assigned to a user.", {**USER_REFERENCE_PROPERTIES, **PROFILE_PROPERTY}, []),
        _tool("keycloak_create_client_role", "Create a client role.", {"client_id": {"type": "string", "description": "Target client_id"}, "role_name": {"type": "string", "description": "Role name"}, "description": {"type": "string", "description": "Optional role description"}, **PROFILE_PROPERTY}, ["client_id", "role_name"]),
        _tool("keycloak_create_client", "Create a Keycloak client with configurable service-account and grant flags.", {"client_id": {"type": "string", "description": "Unique client_id"}, "name": {"type": "string", "description": "Display name"}, "description": {"type": "string", "description": "Description"}, "service_accounts_enabled": {"type": "boolean", "description": "Enable service account"}, "direct_access_grants_enabled": {"type": "boolean", "description": "Enable password grant"}, "standard_flow_enabled": {"type": "boolean", "description": "Enable authorization code flow"}, "public_client": {"type": "boolean", "description": "Mark as public client"}, **PROFILE_PROPERTY}, ["client_id"]),
        _tool("keycloak_add_protocol_mapper", "Add an OIDC user-attribute protocol mapper to a client.", {"client_id": {"type": "string", "description": "Target client_id"}, "mapper_name": {"type": "string", "description": "Mapper name"}, "user_attribute": {"type": "string", "description": "Keycloak user attribute name"}, "token_claim": {"type": "string", "description": "Claim name in token"}, "add_to_id_token": {"type": "boolean", "description": "Expose in ID token"}, "add_to_access_token": {"type": "boolean", "description": "Expose in access token"}, **PROFILE_PROPERTY}, ["client_id", "mapper_name", "user_attribute", "token_claim"]),
        _tool("keycloak_assign_service_account_roles", "Assign client roles to a client's service account user.", {"client_id": {"type": "string", "description": "Target client_id"}, "roles": {"type": "array", "items": {"type": "string"}, "description": "Client role names"}, **PROFILE_PROPERTY}, ["client_id", "roles"]),
        _tool("keycloak_list_groups", "List groups and subgroup paths.", {"search": {"type": "string", "description": "Optional search term"}, "max_results": {"type": "integer", "description": f"Maximum number of groups. Default: {default_group_page_size}"}, **PROFILE_PROPERTY}, []),
        _tool("keycloak_get_user_groups", "List groups assigned to a user.", {**USER_REFERENCE_PROPERTIES, **PROFILE_PROPERTY}, []),
        _tool("keycloak_add_user_to_groups", "Add a user to one or more groups by exact id, name, or path.", {**USER_REFERENCE_PROPERTIES, "groups": {"type": "array", "items": {"type": "string"}, "description": "Group ids, names, or paths"}, **PROFILE_PROPERTY}, ["groups"]),
        _tool("keycloak_create_group", "Create a top-level group or subgroup.", {"group_name": {"type": "string", "description": "New group name"}, "parent_group": {"type": "string", "description": "Optional parent group id, name, or path"}, **PROFILE_PROPERTY}, ["group_name"]),
    ]
