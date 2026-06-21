"""Composable Keycloak admin client used by the MCP handlers."""

from __future__ import annotations

import time
from typing import Any

import requests
from requests import Response, Session
from requests.exceptions import RequestException

from key_mcp_client_clients import KeycloakClientMixin
from key_mcp_client_groups import KeycloakGroupMixin
from key_mcp_client_support import (
    HTTP_PROXIES,
    LOGGER,
    MAX_RETRIES,
    REQUEST_TIMEOUT_SECONDS,
    RETRY_DELAY_SECONDS,
    ToolError,
)
from key_mcp_client_users import KeycloakUserMixin
from key_mcp_config import KeycloakConfig
from key_mcp_config import clean_text as _clean_text
from key_mcp_config import first_non_empty as _first_non_empty


class KeycloakAdminClient(KeycloakUserMixin, KeycloakClientMixin, KeycloakGroupMixin):
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
