from __future__ import annotations

import inspect
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.secrets import redact_secret, resolve_provider_token

ProviderTransport = Callable[..., dict[str, Any]]
MAX_PROVIDER_STREAM_EVENTS = 1000
MAX_PROVIDER_LOG_STREAM_BYTES = 1024 * 1024


class KubernetesProviderError(ValueError):
    pass


def _join_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/") + "/"
    return urllib.parse.urljoin(base, path.lstrip("/"))


def _decode_json_payload(data: bytes) -> dict[str, Any]:
    text = _decode_utf8(data, payload_name="JSON")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = _decode_event_stream_payload(text)
    if not isinstance(payload, dict):
        raise KubernetesProviderError("Provider JSON payload must be an object.")
    return payload


def _decode_log_payload(data: bytes) -> dict[str, Any]:
    text = _decode_utf8(data, payload_name="log")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        try:
            return _decode_event_stream_payload(text)
        except KubernetesProviderError:
            return {"content": text}
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        return {"lines": payload}
    return {"content": str(payload)}


def _decode_utf8(data: bytes, *, payload_name: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KubernetesProviderError(f"Provider returned invalid UTF-8 {payload_name}: {exc}") from exc


def _decode_event_stream_payload(text: str) -> dict[str, Any]:
    events = _decode_sse_json_events(text) or _decode_ndjson_events(text)
    if not events:
        raise KubernetesProviderError("Provider returned invalid JSON event stream.")
    if len(events) == 1:
        return events[0]
    return {"items": events}


def _decode_sse_json_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    payload_lines: list[str] = []
    saw_sse = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            _append_stream_event(events, "\n".join(payload_lines))
            payload_lines = []
            continue
        if line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        saw_sse = True
        raw_payload = line.removeprefix("data:").strip()
        if not raw_payload or raw_payload == "[DONE]":
            continue
        payload_lines.append(raw_payload)
        if len(events) >= MAX_PROVIDER_STREAM_EVENTS:
            break
    _append_stream_event(events, "\n".join(payload_lines))
    return events if saw_sse else []


def _decode_ndjson_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        raw_payload = line.strip()
        if not raw_payload or raw_payload.startswith((":", "event:", "id:", "retry:")):
            continue
        if _append_stream_event(events, raw_payload) and len(events) >= MAX_PROVIDER_STREAM_EVENTS:
            break
    return events


def _append_stream_event(events: list[dict[str, Any]], raw_payload: str) -> bool:
    raw_payload = str(raw_payload or "").strip()
    if not raw_payload or raw_payload == "[DONE]":
        return False
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return False
    if isinstance(payload, dict):
        events.append(payload)
        return True
    return False


def _default_transport(
    url: str,
    headers: dict[str, str],
    timeout: int,
    *,
    verify_tls: bool = True,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = _default_raw_transport(url, headers, timeout, verify_tls=verify_tls, method=method, body=body)
    return _decode_json_payload(data)


def _default_raw_transport(
    url: str,
    headers: dict[str, str],
    timeout: int,
    *,
    verify_tls: bool = True,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> bytes:
    data = None
    if body is not None:
        headers = {**headers, "Content-Type": headers.get("Content-Type", "application/json")}
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url=url, method=method.upper(), headers=headers, data=data)
    context = None if verify_tls or not url.lower().startswith("https://") else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return response.read(5 * 1024 * 1024)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise KubernetesProviderError(f"Provider request failed: {exc}") from exc


class ProviderJsonClient:
    def __init__(self, provider: K8sProvider, *, transport: ProviderTransport | None = None, timeout: int = 20):
        self.provider = provider
        self.timeout = timeout
        self.transport = transport
        self.token = resolve_provider_token(provider)
        labels = provider.labels if isinstance(provider.labels, dict) else {}
        self.labels = labels
        self.verify_tls = str(labels.get("tls_verify", "true")).strip().lower() not in {"0", "false", "no", "off"}

    def get(
        self, path: str, *, include_token: bool = True, extra_headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        return self.request("GET", path, include_token=include_token, extra_headers=extra_headers)

    def get_log_payload(
        self, path: str, *, include_token: bool = True, extra_headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json, text/plain, */*"}
        if extra_headers:
            headers.update(extra_headers)
        return self.request_log_payload("GET", path, include_token=include_token, extra_headers=headers)

    def stream_log_lines(
        self,
        path: str,
        *,
        max_lines: int,
        max_bytes: int = MAX_PROVIDER_LOG_STREAM_BYTES,
        include_token: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[list[str], bool]:
        headers = {"Accept": "text/plain, application/json, */*"}
        if include_token and self.token:
            headers.update(self._token_headers(self.token))
        if extra_headers:
            headers.update(extra_headers)
        url = _join_url(self.provider.base_url, path)
        try:
            if self.transport:
                return _coerce_log_stream_lines(
                    self._call_transport(url, headers, method="GET", body=None), max_lines=max_lines
                )
            return _default_log_stream_lines(
                url,
                headers,
                self.timeout,
                verify_tls=self.verify_tls,
                max_lines=max_lines,
                max_bytes=max_bytes,
            )
        except Exception as exc:
            raise KubernetesProviderError(redact_secret(exc, self.token)) from exc

    def post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        include_token: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self.request("POST", path, body=body, include_token=include_token, extra_headers=extra_headers)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        include_token: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if include_token and self.token:
            headers.update(self._token_headers(self.token))
        if extra_headers:
            headers.update(extra_headers)
        url = _join_url(self.provider.base_url, path)
        try:
            if self.transport:
                return self._call_transport(url, headers, method=method, body=body)
            return _default_transport(url, headers, self.timeout, verify_tls=self.verify_tls, method=method, body=body)
        except Exception as exc:
            raise KubernetesProviderError(redact_secret(exc, self.token)) from exc

    def request_log_payload(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        include_token: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json, text/plain, */*"}
        if include_token and self.token:
            headers.update(self._token_headers(self.token))
        if extra_headers:
            headers.update(extra_headers)
        url = _join_url(self.provider.base_url, path)
        try:
            if self.transport:
                return _coerce_log_transport_payload(self._call_transport(url, headers, method=method, body=body))
            data = _default_raw_transport(
                url, headers, self.timeout, verify_tls=self.verify_tls, method=method, body=body
            )
            return _decode_log_payload(data)
        except Exception as exc:
            raise KubernetesProviderError(redact_secret(exc, self.token)) from exc

    def _token_headers(self, token: str) -> dict[str, str]:
        header_name = str(self.labels.get("token_header") or self.labels.get("auth_header") or "Authorization").strip()
        if not header_name:
            return {}
        if header_name.lower() == "authorization":
            scheme = str(self.labels.get("auth_scheme", "Bearer")).strip()
            return {"Authorization": f"{scheme} {token}" if scheme else token}
        return {header_name: token}

    def _call_transport(
        self, url: str, headers: dict[str, str], *, method: str, body: dict[str, Any] | None
    ) -> dict[str, Any]:
        if _transport_accepts_request_kwargs(self.transport):
            return self.transport(url, headers, self.timeout, method=method, body=body)
        if method.upper() == "GET" and body is None:
            return self.transport(url, headers, self.timeout)
        raise KubernetesProviderError("Provider test transport does not support non-GET requests.")


def _transport_accepts_request_kwargs(transport: ProviderTransport | None) -> bool:
    if transport is None:
        return False
    try:
        parameters = inspect.signature(transport).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters) or any(
        parameter.name in {"method", "body"} for parameter in parameters
    )


def _coerce_log_transport_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, bytes):
        return _decode_log_payload(payload)
    if isinstance(payload, str):
        return _decode_log_payload(payload.encode("utf-8"))
    if isinstance(payload, list):
        return {"lines": payload}
    return {"content": str(payload)}


def _coerce_log_stream_lines(payload: Any, *, max_lines: int) -> tuple[list[str], bool]:
    normalized = _coerce_log_transport_payload(payload)
    lines = _log_lines_from_payload(normalized)
    truncated = len(lines) > max_lines
    return lines[:max_lines], truncated


def _default_log_stream_lines(
    url: str,
    headers: dict[str, str],
    timeout: int,
    *,
    verify_tls: bool,
    max_lines: int,
    max_bytes: int,
) -> tuple[list[str], bool]:
    request = urllib.request.Request(url=url, method="GET", headers=headers)
    context = None if verify_tls or not url.lower().startswith("https://") else ssl._create_unverified_context()
    lines: list[str] = []
    bytes_read = 0
    truncated = False
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            while len(lines) < max_lines:
                remaining = max(1, max_bytes - bytes_read + 1)
                raw_line = response.readline(remaining)
                if not raw_line:
                    break
                bytes_read += len(raw_line)
                if bytes_read > max_bytes:
                    truncated = True
                    break
                lines.append(_decode_utf8(raw_line, payload_name="log line").rstrip("\r\n"))
            if len(lines) >= max_lines:
                remaining = max_bytes - bytes_read
                if remaining <= 0:
                    truncated = True
                else:
                    probe = response.readline(remaining + 1)
                    truncated = bool(probe)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise KubernetesProviderError(f"Provider log stream failed: {exc}") from exc
    return lines, truncated


def _log_lines_from_payload(payload: dict[str, Any]) -> list[str]:
    for key in ("lines", "logs", "log", "content", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return value.splitlines()
    return []


def provider_path(provider: K8sProvider, key: str, default: str) -> str:
    labels = provider.labels if isinstance(provider.labels, dict) else {}
    value = labels.get(key)
    return str(value or default)


class RancherClient:
    def __init__(self, provider: K8sProvider, *, transport: ProviderTransport | None = None):
        self.provider = provider
        self.client = ProviderJsonClient(provider, transport=transport)

    def list_clusters(self) -> dict[str, Any]:
        return self.client.get(provider_path(self.provider, "clusters_path", "/v3/clusters"))

    def list_namespaces(self) -> dict[str, Any]:
        return self.client.get(provider_path(self.provider, "namespaces_path", "/v3/projectnamespaces"))

    def list_workloads(self) -> dict[str, Any]:
        return self.client.get(provider_path(self.provider, "workloads_path", "/v3/workloads"))

    def list_pods(self) -> dict[str, Any]:
        return self.client.get(provider_path(self.provider, "pods_path", "/v3/pods"))

    def list_services(self) -> dict[str, Any]:
        return self.client.get(provider_path(self.provider, "services_path", "/v3/services"))

    def list_ingresses(self) -> dict[str, Any]:
        return self.client.get(provider_path(self.provider, "ingresses_path", "/v3/ingresses"))

    def list_events(self) -> dict[str, Any]:
        return self.client.get(provider_path(self.provider, "events_path", "/v3/events"))

    def list_fleet_bundles(self) -> dict[str, Any]:
        return self.client.get(provider_path(self.provider, "fleet_bundles_path", "/v1/fleet.cattle.io.bundles"))


class DevtronClient:
    def __init__(self, provider: K8sProvider, *, transport: ProviderTransport | None = None):
        self.provider = provider
        self.client = ProviderJsonClient(provider, transport=transport)
        self._session_headers: dict[str, str] | None = None

    def get(self, path: str) -> dict[str, Any]:
        return self.client.get(
            path, include_token=not self._uses_session_auth(), extra_headers=self._devtron_auth_headers()
        )

    def list_apps(self) -> dict[str, Any]:
        return self.get(provider_path(self.provider, "apps_path", "/orchestrator/app/list"))

    def _devtron_auth_headers(self) -> dict[str, str]:
        if not self._uses_session_auth():
            return {}
        labels = self.provider.labels if isinstance(self.provider.labels, dict) else {}
        if self._session_headers is not None:
            return dict(self._session_headers)
        password = self.client.token
        username = str(labels.get("auth_username") or labels.get("username") or "admin").strip()
        if not password:
            raise KubernetesProviderError(f"{self.provider.name} Devtron session password is not configured.")
        login_path = provider_path(self.provider, "login_path", "/orchestrator/api/v1/session")
        username_field = str(labels.get("username_field") or "username").strip() or "username"
        response = self.client.post(login_path, {username_field: username, "password": password}, include_token=False)
        token = _nested_value(response, "result.token") or _nested_value(response, "token")
        token = str(token or "").strip()
        if not token:
            raise KubernetesProviderError(f"{self.provider.name} Devtron session login did not return a token.")
        token_header = str(labels.get("session_token_header") or "token").strip()
        cookie_name = str(labels.get("session_cookie_name") or "argocd.token").strip()
        headers: dict[str, str] = {}
        if token_header:
            headers[token_header] = token
        if cookie_name:
            headers["Cookie"] = f"{cookie_name}={token}"
        self._session_headers = headers
        return dict(headers)

    def _uses_session_auth(self) -> bool:
        labels = self.provider.labels if isinstance(self.provider.labels, dict) else {}
        strategy = str(labels.get("auth_strategy") or labels.get("auth_mode") or "").strip().lower()
        return strategy in {"devtron_session", "session"}


def _nested_value(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current
