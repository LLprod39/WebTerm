from __future__ import annotations

import argparse
import logging
import os
import time
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import requests
from requests import Response, Session
from requests.exceptions import RequestException

from key_mcp_config import (
    KeycloakConfig,
    KeycloakConfigDefaults,
    _RUNTIME_DEFAULT,
    _RUNTIME_DEFAULT_LOCK,
    clean_text as _clean_text,
    current_environment_payload as _current_environment_payload_impl,
    first_non_empty as _first_non_empty,
    get_runtime_default as _get_runtime_default,
    load_profiles as _load_profiles_impl,
    normalize_base_url as _normalize_base_url_impl,
    parse_bool as _parse_bool_impl,
    resolve_config as _resolve_config_impl,
    resolve_profile as _resolve_profile_impl,
    resolve_secret as _resolve_secret_impl,
    resolve_value as _resolve_value_impl,
    set_runtime_default as _set_runtime_default,
)
from key_mcp_protocol import (  # noqa: F401 - private compatibility exports
    _emit_stdio_payload,
    _error_payload,
    _json_text,
    _result_payload,
    _tool_result,
)
from key_mcp_roles import (
    RoleHandlerContext,
    _parse_roles_table as _parse_roles_table_impl,
    _select_client_roles as _select_client_roles_impl,
    handle_assign_realm_roles as _handle_assign_realm_roles_impl,
    handle_assign_roles as _handle_assign_roles_impl,
    handle_assign_roles_from_table as _handle_assign_roles_from_table_impl,
    handle_assign_service_account_roles as _handle_assign_service_account_roles_impl,
    handle_bulk_assign_roles as _handle_bulk_assign_roles_impl,
    handle_create_client_role as _handle_create_client_role_impl,
    handle_create_realm_role as _handle_create_realm_role_impl,
    handle_get_realm_roles as _handle_get_realm_roles_impl,
    handle_get_user_realm_roles as _handle_get_user_realm_roles_impl,
    handle_get_user_roles as _handle_get_user_roles_impl,
    handle_list_client_roles as _handle_list_client_roles_impl,
)
from key_mcp_server import (
    MCPServerRuntime,
    _build_response as _build_response_impl,
    _handle_stdio_request as _handle_stdio_request_impl,
    create_mcp_request_handler as _create_mcp_request_handler,
    run_http_server as _run_http_server_impl,
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
DEFAULT_KEYCLOAK_URL = (os.getenv("KEYCLOAK_URL") or os.getenv("KEYCLOAK_HOST") or "").strip()
DEFAULT_REALM = os.getenv("KEYCLOAK_REALM", "").strip()
DEFAULT_TOKEN_REALM = os.getenv("KEYCLOAK_TOKEN_REALM", "").strip()
DEFAULT_CLIENT_ID = (os.getenv("KEYCLOAK_CLIENT_ID") or "admin-cli").strip() or "admin-cli"
DEFAULT_ADMIN_USER = os.getenv("KEYCLOAK_ADMIN_USER", "").strip()
DEFAULT_ADMIN_PASSWORD = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "").strip()
DEFAULT_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "").strip()
DEFAULT_PROFILE = os.getenv("KEYCLOAK_DEFAULT_PROFILE", "").strip()
DEFAULT_VERIFY_SSL = os.getenv("KEYCLOAK_VERIFY_SSL", "true").strip().lower() == "true"
ALLOW_INSECURE_HTTP = os.getenv("KEYCLOAK_ALLOW_INSECURE_HTTP", "false").strip().lower() == "true"
MAX_RETRIES = max(1, int(os.getenv("KEYCLOAK_MAX_RETRIES", "3")))
RETRY_DELAY_SECONDS = max(0.1, float(os.getenv("KEYCLOAK_RETRY_DELAY", "1.5")))
REQUEST_TIMEOUT_SECONDS = max(5, int(os.getenv("KEYCLOAK_REQUEST_TIMEOUT", "30")))
MAX_SEARCH_RESULTS = max(1, int(os.getenv("KEYCLOAK_MAX_SEARCH_RESULTS", "50")))
DEFAULT_GROUP_PAGE_SIZE = max(10, int(os.getenv("KEYCLOAK_GROUP_PAGE_SIZE", "200")))
PROFILE_FILE = Path(os.getenv("KEYCLOAK_PROFILES_FILE", str(Path(__file__).resolve().parent / "config" / "keycloak_profiles.json")))
EMAIL_DOMAIN_CANDIDATES = [
    item.strip() for item in os.getenv("KEYCLOAK_EMAIL_DOMAINS", "erg.kz,corp.erg.kz,mail.erg.kz").split(",") if item.strip()
]
HTTP_PROXIES = {
    key: value
    for key, value in {
        "http": os.getenv("HTTP_PROXY") or os.getenv("http_proxy"),
        "https": os.getenv("HTTPS_PROXY") or os.getenv("https_proxy"),
    }.items()
    if value
}
LOGGER = logging.getLogger("keycloak-mcp")
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


class ToolError(RuntimeError):
    pass


def _parse_bool(value: Any, *, default: bool | None = None) -> bool:
    return _parse_bool_impl(value, default=default, error_cls=ToolError)


def _looks_like_uuid(value: str) -> bool:
    raw = value.strip()
    return len(raw) == 36 and raw.count("-") == 4


def _normalize_base_url(raw_url: str) -> str:
    return _normalize_base_url_impl(raw_url, allow_insecure_http=ALLOW_INSECURE_HTTP, error_cls=ToolError)


def _dedupe_by_key(items: Iterable[dict[str, Any]], key: str = "id") -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        value = _clean_text(item.get(key))
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(item)
    return unique


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


class KeycloakAdminClient:
    def __init__(self, config: KeycloakConfig):
        self.config = config
        self.session: Session = requests.Session()
        if HTTP_PROXIES:
            self.session.proxies.update(HTTP_PROXIES)
        self._token = ""

    def close(self) -> None:
        self.session.close()

    def ping(self) -> None:
        self.search_users("__keycloak_mcp_ping__", exact=True, max_results=1)

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | list[dict[str, Any]] | None = None,
        allow_statuses: tuple[int, ...] = (200,),
    ) -> Response:
        if not self._token:
            self._token = self._get_token()
        retryable_token_refresh = True
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_body,
                    headers={"Authorization": f"Bearer {self._token}"},
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    verify=self.config.verify_ssl,
                )
            except RequestException as exc:
                last_error = exc
                if attempt == MAX_RETRIES:
                    raise ToolError(f"{method} {url} failed: {exc}") from exc
                time.sleep(RETRY_DELAY_SECONDS * attempt)
                continue

            if response.status_code == 401 and retryable_token_refresh:
                LOGGER.warning("Keycloak token expired, refreshing")
                self._token = self._get_token()
                retryable_token_refresh = False
                continue

            if response.status_code in allow_statuses:
                return response

            if response.status_code >= 500 and attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)
                continue

            raise self._http_error(method, url, response)

        raise ToolError(f"{method} {url} failed after {MAX_RETRIES} attempts: {last_error}")

    def _get_token(self) -> str:
        payload = {
            "grant_type": "password",
            "client_id": self.config.client_id,
            "username": self.config.admin_user,
            "password": self.config.admin_password,
        }
        if self.config.client_secret:
            payload["client_secret"] = self.config.client_secret

        try:
            response = self.session.post(
                self.config.token_url,
                data=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
                verify=self.config.verify_ssl,
            )
        except RequestException as exc:
            raise ToolError(f"Token request failed: {exc}") from exc

        if response.status_code != 200:
            raise self._http_error("POST", self.config.token_url, response)
        try:
            data = response.json()
        except ValueError as exc:
            raise ToolError("Keycloak token response is not valid JSON") from exc
        token = _clean_text(data.get("access_token"))
        if not token:
            raise ToolError("Keycloak token response does not contain access_token")
        return token

    def _http_error(self, method: str, url: str, response: Response) -> ToolError:
        message = ""
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            message = _first_non_empty(
                payload.get("error_description"),
                payload.get("errorMessage"),
                payload.get("message"),
                payload.get("error"),
            )
        if not message:
            message = response.text.strip()[:500]
        message = message or f"HTTP {response.status_code}"
        return ToolError(f"Keycloak {method} {url} returned {response.status_code}: {message}")

    def _get_json(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        response = self._request("GET", url, params=params, allow_statuses=(200,))
        if not response.content:
            return None
        return response.json()

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        allow_statuses: tuple[int, ...] = (200, 201, 204),
    ) -> Response:
        return self._request("POST", url, json_body=payload, allow_statuses=allow_statuses)

    def _put_json(self, url: str, payload: dict[str, Any], *, allow_statuses: tuple[int, ...] = (200, 204)) -> Response:
        return self._request("PUT", url, json_body=payload, allow_statuses=allow_statuses)

    def _put_empty(self, url: str) -> Response:
        return self._request("PUT", url, allow_statuses=(204,))

    def search_users(self, query: str, *, exact: bool = False, max_results: int = MAX_SEARCH_RESULTS) -> list[dict[str, Any]]:
        if exact:
            query_clean = _clean_text(query).lower()
            exact_matches: list[dict[str, Any]] = []
            exact_matches.extend(
                user
                for user in self._get_json(
                    f"{self.config.admin_base_url}/users",
                    params={"username": query, "exact": "true", "max": max(1, min(int(max_results), MAX_SEARCH_RESULTS))},
                )
                or []
                if isinstance(user, dict) and _clean_text(user.get("username")).lower() == query_clean
            )
            if "@" in query_clean:
                exact_matches.extend(
                    user
                    for user in self.search_users_by_email(query_clean)
                    if _clean_text(user.get("email")).lower() == query_clean
                )
            return _dedupe_by_key(exact_matches)

        params: dict[str, Any] = {
            "search": query,
            "max": max(1, min(int(max_results), MAX_SEARCH_RESULTS)),
        }
        if exact:
            params["exact"] = "true"
        users = self._get_json(f"{self.config.admin_base_url}/users", params=params)
        return [item for item in users if isinstance(item, dict)] if isinstance(users, list) else []

    def search_users_by_email(self, email: str) -> list[dict[str, Any]]:
        users = self._get_json(
            f"{self.config.admin_base_url}/users",
            params={"email": email, "exact": "true", "max": MAX_SEARCH_RESULTS},
        )
        return [item for item in users if isinstance(item, dict)] if isinstance(users, list) else []

    def get_user_by_id(self, user_id: str) -> dict[str, Any]:
        if not _looks_like_uuid(user_id):
            raise ToolError(f"Invalid Keycloak user_id: {user_id}")
        user = self._get_json(f"{self.config.admin_base_url}/users/{user_id}")
        if not isinstance(user, dict):
            raise ToolError(f"Keycloak user '{user_id}' was not found")
        return user

    def _email_variants(self, login: str) -> list[str]:
        login_clean = login.strip().lower()
        if "@" in login_clean:
            return [login_clean]
        return [f"{login_clean}@{domain}" for domain in EMAIL_DOMAIN_CANDIDATES]

    def _score_user_match(self, original_login: str, user: dict[str, Any]) -> tuple[int, list[str]]:
        original = original_login.lower()
        username = _clean_text(user.get("username")).lower()
        email = _clean_text(user.get("email")).lower()
        first_name = _clean_text(user.get("firstName")).lower()
        last_name = _clean_text(user.get("lastName")).lower()
        local_email = email.split("@", 1)[0] if email else ""
        score = 0
        reasons: list[str] = []

        if username == original:
            score += 140
            reasons.append("exact_username")
        if email == original:
            score += 130
            reasons.append("exact_email")
        if local_email == original:
            score += 110
            reasons.append("exact_email_local_part")
        if original in username and username != original:
            score += 55
            reasons.append("username_contains_query")
        if username and username in original and username != original:
            score += 30
            reasons.append("query_contains_username")

        parts = [item for item in original.replace(".", " ").replace("_", " ").split() if len(item) >= 3]
        for part in parts:
            if part in username:
                score += 25
                reasons.append(f"username_part:{part}")
            if part in first_name:
                score += 20
                reasons.append(f"first_name_part:{part}")
            if part in last_name:
                score += 20
                reasons.append(f"last_name_part:{part}")
            if part in email:
                score += 10
                reasons.append(f"email_part:{part}")

        return score, reasons

    def search_user_candidates(self, login: str, *, max_candidates: int = 5) -> list[dict[str, Any]]:
        login_clean = login.strip().lower()
        if not login_clean:
            return []

        raw_candidates: list[dict[str, Any]] = []
        raw_candidates.extend(self.search_users(login_clean, exact=True))
        for email in self._email_variants(login_clean):
            raw_candidates.extend(self.search_users_by_email(email))

        search_terms = {login_clean}
        search_terms.update(part for part in login_clean.replace(".", " ").replace("_", " ").split() if len(part) >= 3)
        for term in sorted(search_terms):
            raw_candidates.extend(self.search_users(term, exact=False))

        ranked: list[dict[str, Any]] = []
        for user in _dedupe_by_key(raw_candidates):
            score, reasons = self._score_user_match(login_clean, user)
            if score <= 0:
                continue
            ranked.append({"user": user, "score": score, "reasons": reasons})

        ranked.sort(key=lambda item: (-int(item["score"]), _clean_text(item["user"].get("username"))))
        return ranked[: max(1, max_candidates)]

    def find_user_advanced(self, login: str) -> dict[str, Any] | None:
        candidates = self.search_user_candidates(login, max_candidates=1)
        if not candidates:
            return None
        top = candidates[0]
        if int(top["score"]) < 40:
            return None
        return top["user"]

    def resolve_user(self, *, login: str | None = None, user_id: str | None = None, allow_fuzzy: bool = False) -> dict[str, Any]:
        if user_id:
            return self.get_user_by_id(user_id)

        login_clean = _clean_text(login)
        if not login_clean:
            raise ToolError("Either user_id or login is required")

        exact_matches: list[dict[str, Any]] = []
        exact_matches.extend(
            user
            for user in self.search_users(login_clean, exact=True)
            if _clean_text(user.get("username")).lower() == login_clean.lower()
        )
        for email in self._email_variants(login_clean):
            exact_matches.extend(
                user for user in self.search_users_by_email(email) if _clean_text(user.get("email")).lower() == email.lower()
            )

        exact_matches = _dedupe_by_key(exact_matches)
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            usernames = [_clean_text(item.get("username")) for item in exact_matches[:5]]
            raise ToolError(f"Ambiguous exact user match for '{login_clean}': {', '.join(usernames)}")

        if not allow_fuzzy:
            raise ToolError(
                f"Exact user match not found for '{login_clean}'. Use user_id or allow_fuzzy_user_match=true after verification."
            )

        candidates = self.search_user_candidates(login_clean, max_candidates=3)
        if not candidates:
            raise ToolError(f"User '{login_clean}' not found")

        top = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None
        if int(top["score"]) < 90:
            raise ToolError(f"Fuzzy match for '{login_clean}' is too weak. Verify the user first.")
        if second and int(second["score"]) >= int(top["score"]) - 5:
            raise ToolError(f"Fuzzy match for '{login_clean}' is ambiguous. Verify the user first.")
        return top["user"]

    def list_clients(self, *, search: str = "", max_results: int = 50) -> list[dict[str, Any]]:
        target = _clean_text(search).lower()
        limit = max(1, min(int(max_results), 500))
        page_size = 200
        scan_limit = 1000 if target else limit
        offset = 0
        collected: list[dict[str, Any]] = []

        while offset < scan_limit:
            batch_size = min(page_size, scan_limit - offset)
            batch = self._get_json(f"{self.config.admin_base_url}/clients", params={"first": offset, "max": batch_size})
            items = [item for item in batch if isinstance(item, dict)] if isinstance(batch, list) else []
            if not items:
                break
            collected.extend(items)
            if len(items) < batch_size:
                break
            offset += batch_size
            if not target and len(collected) >= limit:
                break

        clients = _dedupe_by_key(collected)
        if not target:
            clients.sort(key=lambda item: (_clean_text(item.get("clientId")), _clean_text(item.get("name"))))
            return clients[:limit]

        ranked: list[tuple[int, dict[str, Any]]] = []
        for client in clients:
            client_id = _clean_text(client.get("clientId")).lower()
            name = _clean_text(client.get("name")).lower()
            description = _clean_text(client.get("description")).lower()
            score = 0
            if client_id == target:
                score += 200
            if name == target:
                score += 160
            if target in client_id and client_id != target:
                score += 90
            if target in name and name != target:
                score += 70
            if target in description:
                score += 30
            normalized_target = target.replace("-", "").replace("_", "").replace(" ", "")
            normalized_client_id = client_id.replace("-", "").replace("_", "").replace(" ", "")
            if normalized_target and normalized_client_id == normalized_target:
                score += 120
            if score > 0:
                ranked.append((score, client))

        ranked.sort(key=lambda item: (-item[0], _clean_text(item[1].get("clientId"))))
        return [client for _, client in ranked[:limit]]

    def find_clients_with_role(self, role_name: str, *, search: str = "", max_results: int = 50) -> list[dict[str, Any]]:
        target_role = _clean_text(role_name)
        if not target_role:
            return []
        candidates = self.list_clients(search=search, max_results=max_results)
        matches: list[dict[str, Any]] = []
        for client in candidates:
            client_uuid = _clean_text(client.get("id"))
            client_id = _clean_text(client.get("clientId"))
            if not client_uuid or not client_id:
                continue
            role_map = self.get_client_roles(client_uuid)
            if target_role in role_map:
                matches.append(client)
        return matches

    def get_client_uuid(self, client_id: str | None = None) -> str:
        target_client_id = _clean_text(client_id) or self.config.client_id
        if not target_client_id:
            raise ToolError("client_id is required")
        clients = self._get_json(f"{self.config.admin_base_url}/clients", params={"clientId": target_client_id})
        items = [item for item in clients if isinstance(item, dict)] if isinstance(clients, list) else []
        matches = [item for item in items if _clean_text(item.get("clientId")) == target_client_id]
        if not matches:
            raise ToolError(f"Client '{target_client_id}' not found in realm '{self.config.realm}'")
        if len(matches) > 1:
            raise ToolError(f"Multiple clients matched client_id '{target_client_id}'")
        return _clean_text(matches[0].get("id"))

    def get_client_roles(self, client_uuid: str) -> dict[str, dict[str, Any]]:
        roles = self._get_json(f"{self.config.admin_base_url}/clients/{client_uuid}/roles")
        if not isinstance(roles, list):
            return {}
        return {
            _clean_text(role.get("name")): role
            for role in roles
            if isinstance(role, dict) and _clean_text(role.get("name"))
        }

    def get_user_client_roles(self, user_id: str, client_uuid: str) -> list[dict[str, Any]]:
        roles = self._get_json(f"{self.config.admin_base_url}/users/{user_id}/role-mappings/clients/{client_uuid}")
        return [item for item in roles if isinstance(item, dict)] if isinstance(roles, list) else []

    def assign_client_roles(self, user_id: str, client_uuid: str, roles: list[dict[str, Any]]) -> None:
        self._post_json(
            f"{self.config.admin_base_url}/users/{user_id}/role-mappings/clients/{client_uuid}",
            roles,
            allow_statuses=(204,),
        )

    def create_user(
        self,
        *,
        username: str,
        email: str,
        first_name: str = "",
        last_name: str = "",
        enabled: bool = True,
        temporary_password: str | None = None,
        attributes: dict[str, Any] | None = None,
        required_actions: list[str] | None = None,
    ) -> str:
        user_data: dict[str, Any] = {
            "username": username,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": enabled,
            "emailVerified": False,
        }
        if attributes:
            user_data["attributes"] = attributes
        if required_actions:
            user_data["requiredActions"] = required_actions

        response = self._post_json(f"{self.config.admin_base_url}/users", user_data, allow_statuses=(201,))
        location = response.headers.get("Location", "")
        user_id = location.rstrip("/").split("/")[-1] if location else ""
        if not user_id:
            created_user = self.resolve_user(login=username, allow_fuzzy=False)
            user_id = _clean_text(created_user.get("id"))
        if temporary_password:
            self.set_user_password(user_id, temporary_password, temporary=True)
        return user_id

    def set_user_password(self, user_id: str, password: str, *, temporary: bool = True) -> None:
        self._put_json(
            f"{self.config.admin_base_url}/users/{user_id}/reset-password",
            {"type": "password", "value": password, "temporary": temporary},
        )

    def get_realm_roles(self) -> dict[str, dict[str, Any]]:
        roles = self._get_json(f"{self.config.admin_base_url}/roles")
        if not isinstance(roles, list):
            return {}
        return {
            _clean_text(role.get("name")): role
            for role in roles
            if isinstance(role, dict) and _clean_text(role.get("name"))
        }

    def create_realm_role(self, role_name: str, description: str = "") -> dict[str, Any]:
        role = {
            "name": role_name,
            "description": description,
            "composite": False,
            "clientRole": False,
        }
        self._post_json(f"{self.config.admin_base_url}/roles", role, allow_statuses=(201,))
        return role

    def assign_realm_roles(self, user_id: str, roles: list[dict[str, Any]]) -> None:
        self._post_json(
            f"{self.config.admin_base_url}/users/{user_id}/role-mappings/realm",
            roles,
            allow_statuses=(204,),
        )

    def get_user_realm_roles(self, user_id: str) -> list[dict[str, Any]]:
        roles = self._get_json(f"{self.config.admin_base_url}/users/{user_id}/role-mappings/realm")
        return [item for item in roles if isinstance(item, dict)] if isinstance(roles, list) else []

    def create_client_role(self, client_uuid: str, role_name: str, description: str = "") -> dict[str, Any]:
        role = {
            "name": role_name,
            "description": description,
            "composite": False,
            "clientRole": True,
        }
        self._post_json(f"{self.config.admin_base_url}/clients/{client_uuid}/roles", role, allow_statuses=(201,))
        return role

    def create_client(
        self,
        *,
        client_id: str,
        name: str,
        description: str,
        service_accounts_enabled: bool = True,
        direct_access_grants_enabled: bool = True,
        standard_flow_enabled: bool = True,
        public_client: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "clientId": client_id,
            "name": name or client_id,
            "description": description,
            "enabled": True,
            "serviceAccountsEnabled": service_accounts_enabled,
            "directAccessGrantsEnabled": direct_access_grants_enabled,
            "standardFlowEnabled": standard_flow_enabled,
            "implicitFlowEnabled": False,
            "publicClient": public_client,
            "protocol": "openid-connect",
        }
        response = self._post_json(f"{self.config.admin_base_url}/clients", payload, allow_statuses=(201,))
        location = response.headers.get("Location", "")
        client_uuid = location.rstrip("/").split("/")[-1] if location else self.get_client_uuid(client_id)
        return {"id": client_uuid, "clientId": client_id, "name": name or client_id}

    def add_protocol_mapper(
        self,
        *,
        client_uuid: str,
        mapper_name: str,
        user_attribute: str,
        token_claim: str,
        add_to_id_token: bool = True,
        add_to_access_token: bool = True,
    ) -> dict[str, Any]:
        mapper = {
            "name": mapper_name,
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "consentRequired": False,
            "config": {
                "userinfo.token.claim": "true",
                "user.attribute": user_attribute,
                "id.token.claim": str(add_to_id_token).lower(),
                "access.token.claim": str(add_to_access_token).lower(),
                "claim.name": token_claim,
                "jsonType.label": "String",
            },
        }
        self._post_json(
            f"{self.config.admin_base_url}/clients/{client_uuid}/protocol-mappers/models",
            mapper,
            allow_statuses=(201,),
        )
        return {"name": mapper_name, "userAttribute": user_attribute, "tokenClaim": token_claim}

    def list_protocol_mappers(self, client_uuid: str) -> list[dict[str, Any]]:
        mappers = self._get_json(f"{self.config.admin_base_url}/clients/{client_uuid}/protocol-mappers/models")
        return [item for item in mappers if isinstance(item, dict)] if isinstance(mappers, list) else []

    def get_client_service_account_user(self, client_uuid: str) -> dict[str, Any]:
        user = self._get_json(f"{self.config.admin_base_url}/clients/{client_uuid}/service-account-user")
        if not isinstance(user, dict):
            raise ToolError(f"Service account user for client '{client_uuid}' was not found")
        return user

    def list_groups(self, *, search: str = "", max_results: int = DEFAULT_GROUP_PAGE_SIZE) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "briefRepresentation": "false",
            "max": max(1, min(int(max_results), 1000)),
        }
        if _clean_text(search):
            params["search"] = search
        groups = self._get_json(f"{self.config.admin_base_url}/groups", params=params)
        return [item for item in groups if isinstance(item, dict)] if isinstance(groups, list) else []

    def flatten_groups(self, groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        flat: list[dict[str, Any]] = []
        stack = list(groups)
        while stack:
            current = stack.pop(0)
            flat.append(current)
            stack.extend(item for item in current.get("subGroups") or [] if isinstance(item, dict))
        return flat

    def resolve_group(self, identifier: str) -> dict[str, Any]:
        value = _clean_text(identifier)
        if not value:
            raise ToolError("Group identifier is required")
        groups = self.flatten_groups(self.list_groups(search=value, max_results=500))
        matches = _dedupe_by_key(
            [
                group
                for group in groups
                if _clean_text(group.get("id")) == value
                or _clean_text(group.get("name")) == value
                or _clean_text(group.get("path")) == value
            ]
        )
        if not matches:
            raise ToolError(f"Group '{value}' not found")
        if len(matches) > 1:
            names = [_clean_text(item.get("path")) or _clean_text(item.get("name")) for item in matches[:5]]
            raise ToolError(f"Ambiguous group match for '{value}': {', '.join(names)}")
        return matches[0]

    def get_user_groups(self, user_id: str) -> list[dict[str, Any]]:
        groups = self._get_json(f"{self.config.admin_base_url}/users/{user_id}/groups")
        return [item for item in groups if isinstance(item, dict)] if isinstance(groups, list) else []

    def add_user_to_group(self, user_id: str, group_id: str) -> None:
        self._put_empty(f"{self.config.admin_base_url}/users/{user_id}/groups/{group_id}")

    def create_group(self, name: str, *, parent_group: str = "") -> dict[str, Any]:
        payload = {"name": name}
        parent_value = _clean_text(parent_group)
        if parent_value:
            parent = self.resolve_group(parent_value)
            response = self._post_json(
                f"{self.config.admin_base_url}/groups/{_clean_text(parent.get('id'))}/children",
                payload,
                allow_statuses=(201, 204),
            )
            location = response.headers.get("Location", "")
            group_id = location.rstrip("/").split("/")[-1] if location else ""
            if group_id:
                created = self.resolve_group(group_id)
            else:
                created = self.resolve_group(f"{_clean_text(parent.get('path'))}/{name}")
            return _group_summary(created)

        response = self._post_json(f"{self.config.admin_base_url}/groups", payload, allow_statuses=(201, 204))
        location = response.headers.get("Location", "")
        group_id = location.rstrip("/").split("/")[-1] if location else ""
        created = self.resolve_group(group_id) if group_id else self.resolve_group(f"/{name}")
        return _group_summary(created)


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


def handle_configure(arguments: dict[str, Any]) -> dict[str, Any]:
    config = _resolve_config(arguments)
    with _client_from_args(arguments) as client:
        client.ping()
    _set_runtime_default(config)
    payload = {
        "success": True,
        "message": "Keycloak runtime default configured successfully",
        "environment": config.safe_summary(),
        "notes": ["For shared HTTP deployment, prefer env defaults or pass profile explicitly on each call."],
    }
    return _tool_result(payload)


def handle_use_profile(arguments: dict[str, Any]) -> dict[str, Any]:
    profile_name = _clean_text(arguments.get("profile"))
    if not profile_name:
        raise ToolError("profile is required")
    args = {"profile": profile_name}
    config = _resolve_config(args)
    with _client_from_args(args) as client:
        client.ping()
    _set_runtime_default(config)
    payload = {
        "success": True,
        "message": f"Profile '{profile_name}' is active for the current process",
        "environment": config.safe_summary(),
    }
    return _tool_result(payload)


def handle_list_profiles(arguments: dict[str, Any]) -> dict[str, Any]:
    _ = arguments
    profiles_payload = _load_profiles()
    profiles = profiles_payload.get("profiles", {})
    result = {
        "success": True,
        "default_profile": profiles_payload.get("default_profile"),
        "profiles": [
            _profile_public_summary(name, profile)
            for name, profile in sorted(profiles.items())
            if isinstance(profile, dict)
        ],
    }
    return _tool_result(result)


def handle_current_environment(arguments: dict[str, Any]) -> dict[str, Any]:
    _ = arguments
    return _tool_result(_current_environment_payload())


def handle_search_users(arguments: dict[str, Any]) -> dict[str, Any]:
    query = _clean_text(arguments.get("query"))
    if not query:
        raise ToolError("query is required")
    exact = _parse_bool(arguments.get("exact"), default=False)
    max_results = max(1, min(int(arguments.get("max_results") or MAX_SEARCH_RESULTS), MAX_SEARCH_RESULTS))
    with _client_from_args(arguments) as client:
        users = client.search_users(query, exact=exact, max_results=max_results)
    payload = {"success": True, "count": len(users), "users": [_user_summary(user) for user in users]}
    return _tool_result(payload)


def handle_find_user(arguments: dict[str, Any]) -> dict[str, Any]:
    login = _clean_text(arguments.get("login"))
    if not login:
        raise ToolError("login is required")
    with _client_from_args(arguments) as client:
        candidates = client.search_user_candidates(login, max_candidates=5)
    if not candidates:
        return _tool_result({"success": True, "found": False, "message": f"User '{login}' not found"})
    payload = {
        "success": True,
        "found": True,
        "user": _user_summary(candidates[0]["user"]),
        "match": {"score": candidates[0]["score"], "reasons": candidates[0]["reasons"]},
        "candidates": [
            {"score": item["score"], "reasons": item["reasons"], "user": _user_summary(item["user"])}
            for item in candidates
        ],
    }
    return _tool_result(payload)


def handle_list_clients(arguments: dict[str, Any]) -> dict[str, Any]:
    search = _clean_text(arguments.get("search"))
    max_results = max(1, min(int(arguments.get("max_results") or 50), 500))
    with _client_from_args(arguments) as client:
        clients = client.list_clients(search=search, max_results=max_results)
    payload = {"success": True, "count": len(clients), "clients": [_client_summary(item) for item in clients]}
    return _tool_result(payload)


def handle_find_clients_with_role(arguments: dict[str, Any]) -> dict[str, Any]:
    role_name = _clean_text(arguments.get("role_name"))
    if not role_name:
        raise ToolError("role_name is required")
    search = _clean_text(arguments.get("search"))
    max_results = max(1, min(int(arguments.get("max_results") or 50), 500))
    with _client_from_args(arguments) as client:
        clients = client.find_clients_with_role(role_name, search=search, max_results=max_results)
    payload = {
        "success": True,
        "role_name": role_name,
        "count": len(clients),
        "clients": [_client_summary(item) for item in clients],
    }
    return _tool_result(payload)


def handle_list_protocol_mappers(arguments: dict[str, Any]) -> dict[str, Any]:
    client_id = _clean_text(arguments.get("client_id"))
    if not client_id:
        raise ToolError("client_id is required")
    with _client_from_args(arguments, strip_target_client_id=True) as client:
        client_uuid = client.get_client_uuid(client_id)
        mappers = client.list_protocol_mappers(client_uuid)
    payload = {
        "success": True,
        "client_id": client_id,
        "client_uuid": client_uuid,
        "count": len(mappers),
        "protocol_mappers": [_protocol_mapper_summary(item) for item in mappers],
    }
    return _tool_result(payload)


def handle_create_user(arguments: dict[str, Any]) -> dict[str, Any]:
    username = _clean_text(arguments.get("username"))
    email = _clean_text(arguments.get("email"))
    if not username or not email:
        raise ToolError("username and email are required")
    first_name = _clean_text(arguments.get("first_name"))
    last_name = _clean_text(arguments.get("last_name"))
    enabled = _parse_bool(arguments.get("enabled"), default=True)
    temporary_password = _clean_text(arguments.get("temporary_password")) or None
    attributes = arguments.get("attributes")
    if attributes is not None and not isinstance(attributes, dict):
        raise ToolError("attributes must be an object")
    required_actions = arguments.get("required_actions") or []
    if not isinstance(required_actions, list):
        raise ToolError("required_actions must be an array")
    with _client_from_args(arguments) as client:
        user_id = client.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            enabled=enabled,
            temporary_password=temporary_password,
            attributes=attributes,
            required_actions=[_clean_text(item) for item in required_actions if _clean_text(item)],
        )
    payload = {
        "success": True,
        "message": "User created successfully",
        "user": {"id": user_id, "username": username, "email": email, "enabled": enabled},
        "password_set": bool(temporary_password),
        "password_temporary": bool(temporary_password),
    }
    return _tool_result(payload)


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
    client_id = _clean_text(arguments.get("client_id"))
    if not client_id:
        raise ToolError("client_id is required")
    name = _clean_text(arguments.get("name")) or client_id
    description = _clean_text(arguments.get("description"))
    service_accounts_enabled = _parse_bool(arguments.get("service_accounts_enabled"), default=True)
    direct_access_grants_enabled = _parse_bool(arguments.get("direct_access_grants_enabled"), default=True)
    standard_flow_enabled = _parse_bool(arguments.get("standard_flow_enabled"), default=True)
    public_client = _parse_bool(arguments.get("public_client"), default=False)
    with _client_from_args(arguments, strip_target_client_id=True) as client:
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
    return _tool_result(payload)


def handle_add_protocol_mapper(arguments: dict[str, Any]) -> dict[str, Any]:
    client_id = _clean_text(arguments.get("client_id"))
    mapper_name = _clean_text(arguments.get("mapper_name"))
    user_attribute = _clean_text(arguments.get("user_attribute"))
    token_claim = _clean_text(arguments.get("token_claim"))
    if not all([client_id, mapper_name, user_attribute, token_claim]):
        raise ToolError("client_id, mapper_name, user_attribute, and token_claim are required")
    add_to_id_token = _parse_bool(arguments.get("add_to_id_token"), default=True)
    add_to_access_token = _parse_bool(arguments.get("add_to_access_token"), default=True)
    with _client_from_args(arguments, strip_target_client_id=True) as client:
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
    return _tool_result(payload)


def handle_assign_service_account_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    return _handle_assign_service_account_roles_impl(arguments, context=_role_handler_context())


def handle_list_groups(arguments: dict[str, Any]) -> dict[str, Any]:
    search = _clean_text(arguments.get("search"))
    max_results = max(1, min(int(arguments.get("max_results") or DEFAULT_GROUP_PAGE_SIZE), 1000))
    with _client_from_args(arguments) as client:
        groups = client.flatten_groups(client.list_groups(search=search, max_results=max_results))
    payload = {"success": True, "count": len(groups), "groups": [_group_summary(group) for group in groups]}
    return _tool_result(payload)


def handle_get_user_groups(arguments: dict[str, Any]) -> dict[str, Any]:
    login = _clean_text(arguments.get("login"))
    user_id = _clean_text(arguments.get("user_id")) or None
    allow_fuzzy = _parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    with _client_from_args(arguments) as client:
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        groups = client.get_user_groups(_clean_text(user.get("id")))
    payload = {"success": True, "user": _user_summary(user), "groups": [_group_summary(group) for group in groups]}
    return _tool_result(payload)


def handle_add_user_to_groups(arguments: dict[str, Any]) -> dict[str, Any]:
    groups = arguments.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ToolError("groups must be a non-empty array")
    login = _clean_text(arguments.get("login"))
    user_id = _clean_text(arguments.get("user_id")) or None
    allow_fuzzy = _parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    with _client_from_args(arguments) as client:
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        current_groups = client.get_user_groups(_clean_text(user.get("id")))
        current_group_ids = {_clean_text(group.get("id")) for group in current_groups}
        added: list[dict[str, Any]] = []
        already_member: list[dict[str, Any]] = []
        for group_name in groups:
            group = client.resolve_group(_clean_text(group_name))
            group_id = _clean_text(group.get("id"))
            if group_id in current_group_ids:
                already_member.append(_group_summary(group))
                continue
            client.add_user_to_group(_clean_text(user.get("id")), group_id)
            added.append(_group_summary(group))
    payload = {"success": True, "user": _user_summary(user), "groups_added": added, "groups_already_assigned": already_member}
    return _tool_result(payload)


def handle_create_group(arguments: dict[str, Any]) -> dict[str, Any]:
    group_name = _clean_text(arguments.get("group_name"))
    if not group_name:
        raise ToolError("group_name is required")
    parent_group = _clean_text(arguments.get("parent_group"))
    with _client_from_args(arguments) as client:
        group = client.create_group(group_name, parent_group=parent_group)
    payload = {"success": True, "message": "Group created successfully", "group": group}
    return _tool_result(payload)


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
