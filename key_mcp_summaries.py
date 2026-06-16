"""Public summary shaping helpers for Keycloak MCP payloads."""

from __future__ import annotations

from typing import Any


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def first_non_empty(*values: Any) -> str:
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return ""


def _profile_public_summary(
    profile_name: str,
    profile: dict[str, Any],
    *,
    default_verify_ssl: bool,
) -> dict[str, Any]:
    return {
        "name": profile_name,
        "display_name": clean_text(profile.get("name")) or profile_name,
        "base_url": first_non_empty(profile.get("base_url"), profile.get("host")) or None,
        "base_url_env": first_non_empty(profile.get("base_url_env"), profile.get("host_env")) or None,
        "realm": clean_text(profile.get("realm")) or None,
        "realm_env": clean_text(profile.get("realm_env")) or None,
        "token_realm": clean_text(profile.get("token_realm")) or None,
        "token_realm_env": clean_text(profile.get("token_realm_env")) or None,
        "client_id": clean_text(profile.get("client_id")) or None,
        "client_id_env": clean_text(profile.get("client_id_env")) or None,
        "admin_user": clean_text(profile.get("admin_user")) or None,
        "admin_user_env": clean_text(profile.get("admin_user_env")) or None,
        "uses_admin_password_env": bool(clean_text(profile.get("admin_password_env"))),
        "uses_client_secret_env": bool(clean_text(profile.get("client_secret_env"))),
        "uses_verify_ssl_env": bool(clean_text(profile.get("verify_ssl_env"))),
        "has_legacy_admin_password": bool(clean_text(profile.get("admin_password"))),
        "has_legacy_client_secret": bool(clean_text(profile.get("client_secret"))),
        "verify_ssl": profile.get("verify_ssl", default_verify_ssl),
    }


def _user_summary(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "email": user.get("email"),
        "firstName": user.get("firstName"),
        "lastName": user.get("lastName"),
        "enabled": user.get("enabled"),
    }


def _group_summary(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": group.get("id"),
        "name": group.get("name"),
        "path": group.get("path"),
        "subGroupCount": len(group.get("subGroups") or []),
    }


def _client_summary(client: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": client.get("id"),
        "clientId": client.get("clientId"),
        "name": client.get("name"),
        "description": client.get("description"),
        "enabled": client.get("enabled"),
        "protocol": client.get("protocol"),
        "publicClient": client.get("publicClient"),
    }


def _protocol_mapper_summary(mapper: dict[str, Any]) -> dict[str, Any]:
    config = mapper.get("config") if isinstance(mapper.get("config"), dict) else {}
    return {
        "id": mapper.get("id"),
        "name": mapper.get("name"),
        "protocol": mapper.get("protocol"),
        "protocolMapper": mapper.get("protocolMapper"),
        "userAttribute": config.get("user.attribute"),
        "tokenClaim": config.get("claim.name"),
        "addToIdToken": config.get("id.token.claim"),
        "addToAccessToken": config.get("access.token.claim"),
        "addToUserInfo": config.get("userinfo.token.claim"),
    }
