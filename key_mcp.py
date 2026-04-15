from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests
from requests import Response, Session
from requests.exceptions import RequestException

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
PROFILE_FILE = Path(os.getenv("KEYCLOAK_PROFILES_FILE", str(Path(__file__).with_name("keycloak_profiles.json"))))
EMAIL_DOMAIN_CANDIDATES = [
    item.strip()
    for item in os.getenv("KEYCLOAK_EMAIL_DOMAINS", "erg.kz,corp.erg.kz,mail.erg.kz").split(",")
    if item.strip()
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


class ToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class KeycloakConfig:
    base_url: str
    realm: str
    token_realm: str
    client_id: str
    admin_user: str
    admin_password: str
    verify_ssl: bool
    client_secret: str = ""
    profile_name: str = ""

    @property
    def admin_base_url(self) -> str:
        return f"{self.base_url}/admin/realms/{self.realm}"

    @property
    def token_url(self) -> str:
        return f"{self.base_url}/realms/{self.token_realm}/protocol/openid-connect/token"

    def safe_summary(self) -> dict[str, Any]:
        return {
            "profile": self.profile_name or None,
            "base_url": self.base_url,
            "realm": self.realm,
            "token_realm": self.token_realm,
            "client_id": self.client_id,
            "admin_user": self.admin_user,
            "verify_ssl": self.verify_ssl,
            "has_client_secret": bool(self.client_secret),
            "password_source": "configured",
        }


_RUNTIME_DEFAULT_LOCK = RLock()
_RUNTIME_DEFAULT: dict[str, Any] = {}


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _tool_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": _json_text(payload)}],
        "structuredContent": payload,
    }
    if is_error:
        result["isError"] = True
    return result


def _result_payload(message_id: Any, result: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result or {}}


def _error_payload(message_id: Any, error: str, *, code: int = -32000) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": error}}


def _emit_stdio_payload(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _parse_bool(value: Any, *, default: bool | None = None) -> bool:
    if value is None:
        if default is None:
            raise ToolError("Boolean value is required")
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ToolError(f"Invalid boolean value: {value}")


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _looks_like_uuid(value: str) -> bool:
    raw = value.strip()
    return len(raw) == 36 and raw.count("-") == 4


def _normalize_base_url(raw_url: str) -> str:
    raw = _clean_text(raw_url)
    if not raw:
        raise ToolError("Keycloak base_url/host is not configured")
    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    if not parsed.netloc:
        raise ToolError(f"Invalid Keycloak URL: {raw_url}")
    if parsed.scheme not in {"http", "https"}:
        raise ToolError("Keycloak URL must use http or https")
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme == "http" and not ALLOW_INSECURE_HTTP and hostname not in {"localhost", "127.0.0.1"}:
        raise ToolError("Plain HTTP Keycloak URL is disabled. Use https or set KEYCLOAK_ALLOW_INSECURE_HTTP=true")
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


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


def _load_profiles() -> dict[str, Any]:
    if not PROFILE_FILE.exists():
        return {"profiles": {}, "default_profile": DEFAULT_PROFILE or None}
    try:
        with PROFILE_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        LOGGER.warning("Failed to load Keycloak profiles from %s: %s", PROFILE_FILE, exc)
        return {"profiles": {}, "default_profile": DEFAULT_PROFILE or None}
    if not isinstance(payload, dict):
        return {"profiles": {}, "default_profile": DEFAULT_PROFILE or None}
    payload.setdefault("profiles", {})
    if "default_profile" not in payload:
        payload["default_profile"] = DEFAULT_PROFILE or None
    return payload


def _resolve_profile(profile_name: str | None) -> tuple[str, dict[str, Any]]:
    profiles_payload = _load_profiles()
    selected = _clean_text(profile_name or profiles_payload.get("default_profile") or DEFAULT_PROFILE)
    if not selected:
        return "", {}
    profile = profiles_payload.get("profiles", {}).get(selected)
    if not isinstance(profile, dict):
        raise ToolError(f"Profile '{selected}' not found")
    return selected, profile


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
    explicit_text = _clean_text(explicit_value)
    if explicit_text:
        return explicit_text
    env_name = _clean_text(explicit_env_name)
    if env_name:
        env_value = os.getenv(env_name, "").strip()
        if not env_value:
            raise ToolError(f"Secret env var '{env_name}' is empty or not set")
        return env_value
    profile_env_name = _clean_text(profile.get(env_field))
    if profile_env_name:
        env_value = os.getenv(profile_env_name, "").strip()
        if not env_value:
            raise ToolError(f"Secret env var '{profile_env_name}' is empty or not set")
        return env_value
    runtime_text = _clean_text(runtime_value)
    if runtime_text:
        return runtime_text
    legacy_value = _clean_text(profile.get(legacy_field))
    if legacy_value:
        LOGGER.warning(
            "Profile '%s' stores '%s' in plain text. Move it to '%s'.",
            profile.get("name") or "unknown",
            legacy_field,
            env_field,
        )
        return legacy_value
    return default_value.strip()


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
    explicit_text = _clean_text(explicit_value)
    if explicit_text:
        return explicit_text
    env_name = _clean_text(explicit_env_name)
    if env_name:
        env_value = os.getenv(env_name, "").strip()
        if not env_value:
            raise ToolError(f"Config env var '{env_name}' for {label} is empty or not set")
        return env_value
    for profile_env_name in profile_env_names:
        resolved_env_name = _clean_text(profile_env_name)
        if not resolved_env_name:
            continue
        env_value = os.getenv(resolved_env_name, "").strip()
        if not env_value:
            raise ToolError(f"Config env var '{resolved_env_name}' for {label} is empty or not set")
        return env_value
    profile_text = _first_non_empty(*profile_values)
    if profile_text:
        return profile_text
    runtime_text = _clean_text(runtime_value)
    if runtime_text:
        return runtime_text
    return _clean_text(default_value)


def _set_runtime_default(config: KeycloakConfig) -> None:
    state = {
        "profile": config.profile_name,
        "base_url": config.base_url,
        "realm": config.realm,
        "token_realm": config.token_realm,
        "client_id": config.client_id,
        "admin_user": config.admin_user,
        "admin_password": config.admin_password,
        "client_secret": config.client_secret,
        "verify_ssl": config.verify_ssl,
    }
    with _RUNTIME_DEFAULT_LOCK:
        _RUNTIME_DEFAULT.clear()
        _RUNTIME_DEFAULT.update(state)


def _get_runtime_default() -> dict[str, Any]:
    with _RUNTIME_DEFAULT_LOCK:
        return dict(_RUNTIME_DEFAULT)


def _current_environment_payload() -> dict[str, Any]:
    runtime = _get_runtime_default()
    profiles = _load_profiles()
    configured_profiles = sorted(name for name, profile in profiles.get("profiles", {}).items() if isinstance(profile, dict))
    return {
        "success": True,
        "runtime_default": {
            "configured": bool(runtime),
            "profile": runtime.get("profile") or None,
            "base_url": runtime.get("base_url") or None,
            "realm": runtime.get("realm") or None,
            "token_realm": runtime.get("token_realm") or None,
            "client_id": runtime.get("client_id") or None,
            "admin_user": runtime.get("admin_user") or None,
            "verify_ssl": runtime.get("verify_ssl") if runtime else None,
        },
        "defaults": {
            "base_url": DEFAULT_KEYCLOAK_URL or None,
            "realm": DEFAULT_REALM or None,
            "token_realm": DEFAULT_TOKEN_REALM or None,
            "client_id": DEFAULT_CLIENT_ID,
            "admin_user": DEFAULT_ADMIN_USER or None,
            "verify_ssl": DEFAULT_VERIFY_SSL,
            "default_profile": profiles.get("default_profile") or None,
            "configured_profiles": configured_profiles,
        },
    }


def _resolve_config(arguments: dict[str, Any] | None = None) -> KeycloakConfig:
    args = arguments or {}
    if not isinstance(args, dict):
        raise ToolError("Tool arguments must be an object")

    runtime = _get_runtime_default()
    profile_name, profile = _resolve_profile(args.get("profile") or runtime.get("profile"))
    base_url = _resolve_value(
        explicit_value=_first_non_empty(args.get("base_url"), args.get("host")),
        explicit_env_name=_first_non_empty(args.get("base_url_env"), args.get("host_env")),
        profile_values=(profile.get("base_url"), profile.get("host")),
        profile_env_names=(profile.get("base_url_env"), profile.get("host_env")),
        runtime_value=_first_non_empty(runtime.get("base_url"), runtime.get("host")),
        default_value=DEFAULT_KEYCLOAK_URL,
        label="base_url",
    )
    realm = _resolve_value(
        explicit_value=args.get("realm"),
        explicit_env_name=args.get("realm_env"),
        profile_values=(profile.get("realm"),),
        profile_env_names=(profile.get("realm_env"),),
        runtime_value=runtime.get("realm"),
        default_value=DEFAULT_REALM,
        label="realm",
    )
    token_realm = _resolve_value(
        explicit_value=args.get("token_realm"),
        explicit_env_name=args.get("token_realm_env"),
        profile_values=(profile.get("token_realm"),),
        profile_env_names=(profile.get("token_realm_env"),),
        runtime_value=runtime.get("token_realm"),
        default_value=DEFAULT_TOKEN_REALM or realm,
        label="token_realm",
    )
    client_id = _resolve_value(
        explicit_value=args.get("client_id"),
        explicit_env_name=args.get("client_id_env"),
        profile_values=(profile.get("client_id"),),
        profile_env_names=(profile.get("client_id_env"),),
        runtime_value=runtime.get("client_id"),
        default_value=DEFAULT_CLIENT_ID,
        label="client_id",
    )
    admin_user = _resolve_value(
        explicit_value=args.get("admin_user"),
        explicit_env_name=args.get("admin_user_env"),
        profile_values=(profile.get("admin_user"),),
        profile_env_names=(profile.get("admin_user_env"),),
        runtime_value=runtime.get("admin_user"),
        default_value=DEFAULT_ADMIN_USER,
        label="admin_user",
    )
    verify_ssl = args.get("verify_ssl")
    if verify_ssl is None and _clean_text(args.get("verify_ssl_env")):
        verify_ssl = os.getenv(_clean_text(args.get("verify_ssl_env")))
        if verify_ssl in {None, ""}:
            raise ToolError(f"Config env var '{_clean_text(args.get('verify_ssl_env'))}' for verify_ssl is empty or not set")
    if verify_ssl is None and _clean_text(profile.get("verify_ssl_env")):
        profile_verify_ssl_env = _clean_text(profile.get("verify_ssl_env"))
        verify_ssl = os.getenv(profile_verify_ssl_env)
        if verify_ssl in {None, ""}:
            raise ToolError(f"Config env var '{profile_verify_ssl_env}' for verify_ssl is empty or not set")
    if verify_ssl is None and "verify_ssl" in profile:
        verify_ssl = profile.get("verify_ssl")
    if verify_ssl is None and "verify_ssl" in runtime:
        verify_ssl = runtime.get("verify_ssl")
    verify_ssl = _parse_bool(verify_ssl, default=DEFAULT_VERIFY_SSL)
    admin_password = _resolve_secret(
        explicit_value=args.get("admin_password"),
        explicit_env_name=args.get("admin_password_env"),
        profile=profile,
        runtime_value=runtime.get("admin_password"),
        default_value=DEFAULT_ADMIN_PASSWORD,
        legacy_field="admin_password",
        env_field="admin_password_env",
    )
    client_secret = _resolve_secret(
        explicit_value=args.get("client_secret"),
        explicit_env_name=args.get("client_secret_env"),
        profile=profile,
        runtime_value=runtime.get("client_secret"),
        default_value=DEFAULT_CLIENT_SECRET,
        legacy_field="client_secret",
        env_field="client_secret_env",
    )

    if not base_url:
        raise ToolError("Keycloak host/base_url is required")
    if not realm:
        raise ToolError("Keycloak realm is required")
    if not token_realm:
        raise ToolError("Keycloak token_realm is required")
    if not admin_user:
        raise ToolError("Keycloak admin_user is required")
    if not admin_password:
        raise ToolError("Keycloak admin_password is required")

    return KeycloakConfig(
        base_url=_normalize_base_url(base_url),
        realm=realm,
        token_realm=token_realm,
        client_id=client_id or "admin-cli",
        admin_user=admin_user,
        admin_password=admin_password,
        client_secret=client_secret,
        verify_ssl=verify_ssl,
        profile_name=profile_name,
    )


def _profile_public_summary(profile_name: str, profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": profile_name,
        "display_name": _clean_text(profile.get("name")) or profile_name,
        "base_url": _first_non_empty(profile.get("base_url"), profile.get("host")) or None,
        "base_url_env": _first_non_empty(profile.get("base_url_env"), profile.get("host_env")) or None,
        "realm": _clean_text(profile.get("realm")) or None,
        "realm_env": _clean_text(profile.get("realm_env")) or None,
        "token_realm": _clean_text(profile.get("token_realm")) or None,
        "token_realm_env": _clean_text(profile.get("token_realm_env")) or None,
        "client_id": _clean_text(profile.get("client_id")) or None,
        "client_id_env": _clean_text(profile.get("client_id_env")) or None,
        "admin_user": _clean_text(profile.get("admin_user")) or None,
        "admin_user_env": _clean_text(profile.get("admin_user_env")) or None,
        "uses_admin_password_env": bool(_clean_text(profile.get("admin_password_env"))),
        "uses_client_secret_env": bool(_clean_text(profile.get("client_secret_env"))),
        "uses_verify_ssl_env": bool(_clean_text(profile.get("verify_ssl_env"))),
        "has_legacy_admin_password": bool(_clean_text(profile.get("admin_password"))),
        "has_legacy_client_secret": bool(_clean_text(profile.get("client_secret"))),
        "verify_ssl": profile.get("verify_ssl", DEFAULT_VERIFY_SSL),
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


def _select_client_roles(role_map: dict[str, dict[str, Any]], current_roles: list[dict[str, Any]], requested_names: list[str]):
    current_role_names = {_clean_text(role.get("name")) for role in current_roles}
    roles_to_add: list[dict[str, Any]] = []
    already_has: list[str] = []
    not_found: list[str] = []
    for role_name in requested_names:
        name = _clean_text(role_name)
        if not name:
            continue
        if name in current_role_names:
            already_has.append(name)
        elif name in role_map:
            roles_to_add.append(role_map[name])
        else:
            not_found.append(name)
    return roles_to_add, already_has, not_found


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
    client_id = _clean_text(arguments.get("client_id"))
    with _client_from_args(arguments, strip_target_client_id=True) as client:
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
    return _tool_result(payload)


def handle_assign_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    roles = arguments.get("roles")
    if not isinstance(roles, list) or not roles:
        raise ToolError("roles must be a non-empty array")
    login = _clean_text(arguments.get("login"))
    user_id = _clean_text(arguments.get("user_id")) or None
    allow_fuzzy = _parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    client_id = _clean_text(arguments.get("client_id"))
    with _client_from_args(arguments, strip_target_client_id=True) as client:
        resolved_client_id = client_id or client.config.client_id
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        client_uuid = client.get_client_uuid(client_id or None)
        role_map = client.get_client_roles(client_uuid)
        current_roles = client.get_user_client_roles(_clean_text(user.get("id")), client_uuid)
        roles_to_add, already_has, not_found = _select_client_roles(role_map, current_roles, list(roles))
        if roles_to_add:
            client.assign_client_roles(_clean_text(user.get("id")), client_uuid, roles_to_add)
    payload = {
        "success": True,
        "user": _user_summary(user),
        "client_id": resolved_client_id,
        "roles_added": [_clean_text(role.get("name")) for role in roles_to_add],
        "roles_already_assigned": already_has,
        "roles_not_found": not_found,
    }
    return _tool_result(payload)


def handle_get_user_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    login = _clean_text(arguments.get("login"))
    user_id = _clean_text(arguments.get("user_id")) or None
    client_id = _clean_text(arguments.get("client_id"))
    allow_fuzzy = _parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    with _client_from_args(arguments, strip_target_client_id=True) as client:
        resolved_client_id = client_id or client.config.client_id
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        client_uuid = client.get_client_uuid(client_id or None)
        roles = client.get_user_client_roles(_clean_text(user.get("id")), client_uuid)
    payload = {
        "success": True,
        "user": _user_summary(user),
        "client_id": resolved_client_id,
        "roles": sorted(_clean_text(role.get("name")) for role in roles if _clean_text(role.get("name"))),
    }
    return _tool_result(payload)


def handle_bulk_assign_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    users = arguments.get("users")
    if not isinstance(users, list) or not users:
        raise ToolError("users must be a non-empty array")
    client_id = _clean_text(arguments.get("client_id"))
    results = {"assigned": [], "errors": [], "skipped": []}
    with _client_from_args(arguments, strip_target_client_id=True) as client:
        resolved_client_id = client_id or client.config.client_id
        client_uuid = client.get_client_uuid(client_id or None)
        role_map = client.get_client_roles(client_uuid)
        for item in users:
            if not isinstance(item, dict):
                results["errors"].append({"item": item, "error": "user entry must be an object"})
                continue
            login = _clean_text(item.get("login"))
            user_id = _clean_text(item.get("user_id")) or None
            role_names = item.get("roles")
            if not isinstance(role_names, list) or not role_names:
                results["errors"].append({"login": login or None, "user_id": user_id, "error": "roles must be a non-empty array"})
                continue
            try:
                user = client.resolve_user(
                    login=login,
                    user_id=user_id,
                    allow_fuzzy=_parse_bool(item.get("allow_fuzzy_user_match"), default=False),
                )
                current_roles = client.get_user_client_roles(_clean_text(user.get("id")), client_uuid)
                roles_to_add, already_has, not_found = _select_client_roles(role_map, current_roles, list(role_names))
                if roles_to_add:
                    client.assign_client_roles(_clean_text(user.get("id")), client_uuid, roles_to_add)
                    results["assigned"].append(
                        {
                            "user": _user_summary(user),
                            "roles_added": [_clean_text(role.get("name")) for role in roles_to_add],
                            "roles_already_assigned": already_has,
                            "roles_not_found": not_found,
                        }
                    )
                else:
                    results["skipped"].append(
                        {
                            "user": _user_summary(user),
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
    return _tool_result(payload, is_error=bool(results["errors"]))


def handle_assign_roles_from_table(arguments: dict[str, Any]) -> dict[str, Any]:
    login = _clean_text(arguments.get("login"))
    user_id = _clean_text(arguments.get("user_id")) or None
    roles_table = _clean_text(arguments.get("roles_table"))
    if not roles_table:
        raise ToolError("roles_table is required")
    roles_by_client = _parse_roles_table(roles_table)
    if not roles_by_client:
        raise ToolError("Could not parse roles table. Expected format: | Client | Role |")
    allow_fuzzy = _parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    results = {"assigned": [], "errors": [], "skipped": []}
    with _client_from_args(arguments) as client:
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        resolved_user_id = _clean_text(user.get("id"))
        for client_key, role_names in roles_by_client.items():
            try:
                client_uuid = client.get_client_uuid(client_key)
                role_map = client.get_client_roles(client_uuid)
                current_roles = client.get_user_client_roles(resolved_user_id, client_uuid)
                roles_to_add, already_has, not_found = _select_client_roles(role_map, current_roles, role_names)
                if roles_to_add:
                    client.assign_client_roles(resolved_user_id, client_uuid, roles_to_add)
                    results["assigned"].append(
                        {
                            "client_id": client_key,
                            "roles_added": [_clean_text(role.get("name")) for role in roles_to_add],
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
        "user": _user_summary(user),
        "total_clients_processed": len(roles_by_client),
        "clients_with_changes": len(results["assigned"]),
        "clients_skipped": len(results["skipped"]),
        "clients_with_errors": len(results["errors"]),
        "details": results,
    }
    return _tool_result(payload, is_error=bool(results["errors"]))

def handle_create_realm_role(arguments: dict[str, Any]) -> dict[str, Any]:
    role_name = _clean_text(arguments.get("role_name"))
    if not role_name:
        raise ToolError("role_name is required")
    description = _clean_text(arguments.get("description"))
    with _client_from_args(arguments) as client:
        role = client.create_realm_role(role_name, description)
    payload = {"success": True, "message": "Realm role created successfully", "role": role}
    return _tool_result(payload)


def handle_assign_realm_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    roles = arguments.get("roles")
    if not isinstance(roles, list) or not roles:
        raise ToolError("roles must be a non-empty array")
    login = _clean_text(arguments.get("login"))
    user_id = _clean_text(arguments.get("user_id")) or None
    allow_fuzzy = _parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    with _client_from_args(arguments) as client:
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        role_map = client.get_realm_roles()
        current_roles = client.get_user_realm_roles(_clean_text(user.get("id")))
        roles_to_add, already_has, not_found = _select_client_roles(role_map, current_roles, list(roles))
        if roles_to_add:
            client.assign_realm_roles(_clean_text(user.get("id")), roles_to_add)
    payload = {
        "success": True,
        "user": _user_summary(user),
        "roles_added": [_clean_text(role.get("name")) for role in roles_to_add],
        "roles_already_assigned": already_has,
        "roles_not_found": not_found,
    }
    return _tool_result(payload)


def handle_get_realm_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    with _client_from_args(arguments) as client:
        role_map = client.get_realm_roles()
    payload = {
        "success": True,
        "count": len(role_map),
        "roles": [{"name": name, "description": role.get("description", "")} for name, role in sorted(role_map.items())],
    }
    return _tool_result(payload)


def handle_get_user_realm_roles(arguments: dict[str, Any]) -> dict[str, Any]:
    login = _clean_text(arguments.get("login"))
    user_id = _clean_text(arguments.get("user_id")) or None
    allow_fuzzy = _parse_bool(arguments.get("allow_fuzzy_user_match"), default=False)
    with _client_from_args(arguments) as client:
        user = client.resolve_user(login=login, user_id=user_id, allow_fuzzy=allow_fuzzy)
        roles = client.get_user_realm_roles(_clean_text(user.get("id")))
    payload = {
        "success": True,
        "user": _user_summary(user),
        "roles": sorted(_clean_text(role.get("name")) for role in roles if _clean_text(role.get("name"))),
    }
    return _tool_result(payload)


def handle_create_client_role(arguments: dict[str, Any]) -> dict[str, Any]:
    client_id = _clean_text(arguments.get("client_id"))
    role_name = _clean_text(arguments.get("role_name"))
    if not client_id or not role_name:
        raise ToolError("client_id and role_name are required")
    description = _clean_text(arguments.get("description"))
    with _client_from_args(arguments, strip_target_client_id=True) as client:
        client_uuid = client.get_client_uuid(client_id)
        role = client.create_client_role(client_uuid, role_name, description)
    payload = {"success": True, "message": "Client role created successfully", "client_id": client_id, "role": role}
    return _tool_result(payload)


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
    client_id = _clean_text(arguments.get("client_id"))
    roles = arguments.get("roles")
    if not client_id or not isinstance(roles, list) or not roles:
        raise ToolError("client_id and roles are required")
    with _client_from_args(arguments, strip_target_client_id=True) as client:
        client_uuid = client.get_client_uuid(client_id)
        service_account_user = client.get_client_service_account_user(client_uuid)
        role_map = client.get_client_roles(client_uuid)
        current_roles = client.get_user_client_roles(_clean_text(service_account_user.get("id")), client_uuid)
        roles_to_add, already_has, not_found = _select_client_roles(role_map, current_roles, list(roles))
        if roles_to_add:
            client.assign_client_roles(_clean_text(service_account_user.get("id")), client_uuid, roles_to_add)
    payload = {
        "success": True,
        "message": "Service account roles assigned successfully",
        "client_id": client_id,
        "service_account_user": _user_summary(service_account_user),
        "roles_added": [_clean_text(role.get("name")) for role in roles_to_add],
        "roles_already_assigned": already_has,
        "roles_not_found": not_found,
    }
    return _tool_result(payload)


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


PROFILE_PROPERTY = {
    "profile": {
        "type": "string",
        "description": "Optional profile name from keycloak_profiles.json. Safer than mutating process defaults on shared HTTP servers.",
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


TOOLS = [
    _tool(
        "keycloak_configure",
        "Validate Keycloak connection settings and store them as the current process default. Prefer env defaults or profiles for shared HTTP deployment.",
        {
            "base_url": {"type": "string", "description": f"Keycloak base URL or host. Default: {DEFAULT_KEYCLOAK_URL or '(not set)'}"},
            "host": {"type": "string", "description": "Legacy alias for base_url."},
            "base_url_env": {"type": "string", "description": "Environment variable that contains Keycloak base_url"},
            "host_env": {"type": "string", "description": "Legacy alias for base_url_env."},
            "realm": {"type": "string", "description": f"Target realm. Default: {DEFAULT_REALM or '(not set)'}"},
            "realm_env": {"type": "string", "description": "Environment variable that contains target realm"},
            "token_realm": {"type": "string", "description": f"Realm used for token grant. Default: {DEFAULT_TOKEN_REALM or DEFAULT_REALM or '(not set)'}"},
            "token_realm_env": {"type": "string", "description": "Environment variable that contains token realm"},
            "client_id": {"type": "string", "description": f"Admin client_id. Default: {DEFAULT_CLIENT_ID}"},
            "client_id_env": {"type": "string", "description": "Environment variable that contains admin client_id"},
            "admin_user": {"type": "string", "description": "Keycloak admin username"},
            "admin_user_env": {"type": "string", "description": "Environment variable that contains Keycloak admin username"},
            "admin_password": {"type": "string", "description": "Keycloak admin password"},
            "admin_password_env": {"type": "string", "description": "Environment variable that contains Keycloak admin password"},
            "client_secret": {"type": "string", "description": "Optional client secret for confidential admin client"},
            "client_secret_env": {"type": "string", "description": "Environment variable that contains the client secret"},
            "verify_ssl": {"type": "boolean", "description": f"Verify TLS certificate. Default: {DEFAULT_VERIFY_SSL}"},
            "verify_ssl_env": {"type": "string", "description": "Environment variable that contains verify_ssl flag"},
            "profile": PROFILE_PROPERTY["profile"],
        },
        ["admin_user"],
    ),
    _tool("keycloak_use_profile", "Validate a named profile and make it the current process default.", {"profile": {"type": "string", "description": "Profile name from keycloak_profiles.json"}}, ["profile"]),
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
            "max_results": {"type": "integer", "description": f"Maximum number of users. Default: {MAX_SEARCH_RESULTS}"},
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
    _tool("keycloak_list_groups", "List groups and subgroup paths.", {"search": {"type": "string", "description": "Optional search term"}, "max_results": {"type": "integer", "description": f"Maximum number of groups. Default: {DEFAULT_GROUP_PAGE_SIZE}"}, **PROFILE_PROPERTY}, []),
    _tool("keycloak_get_user_groups", "List groups assigned to a user.", {**USER_REFERENCE_PROPERTIES, **PROFILE_PROPERTY}, []),
    _tool("keycloak_add_user_to_groups", "Add a user to one or more groups by exact id, name, or path.", {**USER_REFERENCE_PROPERTIES, "groups": {"type": "array", "items": {"type": "string"}, "description": "Group ids, names, or paths"}, **PROFILE_PROPERTY}, ["groups"]),
    _tool("keycloak_create_group", "Create a top-level group or subgroup.", {"group_name": {"type": "string", "description": "New group name"}, "parent_group": {"type": "string", "description": "Optional parent group id, name, or path"}, **PROFILE_PROPERTY}, ["group_name"]),
]


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


def _build_response(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return _result_payload(
            message_id,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "serverInfo": {"name": "keycloak-admin-mcp", "version": "2.0"},
                "capabilities": {"tools": {"listChanged": False}},
            },
        )

    if method == "tools/list":
        return _result_payload(message_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = _clean_text(params.get("name"))
        arguments = params.get("arguments") or {}
        handler = TOOL_HANDLERS.get(tool_name)
        if not handler:
            return _error_payload(message_id, f"Unknown tool: {tool_name}")
        if not isinstance(arguments, dict):
            return _error_payload(message_id, "Tool arguments must be an object")
        try:
            return _result_payload(message_id, handler(arguments))
        except ToolError as exc:
            LOGGER.warning("Keycloak MCP tool error in %s: %s", tool_name, exc)
            return _result_payload(
                message_id,
                _tool_result({"success": False, "error": str(exc), "tool": tool_name}, is_error=True),
            )
        except Exception as exc:
            LOGGER.exception("Keycloak MCP unexpected error in %s", tool_name)
            return _error_payload(message_id, str(exc))

    if message_id is None:
        return None
    return _error_payload(message_id, f"Unsupported method: {method}")


def _handle_stdio_request(message: dict[str, Any]) -> None:
    payload = _build_response(message)
    if payload is not None:
        _emit_stdio_payload(payload)


class _MCPRequestHandler(BaseHTTPRequestHandler):
    server_version = "KeycloakAdminMCP/2.0"

    def do_GET(self):
        if self.path.startswith("/health"):
            self._write_json(200, {"ok": True, "service": "keycloak-admin-mcp"})
            return
        if self.path.startswith("/mcp"):
            self._write_json(
                200,
                {
                    "ok": True,
                    "service": "keycloak-admin-mcp",
                    "transport": "http",
                    "tools": [tool["name"] for tool in TOOLS],
                },
            )
            return
        self._write_json(404, {"error": "Not found"})

    def do_POST(self):
        if not self.path.startswith("/mcp"):
            self._write_json(404, {"error": "Not found"})
            return
        length = int(self.headers.get("content-length") or "0")
        raw_body = self.rfile.read(length)
        try:
            message = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(400, {"error": "Invalid JSON"})
            return
        if not isinstance(message, dict):
            self._write_json(400, {"error": "JSON-RPC payload must be an object"})
            return
        payload = _build_response(message)
        if payload is None:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._write_json(200, payload)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_stdio_server() -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict):
            _handle_stdio_request(message)
    return 0


def run_http_server(host: str, port: int) -> int:
    server = ThreadingHTTPServer((host, port), _MCPRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


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
