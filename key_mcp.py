from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import key_mcp_config as _config
import key_mcp_handlers as _handlers
import key_mcp_roles as _roles
from key_mcp_client import KeycloakAdminClient
from key_mcp_client_support import (
    ALLOW_INSECURE_HTTP,
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USER,
    DEFAULT_CLIENT_ID,
    DEFAULT_CLIENT_SECRET,
    DEFAULT_GROUP_PAGE_SIZE,
    DEFAULT_KEYCLOAK_URL,
    DEFAULT_PROFILE,
    DEFAULT_REALM,
    DEFAULT_TOKEN_REALM,
    DEFAULT_VERIFY_SSL,
    LOGGER,
    MAX_SEARCH_RESULTS,
    PROFILE_FILE,
    ToolError,
)
from key_mcp_client_support import _dedupe_by_key as _dedupe_by_key  # noqa: F401
from key_mcp_client_support import _looks_like_uuid as _looks_like_uuid  # noqa: F401

KeycloakConfig = _config.KeycloakConfig
KeycloakConfigDefaults = _config.KeycloakConfigDefaults
_RUNTIME_DEFAULT = _config._RUNTIME_DEFAULT
_RUNTIME_DEFAULT_LOCK = _config._RUNTIME_DEFAULT_LOCK
_clean_text = _config.clean_text
_current_environment_payload_impl = _config.current_environment_payload
_first_non_empty = _config.first_non_empty
_get_runtime_default = _config.get_runtime_default
_load_profiles_impl = _config.load_profiles
_normalize_base_url_impl = _config.normalize_base_url
_parse_bool_impl = _config.parse_bool
_resolve_config_impl = _config.resolve_config
_resolve_profile_impl = _config.resolve_profile
_resolve_secret_impl = _config.resolve_secret
_resolve_value_impl = _config.resolve_value
_set_runtime_default = _config.set_runtime_default
KeycloakHandlerContext = _handlers.KeycloakHandlerContext
_handle_add_protocol_mapper_impl = _handlers.handle_add_protocol_mapper
_handle_add_user_to_groups_impl = _handlers.handle_add_user_to_groups
_handle_configure_impl = _handlers.handle_configure
_handle_create_client_impl = _handlers.handle_create_client
_handle_create_group_impl = _handlers.handle_create_group
_handle_create_user_impl = _handlers.handle_create_user
_handle_current_environment_impl = _handlers.handle_current_environment
_handle_find_clients_with_role_impl = _handlers.handle_find_clients_with_role
_handle_find_user_impl = _handlers.handle_find_user
_handle_get_user_groups_impl = _handlers.handle_get_user_groups
_handle_list_clients_impl = _handlers.handle_list_clients
_handle_list_groups_impl = _handlers.handle_list_groups
_handle_list_profiles_impl = _handlers.handle_list_profiles
_handle_list_protocol_mappers_impl = _handlers.handle_list_protocol_mappers
_handle_search_users_impl = _handlers.handle_search_users
_handle_use_profile_impl = _handlers.handle_use_profile
RoleHandlerContext = _roles.RoleHandlerContext
_parse_roles_table_impl = _roles._parse_roles_table
_select_client_roles_impl = _roles._select_client_roles
_handle_assign_realm_roles_impl = _roles.handle_assign_realm_roles
_handle_assign_roles_impl = _roles.handle_assign_roles
_handle_assign_roles_from_table_impl = _roles.handle_assign_roles_from_table
_handle_assign_service_account_roles_impl = _roles.handle_assign_service_account_roles
_handle_bulk_assign_roles_impl = _roles.handle_bulk_assign_roles
_handle_create_client_role_impl = _roles.handle_create_client_role
_handle_create_realm_role_impl = _roles.handle_create_realm_role
_handle_get_realm_roles_impl = _roles.handle_get_realm_roles
_handle_get_user_realm_roles_impl = _roles.handle_get_user_realm_roles
_handle_get_user_roles_impl = _roles.handle_get_user_roles
_handle_list_client_roles_impl = _roles.handle_list_client_roles
from key_mcp_protocol import (  # noqa: F401 - private compatibility exports
    _emit_stdio_payload,
    _error_payload,
    _json_text,
    _result_payload,
    _tool_result,
)
from key_mcp_server import (
    MCPServerRuntime,
)
from key_mcp_server import (
    _build_response as _build_response_impl,
)
from key_mcp_server import (
    _handle_stdio_request as _handle_stdio_request_impl,
)
from key_mcp_server import (
    create_mcp_request_handler as _create_mcp_request_handler,
)
from key_mcp_server import (
    run_http_server as _run_http_server_impl,
)
from key_mcp_server import (
    run_stdio_server as _run_stdio_server_impl,
)
from key_mcp_summaries import (  # noqa: F401 - private compatibility exports
    _client_summary,
    _group_summary,
    _protocol_mapper_summary,
    _user_summary,
)
from key_mcp_summaries import _profile_public_summary as _profile_public_summary_impl
from key_mcp_tools import (  # noqa: F401 - private compatibility exports
    PROFILE_PROPERTY,
    USER_REFERENCE_PROPERTIES,
    _tool,
    build_keycloak_tools,
)

MCP_PROTOCOL_VERSION = os.getenv("MCP_PROTOCOL_VERSION", "2025-06-18")
logging.basicConfig(level=logging.INFO)

TOOLS = build_keycloak_tools(
    default_keycloak_url=DEFAULT_KEYCLOAK_URL,
    default_realm=DEFAULT_REALM,
    default_token_realm=DEFAULT_TOKEN_REALM,
    default_client_id=DEFAULT_CLIENT_ID,
    default_verify_ssl=DEFAULT_VERIFY_SSL,
    max_search_results=MAX_SEARCH_RESULTS,
    default_group_page_size=DEFAULT_GROUP_PAGE_SIZE,
)


def _parse_bool(value: Any, *, default: bool | None = None) -> bool:
    return _parse_bool_impl(value, default=default, error_cls=ToolError)


def _normalize_base_url(raw_url: str) -> str:
    return _normalize_base_url_impl(raw_url, allow_insecure_http=ALLOW_INSECURE_HTTP, error_cls=ToolError)


def _config_defaults() -> KeycloakConfigDefaults:
    return KeycloakConfigDefaults(
        default_keycloak_url=DEFAULT_KEYCLOAK_URL,
        default_realm=DEFAULT_REALM,
        default_token_realm=DEFAULT_TOKEN_REALM,
        default_client_id=DEFAULT_CLIENT_ID,
        default_admin_user=DEFAULT_ADMIN_USER,
        default_admin_password=DEFAULT_ADMIN_PASSWORD,
        default_client_secret=DEFAULT_CLIENT_SECRET,
        default_profile=DEFAULT_PROFILE,
        default_verify_ssl=DEFAULT_VERIFY_SSL,
        allow_insecure_http=ALLOW_INSECURE_HTTP,
        profile_file=Path(PROFILE_FILE),
    )


def _load_profiles() -> dict[str, Any]:
    defaults = _config_defaults()
    return _load_profiles_impl(profile_file=defaults.profile_file, default_profile=defaults.default_profile, logger=LOGGER)


def _resolve_profile(profile_name: str | None) -> tuple[str, dict[str, Any]]:
    return _resolve_profile_impl(
        profile_name,
        load_profiles_func=_load_profiles,
        default_profile=DEFAULT_PROFILE,
        error_cls=ToolError,
    )


def _resolve_secret(
    *,
    explicit_value: Any,
    explicit_env_name: Any,
    profile: dict[str, Any],
    runtime_value: Any,
    default_value: str,
    legacy_field: str,
    env_field: str,
) -> str:
    return _resolve_secret_impl(
        explicit_value=explicit_value,
        explicit_env_name=explicit_env_name,
        profile=profile,
        runtime_value=runtime_value,
        default_value=default_value,
        legacy_field=legacy_field,
        env_field=env_field,
        logger=LOGGER,
        error_cls=ToolError,
    )


def _resolve_value(
    *,
    explicit_value: Any,
    explicit_env_name: Any,
    profile_values: Iterable[Any],
    profile_env_names: Iterable[Any],
    runtime_value: Any,
    default_value: Any,
    label: str,
) -> str:
    return _resolve_value_impl(
        explicit_value=explicit_value,
        explicit_env_name=explicit_env_name,
        profile_values=profile_values,
        profile_env_names=profile_env_names,
        runtime_value=runtime_value,
        default_value=default_value,
        label=label,
        error_cls=ToolError,
    )


def _current_environment_payload() -> dict[str, Any]:
    return _current_environment_payload_impl(
        defaults=_config_defaults(),
        get_runtime_default_func=_get_runtime_default,
        load_profiles_func=_load_profiles,
    )


def _resolve_config(arguments: dict[str, Any] | None = None) -> KeycloakConfig:
    return _resolve_config_impl(
        arguments,
        defaults=_config_defaults(),
        get_runtime_default_func=_get_runtime_default,
        resolve_profile_func=_resolve_profile,
        resolve_value_func=_resolve_value,
        resolve_secret_func=_resolve_secret,
        parse_bool_func=_parse_bool,
        normalize_base_url_func=_normalize_base_url,
        error_cls=ToolError,
    )


def _profile_public_summary(profile_name: str, profile: dict[str, Any]) -> dict[str, Any]:
    return _profile_public_summary_impl(profile_name, profile, default_verify_ssl=DEFAULT_VERIFY_SSL)


@contextmanager
def _client_from_args(arguments: dict[str, Any], *, strip_target_client_id: bool = False):
    resolved_arguments = dict(arguments)
    if strip_target_client_id:
        resolved_arguments.pop("client_id", None)
        resolved_arguments.pop("client_id_env", None)
    client = KeycloakAdminClient(_resolve_config(resolved_arguments))
    try:
        yield client
    finally:
        client.close()


def _parse_roles_table(text: str) -> dict[str, list[str]]:
    return _parse_roles_table_impl(text)


def _select_client_roles(role_map: dict[str, dict[str, Any]], current_roles: list[dict[str, Any]], requested_names: list[str]):
    return _select_client_roles_impl(role_map, current_roles, requested_names, clean_text=_clean_text)


def _role_handler_context() -> RoleHandlerContext:
    return RoleHandlerContext(
        client_from_args=_client_from_args,
        clean_text=_clean_text,
        parse_bool=_parse_bool,
        tool_result=_tool_result,
        user_summary=_user_summary,
        tool_error=ToolError,
    )



def _handler_context() -> KeycloakHandlerContext:
    return KeycloakHandlerContext(
        client_from_args=_client_from_args,
        clean_text=_clean_text,
        parse_bool=_parse_bool,
        resolve_config=_resolve_config,
        set_runtime_default=_set_runtime_default,
        load_profiles=_load_profiles,
        current_environment_payload=_current_environment_payload,
        profile_public_summary=_profile_public_summary,
        tool_result=_tool_result,
        user_summary=_user_summary,
        client_summary=_client_summary,
        group_summary=_group_summary,
        protocol_mapper_summary=_protocol_mapper_summary,
        max_search_results=MAX_SEARCH_RESULTS,
        default_group_page_size=DEFAULT_GROUP_PAGE_SIZE,
        tool_error=ToolError,
    )


def handle_configure(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_configure_impl(arguments, context=_handler_context())


def handle_use_profile(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_use_profile_impl(arguments, context=_handler_context())


def handle_list_profiles(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_list_profiles_impl(arguments, context=_handler_context())


def handle_current_environment(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_current_environment_impl(arguments, context=_handler_context())


def handle_search_users(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_search_users_impl(arguments, context=_handler_context())


def handle_find_user(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_find_user_impl(arguments, context=_handler_context())


def handle_list_clients(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_list_clients_impl(arguments, context=_handler_context())


def handle_find_clients_with_role(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_find_clients_with_role_impl(arguments, context=_handler_context())


def handle_list_protocol_mappers(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_list_protocol_mappers_impl(arguments, context=_handler_context())


def handle_create_user(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_create_user_impl(arguments, context=_handler_context())


def handle_list_client_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_list_client_roles_impl(arguments, context=_role_handler_context())


def handle_assign_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_assign_roles_impl(arguments, context=_role_handler_context())


def handle_get_user_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_get_user_roles_impl(arguments, context=_role_handler_context())


def handle_bulk_assign_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_bulk_assign_roles_impl(arguments, context=_role_handler_context())


def handle_assign_roles_from_table(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_assign_roles_from_table_impl(arguments, context=_role_handler_context())


def handle_create_realm_role(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_create_realm_role_impl(arguments, context=_role_handler_context())


def handle_assign_realm_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_assign_realm_roles_impl(arguments, context=_role_handler_context())


def handle_get_realm_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_get_realm_roles_impl(arguments, context=_role_handler_context())


def handle_get_user_realm_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_get_user_realm_roles_impl(arguments, context=_role_handler_context())


def handle_create_client_role(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_create_client_role_impl(arguments, context=_role_handler_context())


def handle_create_client(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_create_client_impl(arguments, context=_handler_context())


def handle_add_protocol_mapper(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_add_protocol_mapper_impl(arguments, context=_handler_context())


def handle_assign_service_account_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_assign_service_account_roles_impl(arguments, context=_role_handler_context())


def handle_list_groups(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_list_groups_impl(arguments, context=_handler_context())


def handle_get_user_groups(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_get_user_groups_impl(arguments, context=_handler_context())


def handle_add_user_to_groups(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_add_user_to_groups_impl(arguments, context=_handler_context())


def handle_create_group(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_create_group_impl(arguments, context=_handler_context())


TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "keycloak_configure": handle_configure,
    "keycloak_use_profile": handle_use_profile,
    "keycloak_list_profiles": handle_list_profiles,
    "keycloak_current_environment": handle_current_environment,
    "keycloak_list_clients": handle_list_clients,
    "keycloak_find_clients_with_role": handle_find_clients_with_role,
    "keycloak_list_protocol_mappers": handle_list_protocol_mappers,
    "keycloak_search_users": handle_search_users,
    "keycloak_find_user": handle_find_user,
    "keycloak_create_user": handle_create_user,
    "keycloak_list_client_roles": handle_list_client_roles,
    "keycloak_assign_roles": handle_assign_roles,
    "keycloak_get_user_roles": handle_get_user_roles,
    "keycloak_bulk_assign_roles": handle_bulk_assign_roles,
    "keycloak_assign_roles_from_table": handle_assign_roles_from_table,
    "keycloak_create_realm_role": handle_create_realm_role,
    "keycloak_get_realm_roles": handle_get_realm_roles,
    "keycloak_assign_realm_roles": handle_assign_realm_roles,
    "keycloak_get_user_realm_roles": handle_get_user_realm_roles,
    "keycloak_create_client_role": handle_create_client_role,
    "keycloak_create_client": handle_create_client,
    "keycloak_add_protocol_mapper": handle_add_protocol_mapper,
    "keycloak_assign_service_account_roles": handle_assign_service_account_roles,
    "keycloak_list_groups": handle_list_groups,
    "keycloak_get_user_groups": handle_get_user_groups,
    "keycloak_add_user_to_groups": handle_add_user_to_groups,
    "keycloak_create_group": handle_create_group,
}


def _server_runtime() -> MCPServerRuntime:
    return MCPServerRuntime(
        protocol_version=MCP_PROTOCOL_VERSION,
        tools=TOOLS,
        tool_handlers=TOOL_HANDLERS,
        clean_text=_clean_text,
        result_payload=_result_payload,
        error_payload=_error_payload,
        tool_result=_tool_result,
        tool_error=ToolError,
        logger=LOGGER,
    )


def _build_response(message: dict[str, Any]) -> dict[str, Any] | None:
    return _build_response_impl(message, runtime=_server_runtime())


def _handle_stdio_request(message: dict[str, Any]) -> None:
    _handle_stdio_request_impl(message, runtime=_server_runtime(), emit_stdio_payload=_emit_stdio_payload)


_MCPRequestHandler = _create_mcp_request_handler(_server_runtime)
_MCPRequestHandler.__module__ = __name__


def run_stdio_server() -> int:
    return _run_stdio_server_impl(runtime_provider=_server_runtime, emit_stdio_payload=_emit_stdio_payload)


def run_http_server(host: str, port: int) -> int:
    return _run_http_server_impl(host, port, request_handler_cls=_MCPRequestHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keycloak MCP server for Studio")
    parser.add_argument("--http", action="store_true", help="Run as HTTP JSON-RPC server")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8766, help="HTTP bind port")
    args = parser.parse_args(argv)
    if args.http:
        return run_http_server(args.host, args.port)
    return run_stdio_server()


if __name__ == "__main__":
    raise SystemExit(main())
