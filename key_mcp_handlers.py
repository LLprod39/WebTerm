"""Non-role Keycloak MCP tool handlers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KeycloakHandlerContext:
    client_from_args: Callable[..., Any]
    clean_text: Callable[[Any], str]
    parse_bool: Callable[..., bool]
    resolve_config: Callable[[dict[str, Any]], Any]
    set_runtime_default: Callable[[Any], None]
    load_profiles: Callable[[], dict[str, Any]]
    current_environment_payload: Callable[[], dict[str, Any]]
    profile_public_summary: Callable[[str, dict[str, Any]], dict[str, Any]]
    tool_result: Callable[..., dict[str, Any]]
    user_summary: Callable[[dict[str, Any]], dict[str, Any]]
    client_summary: Callable[[dict[str, Any]], dict[str, Any]]
    group_summary: Callable[[dict[str, Any]], dict[str, Any]]
    protocol_mapper_summary: Callable[[dict[str, Any]], dict[str, Any]]
    max_search_results: int
    default_group_page_size: int
    tool_error: type[Exception]


def handle_configure(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    config = context.resolve_config(arguments)
    with context.client_from_args(arguments) as client:
        client.ping()
    context.set_runtime_default(config)
    payload = {
        "success": True,
        "message": "Keycloak runtime default configured successfully",
        "environment": config.safe_summary(),
        "notes": ["For shared HTTP deployment, prefer env defaults or pass profile explicitly on each call."],
    }
    return context.tool_result(payload)


def handle_use_profile(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    profile_name = context.clean_text(arguments.get("profile"))
    if not profile_name:
        raise context.tool_error("profile is required")
    args = {"profile": profile_name}
    config = context.resolve_config(args)
    with context.client_from_args(args) as client:
        client.ping()
    context.set_runtime_default(config)
    payload = {
        "success": True,
        "message": f"Profile '{profile_name}' is active for the current process",
        "environment": config.safe_summary(),
    }
    return context.tool_result(payload)


def handle_list_profiles(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    _ = arguments
    profiles_payload = context.load_profiles()
    profiles = profiles_payload.get("profiles", {})
    result = {
        "success": True,
        "default_profile": profiles_payload.get("default_profile"),
        "profiles": [
            context.profile_public_summary(name, profile)
            for name, profile in sorted(profiles.items())
            if isinstance(profile, dict)
        ],
    }
    return context.tool_result(result)


def handle_current_environment(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    _ = arguments
    return context.tool_result(context.current_environment_payload())


def handle_search_users(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    query = context.clean_text(arguments.get("query"))
    if not query:
        raise context.tool_error("query is required")
    exact = context.parse_bool(arguments.get("exact"), default=False)
    max_results = max(1, min(int(arguments.get("max_results") or context.max_search_results), context.max_search_results))
    with context.client_from_args(arguments) as client:
        users = client.search_users(query, exact=exact, max_results=max_results)
    payload = {"success": True, "count": len(users), "users": [context.user_summary(user) for user in users]}
    return context.tool_result(payload)


def handle_find_user(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    login = context.clean_text(arguments.get("login"))
    if not login:
        raise context.tool_error("login is required")
    with context.client_from_args(arguments) as client:
        candidates = client.search_user_candidates(login, max_candidates=5)
    if not candidates:
        return context.tool_result({"success": True, "found": False, "message": f"User '{login}' not found"})
    payload = {
        "success": True,
        "found": True,
        "user": context.user_summary(candidates[0]["user"]),
        "match": {"score": candidates[0]["score"], "reasons": candidates[0]["reasons"]},
        "candidates": [
            {"score": item["score"], "reasons": item["reasons"], "user": context.user_summary(item["user"])}
            for item in candidates
        ],
    }
    return context.tool_result(payload)


def handle_list_clients(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    search = context.clean_text(arguments.get("search"))
    max_results = max(1, min(int(arguments.get("max_results") or 50), 500))
    with context.client_from_args(arguments) as client:
        clients = client.list_clients(search=search, max_results=max_results)
    payload = {"success": True, "count": len(clients), "clients": [context.client_summary(item) for item in clients]}
    return context.tool_result(payload)


def handle_find_clients_with_role(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    role_name = context.clean_text(arguments.get("role_name"))
    if not role_name:
        raise context.tool_error("role_name is required")
    search = context.clean_text(arguments.get("search"))
    max_results = max(1, min(int(arguments.get("max_results") or 50), 500))
    with context.client_from_args(arguments) as client:
        clients = client.find_clients_with_role(role_name, search=search, max_results=max_results)
    payload = {
        "success": True,
        "role_name": role_name,
        "count": len(clients),
        "clients": [context.client_summary(item) for item in clients],
    }
    return context.tool_result(payload)


def handle_list_protocol_mappers(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    client_id = context.clean_text(arguments.get("client_id"))
    if not client_id:
        raise context.tool_error("client_id is required")
    with context.client_from_args(arguments, strip_target_client_id=True) as client:
        client_uuid = client.get_client_uuid(client_id)
        mappers = client.list_protocol_mappers(client_uuid)
    payload = {
        "success": True,
        "client_id": client_id,
        "client_uuid": client_uuid,
        "count": len(mappers),
        "protocol_mappers": [context.protocol_mapper_summary(item) for item in mappers],
    }
    return context.tool_result(payload)


def handle_create_user(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    username = context.clean_text(arguments.get("username"))
    email = context.clean_text(arguments.get("email"))
    if not username or not email:
        raise context.tool_error("username and email are required")
    first_name = context.clean_text(arguments.get("first_name"))
    last_name = context.clean_text(arguments.get("last_name"))
    enabled = context.parse_bool(arguments.get("enabled"), default=True)
    temporary_password = context.clean_text(arguments.get("temporary_password")) or None
    attributes = arguments.get("attributes")
    if attributes is not None and not isinstance(attributes, dict):
        raise context.tool_error("attributes must be an object")
    required_actions = arguments.get("required_actions") or []
    if not isinstance(required_actions, list):
        raise context.tool_error("required_actions must be an array")
    with context.client_from_args(arguments) as client:
        user_id = client.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            enabled=enabled,
            temporary_password=temporary_password,
            attributes=attributes,
            required_actions=[context.clean_text(item) for item in required_actions if context.clean_text(item)],
        )
    payload = {
        "success": True,
        "message": "User created successfully",
        "user": {"id": user_id, "username": username, "email": email, "enabled": enabled},
        "password_set": bool(temporary_password),
        "password_temporary": bool(temporary_password),
    }
    return context.tool_result(payload)


def handle_create_client(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    client_id = context.clean_text(arguments.get("client_id"))
    if not client_id:
        raise context.tool_error("client_id is required")
    name = context.clean_text(arguments.get("name")) or client_id
    description = context.clean_text(arguments.get("description"))
    service_accounts_enabled = context.parse_bool(arguments.get("service_accounts_enabled"), default=True)
    direct_access_grants_enabled = context.parse_bool(arguments.get("direct_access_grants_enabled"), default=True)
    standard_flow_enabled = context.parse_bool(arguments.get("standard_flow_enabled"), default=True)
    public_client = context.parse_bool(arguments.get("public_client"), default=False)
    with context.client_from_args(arguments, strip_target_client_id=True) as client:
        client_info = client.create_client(
            client_id=client_id,
            name=name,
            description=description,
            service_accounts_enabled=service_accounts_enabled,
            direct_access_grants_enabled=direct_access_grants_enabled,
            standard_flow_enabled=standard_flow_enabled,
            public_client=public_client,
        )
    payload = {"success": True, "message": "Client created successfully", "client": client_info}
    return context.tool_result(payload)


def handle_add_protocol_mapper(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    client_id = context.clean_text(arguments.get("client_id"))
    mapper_name = context.clean_text(arguments.get("mapper_name"))
    user_attribute = context.clean_text(arguments.get("user_attribute"))
    token_claim = context.clean_text(arguments.get("token_claim"))
    if not all([client_id, mapper_name, user_attribute, token_claim]):
        raise context.tool_error("client_id, mapper_name, user_attribute, and token_claim are required")
    add_to_id_token = context.parse_bool(arguments.get("add_to_id_token"), default=True)
    add_to_access_token = context.parse_bool(arguments.get("add_to_access_token"), default=True)
    with context.client_from_args(arguments, strip_target_client_id=True) as client:
        client_uuid = client.get_client_uuid(client_id)
        mapper = client.add_protocol_mapper(
            client_uuid=client_uuid,
            mapper_name=mapper_name,
            user_attribute=user_attribute,
            token_claim=token_claim,
            add_to_id_token=add_to_id_token,
            add_to_access_token=add_to_access_token,
        )
    payload = {
        "success": True,
        "message": "Protocol mapper added successfully",
        "client_id": client_id,
        "mapper": mapper,
    }
    return context.tool_result(payload)


def handle_list_groups(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    search = context.clean_text(arguments.get("search"))
    max_results = max(1, min(int(arguments.get("max_results") or context.default_group_page_size), 1000))
    with context.client_from_args(arguments) as client:
        groups = client.flatten_groups(client.list_groups(search=search, max_results=max_results))
    payload = {"success": True, "count": len(groups), "groups": [context.group_summary(group) for group in groups]}
    return context.tool_result(payload)


def handle_get_user_groups(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    login = context.clean_text(arguments.get("login"))
    user_id = context.clean_text(arguments.get("user_id")) or None
    allow_fuzzy = context.parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    with context.client_from_args(arguments) as client:
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        groups = client.get_user_groups(context.clean_text(user.get("id")))
    payload = {"success": True, "user": context.user_summary(user), "groups": [context.group_summary(group) for group in groups]}
    return context.tool_result(payload)


def handle_add_user_to_groups(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    groups = arguments.get("groups")
    if not isinstance(groups, list) or not groups:
        raise context.tool_error("groups must be a non-empty array")
    login = context.clean_text(arguments.get("login"))
    user_id = context.clean_text(arguments.get("user_id")) or None
    allow_fuzzy = context.parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    with context.client_from_args(arguments) as client:
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        current_groups = client.get_user_groups(context.clean_text(user.get("id")))
        current_group_ids = {context.clean_text(group.get("id")) for group in current_groups}
        added: list[dict[str, Any]] = []
        already_member: list[dict[str, Any]] = []
        for group_name in groups:
            group = client.resolve_group(context.clean_text(group_name))
            group_id = context.clean_text(group.get("id"))
            if group_id in current_group_ids:
                already_member.append(context.group_summary(group))
                continue
            client.add_user_to_group(context.clean_text(user.get("id")), group_id)
            added.append(context.group_summary(group))
    payload = {"success": True, "user": context.user_summary(user), "groups_added": added, "groups_already_assigned": already_member}
    return context.tool_result(payload)


def handle_create_group(arguments: dict[str, Any], *, context: KeycloakHandlerContext) -> dict[str, Any]:
    group_name = context.clean_text(arguments.get("group_name"))
    if not group_name:
        raise context.tool_error("group_name is required")
    parent_group = context.clean_text(arguments.get("parent_group"))
    with context.client_from_args(arguments) as client:
        group = client.create_group(group_name, parent_group=parent_group)
    payload = {"success": True, "message": "Group created successfully", "group": group}
    return context.tool_result(payload)
