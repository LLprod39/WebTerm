"""Role-management tool handlers for the Keycloak MCP server."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RoleHandlerContext:
    client_from_args: Callable[..., Any]
    clean_text: Callable[[Any], str]
    parse_bool: Callable[..., bool]
    tool_result: Callable[..., dict[str, Any]]
    user_summary: Callable[[dict[str, Any]], dict[str, Any]]
    tool_error: type[Exception]


def _parse_roles_table(text: str) -> dict[str, list[str]]:
    roles_by_client: dict[str, list[str]] = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or "---" in line or "Клиент" in line or "Client" in line:
            continue
        if not line.startswith("|"):
            continue
        parts = [item.strip() for item in line.split("|")[1:-1]]
        if len(parts) < 2:
            continue
        client_id, role_name = parts[0], parts[1]
        if not client_id or not role_name:
            continue
        roles_by_client.setdefault(client_id, []).append(role_name)
    return roles_by_client


def _select_client_roles(
    role_map: dict[str, dict[str, Any]],
    current_roles: list[dict[str, Any]],
    requested_names: list[str],
    *,
    clean_text: Callable[[Any], str],
):
    current_role_names = {clean_text(role.get("name")) for role in current_roles}
    roles_to_add: list[dict[str, Any]] = []
    already_has: list[str] = []
    not_found: list[str] = []
    for role_name in requested_names:
        name = clean_text(role_name)
        if not name:
            continue
        if name in current_role_names:
            already_has.append(name)
        elif name in role_map:
            roles_to_add.append(role_map[name])
        else:
            not_found.append(name)
    return roles_to_add, already_has, not_found


def handle_list_client_roles(arguments: dict[str, Any], *, context: RoleHandlerContext) -> dict[str, Any]:
    clean_text = context.clean_text
    client_id = clean_text(arguments.get("client_id"))
    with context.client_from_args(arguments, strip_target_client_id=True) as client:
        resolved_client_id = client_id or client.config.client_id
        client_uuid = client.get_client_uuid(client_id or None)
        role_map = client.get_client_roles(client_uuid)
    payload = {
        "success": True,
        "client_id": resolved_client_id,
        "client_uuid": client_uuid,
        "count": len(role_map),
        "roles": sorted(role_map),
    }
    return context.tool_result(payload)


def handle_assign_roles(arguments: dict[str, Any], *, context: RoleHandlerContext) -> dict[str, Any]:
    clean_text = context.clean_text
    roles = arguments.get("roles")
    if not isinstance(roles, list) or not roles:
        raise context.tool_error("roles must be a non-empty array")
    login = clean_text(arguments.get("login"))
    user_id = clean_text(arguments.get("user_id")) or None
    allow_fuzzy = context.parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    client_id = clean_text(arguments.get("client_id"))
    with context.client_from_args(arguments, strip_target_client_id=True) as client:
        resolved_client_id = client_id or client.config.client_id
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        client_uuid = client.get_client_uuid(client_id or None)
        role_map = client.get_client_roles(client_uuid)
        current_roles = client.get_user_client_roles(clean_text(user.get("id")), client_uuid)
        roles_to_add, already_has, not_found = _select_client_roles(role_map, current_roles, list(roles), clean_text=clean_text)
        if roles_to_add:
            client.assign_client_roles(clean_text(user.get("id")), client_uuid, roles_to_add)
    payload = {
        "success": True,
        "user": context.user_summary(user),
        "client_id": resolved_client_id,
        "roles_added": [clean_text(role.get("name")) for role in roles_to_add],
        "roles_already_assigned": already_has,
        "roles_not_found": not_found,
    }
    return context.tool_result(payload)


def handle_get_user_roles(arguments: dict[str, Any], *, context: RoleHandlerContext) -> dict[str, Any]:
    clean_text = context.clean_text
    login = clean_text(arguments.get("login"))
    user_id = clean_text(arguments.get("user_id")) or None
    client_id = clean_text(arguments.get("client_id"))
    allow_fuzzy = context.parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    with context.client_from_args(arguments, strip_target_client_id=True) as client:
        resolved_client_id = client_id or client.config.client_id
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        client_uuid = client.get_client_uuid(client_id or None)
        roles = client.get_user_client_roles(clean_text(user.get("id")), client_uuid)
    payload = {
        "success": True,
        "user": context.user_summary(user),
        "client_id": resolved_client_id,
        "roles": sorted(clean_text(role.get("name")) for role in roles if clean_text(role.get("name"))),
    }
    return context.tool_result(payload)


def handle_bulk_assign_roles(arguments: dict[str, Any], *, context: RoleHandlerContext) -> dict[str, Any]:
    clean_text = context.clean_text
    users = arguments.get("users")
    if not isinstance(users, list) or not users:
        raise context.tool_error("users must be a non-empty array")
    client_id = clean_text(arguments.get("client_id"))
    results = {"assigned": [], "errors": [], "skipped": []}
    with context.client_from_args(arguments, strip_target_client_id=True) as client:
        resolved_client_id = client_id or client.config.client_id
        client_uuid = client.get_client_uuid(client_id or None)
        role_map = client.get_client_roles(client_uuid)
        for item in users:
            if not isinstance(item, dict):
                results["errors"].append({"item": item, "error": "user entry must be an object"})
                continue
            login = clean_text(item.get("login"))
            user_id = clean_text(item.get("user_id")) or None
            role_names = item.get("roles")
            if not isinstance(role_names, list) or not role_names:
                results["errors"].append({"login": login or None, "user_id": user_id, "error": "roles must be a non-empty array"})
                continue
            try:
                user = client.resolve_user(
                    login=login,
                    user_id=user_id,
                    allow_fuzzy=context.parse_bool(item.get("allow_fuzzy_user_match"), default=False),
                )
                current_roles = client.get_user_client_roles(clean_text(user.get("id")), client_uuid)
                roles_to_add, already_has, not_found = _select_client_roles(role_map, current_roles, list(role_names), clean_text=clean_text)
                if roles_to_add:
                    client.assign_client_roles(clean_text(user.get("id")), client_uuid, roles_to_add)
                    results["assigned"].append(
                        {
                            "user": context.user_summary(user),
                            "roles_added": [clean_text(role.get("name")) for role in roles_to_add],
                            "roles_already_assigned": already_has,
                            "roles_not_found": not_found,
                        }
                    )
                else:
                    results["skipped"].append(
                        {
                            "user": context.user_summary(user),
                            "roles_already_assigned": already_has,
                            "roles_not_found": not_found,
                            "reason": "all_roles_already_assigned" if already_has else "no_valid_roles",
                        }
                    )
            except Exception as exc:
                results["errors"].append({"login": login or None, "user_id": user_id, "error": str(exc), "roles": role_names})
    payload = {
        "success": not results["errors"],
        "client_id": resolved_client_id,
        "total_processed": len(users),
        "assigned_count": len(results["assigned"]),
        "skipped_count": len(results["skipped"]),
        "error_count": len(results["errors"]),
        "details": results,
    }
    return context.tool_result(payload, is_error=bool(results["errors"]))


def handle_assign_roles_from_table(arguments: dict[str, Any], *, context: RoleHandlerContext) -> dict[str, Any]:
    clean_text = context.clean_text
    login = clean_text(arguments.get("login"))
    user_id = clean_text(arguments.get("user_id")) or None
    roles_table = clean_text(arguments.get("roles_table"))
    if not roles_table:
        raise context.tool_error("roles_table is required")
    roles_by_client = _parse_roles_table(roles_table)
    if not roles_by_client:
        raise context.tool_error("Could not parse roles table. Expected format: | Client | Role |")
    allow_fuzzy = context.parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    results = {"assigned": [], "errors": [], "skipped": []}
    with context.client_from_args(arguments) as client:
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        resolved_user_id = clean_text(user.get("id"))
        for client_key, role_names in roles_by_client.items():
            try:
                client_uuid = client.get_client_uuid(client_key)
                role_map = client.get_client_roles(client_uuid)
                current_roles = client.get_user_client_roles(resolved_user_id, client_uuid)
                roles_to_add, already_has, not_found = _select_client_roles(role_map, current_roles, role_names, clean_text=clean_text)
                if roles_to_add:
                    client.assign_client_roles(resolved_user_id, client_uuid, roles_to_add)
                    results["assigned"].append(
                        {
                            "client_id": client_key,
                            "roles_added": [clean_text(role.get("name")) for role in roles_to_add],
                            "roles_already_assigned": already_has,
                            "roles_not_found": not_found,
                        }
                    )
                else:
                    results["skipped"].append(
                        {
                            "client_id": client_key,
                            "roles_already_assigned": already_has,
                            "roles_not_found": not_found,
                            "reason": "all_roles_already_assigned" if already_has else "no_valid_roles",
                        }
                    )
            except Exception as exc:
                results["errors"].append({"client_id": client_key, "error": str(exc), "roles": role_names})
    payload = {
        "success": not results["errors"],
        "user": context.user_summary(user),
        "total_clients_processed": len(roles_by_client),
        "clients_with_changes": len(results["assigned"]),
        "clients_skipped": len(results["skipped"]),
        "clients_with_errors": len(results["errors"]),
        "details": results,
    }
    return context.tool_result(payload, is_error=bool(results["errors"]))


def handle_create_realm_role(arguments: dict[str, Any], *, context: RoleHandlerContext) -> dict[str, Any]:
    clean_text = context.clean_text
    role_name = clean_text(arguments.get("role_name"))
    if not role_name:
        raise context.tool_error("role_name is required")
    description = clean_text(arguments.get("description"))
    with context.client_from_args(arguments) as client:
        role = client.create_realm_role(role_name, description)
    payload = {"success": True, "message": "Realm role created successfully", "role": role}
    return context.tool_result(payload)


def handle_assign_realm_roles(arguments: dict[str, Any], *, context: RoleHandlerContext) -> dict[str, Any]:
    clean_text = context.clean_text
    roles = arguments.get("roles")
    if not isinstance(roles, list) or not roles:
        raise context.tool_error("roles must be a non-empty array")
    login = clean_text(arguments.get("login"))
    user_id = clean_text(arguments.get("user_id")) or None
    allow_fuzzy = context.parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    with context.client_from_args(arguments) as client:
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        role_map = client.get_realm_roles()
        current_roles = client.get_user_realm_roles(clean_text(user.get("id")))
        roles_to_add, already_has, not_found = _select_client_roles(role_map, current_roles, list(roles), clean_text=clean_text)
        if roles_to_add:
            client.assign_realm_roles(clean_text(user.get("id")), roles_to_add)
    payload = {
        "success": True,
        "user": context.user_summary(user),
        "roles_added": [clean_text(role.get("name")) for role in roles_to_add],
        "roles_already_assigned": already_has,
        "roles_not_found": not_found,
    }
    return context.tool_result(payload)


def handle_get_realm_roles(arguments: dict[str, Any], *, context: RoleHandlerContext) -> dict[str, Any]:
    with context.client_from_args(arguments) as client:
        role_map = client.get_realm_roles()
    payload = {
        "success": True,
        "count": len(role_map),
        "roles": [{"name": name, "description": role.get("description", "")} for name, role in sorted(role_map.items())],
    }
    return context.tool_result(payload)


def handle_get_user_realm_roles(arguments: dict[str, Any], *, context: RoleHandlerContext) -> dict[str, Any]:
    clean_text = context.clean_text
    login = clean_text(arguments.get("login"))
    user_id = clean_text(arguments.get("user_id")) or None
    allow_fuzzy = context.parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    with context.client_from_args(arguments) as client:
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        roles = client.get_user_realm_roles(clean_text(user.get("id")))
    payload = {
        "success": True,
        "user": context.user_summary(user),
        "roles": sorted(clean_text(role.get("name")) for role in roles if clean_text(role.get("name"))),
    }
    return context.tool_result(payload)


def handle_create_client_role(arguments: dict[str, Any], *, context: RoleHandlerContext) -> dict[str, Any]:
    clean_text = context.clean_text
    client_id = clean_text(arguments.get("client_id"))
    role_name = clean_text(arguments.get("role_name"))
    if not client_id or not role_name:
        raise context.tool_error("client_id and role_name are required")
    description = clean_text(arguments.get("description"))
    with context.client_from_args(arguments, strip_target_client_id=True) as client:
        client_uuid = client.get_client_uuid(client_id)
        role = client.create_client_role(client_uuid, role_name, description)
    payload = {"success": True, "message": "Client role created successfully", "client_id": client_id, "role": role}
    return context.tool_result(payload)


def handle_assign_service_account_roles(arguments: dict[str, Any], *, context: RoleHandlerContext) -> dict[str, Any]:
    clean_text = context.clean_text
    client_id = clean_text(arguments.get("client_id"))
    roles = arguments.get("roles")
    if not client_id or not isinstance(roles, list) or not roles:
        raise context.tool_error("client_id and roles are required")
    with context.client_from_args(arguments, strip_target_client_id=True) as client:
        client_uuid = client.get_client_uuid(client_id)
        service_account_user = client.get_client_service_account_user(client_uuid)
        role_map = client.get_client_roles(client_uuid)
        current_roles = client.get_user_client_roles(clean_text(service_account_user.get("id")), client_uuid)
        roles_to_add, already_has, not_found = _select_client_roles(role_map, current_roles, list(roles), clean_text=clean_text)
        if roles_to_add:
            client.assign_client_roles(clean_text(service_account_user.get("id")), client_uuid, roles_to_add)
    payload = {
        "success": True,
        "message": "Service account roles assigned successfully",
        "client_id": client_id,
        "service_account_user": context.user_summary(service_account_user),
        "roles_added": [clean_text(role.get("name")) for role in roles_to_add],
        "roles_already_assigned": already_has,
        "roles_not_found": not_found,
    }
    return context.tool_result(payload)
