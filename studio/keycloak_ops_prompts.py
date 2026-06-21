from __future__ import annotations


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
