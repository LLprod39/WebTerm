from __future__ import annotations

import base64
import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.provider_clients import (
    KubernetesProviderError,
    ProviderJsonClient,
    ProviderTransport,
    _decode_utf8,
    _join_url,
)

MAX_PROVIDER_TUNNEL_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ProviderPortForwardTunnelEvent:
    data: bytes = b""
    eof: bool = False


class UrlopenProviderPortForwardTunnel:
    supports_client_data = False

    def __init__(self, *, url: str, headers: dict[str, str], timeout: int, body: dict[str, Any], verify_tls: bool):
        self.url = url
        self.headers = headers
        self.timeout = timeout
        self.body = body
        self.verify_tls = verify_tls
        self._response = None
        self._eof = False

    def open(self) -> UrlopenProviderPortForwardTunnel:
        headers = {**self.headers, "Content-Type": self.headers.get("Content-Type", "application/json")}
        request = urllib.request.Request(url=self.url, method="POST", headers=headers, data=json.dumps(self.body).encode("utf-8"))
        context = None if self.verify_tls or not self.url.lower().startswith("https://") else ssl._create_unverified_context()
        try:
            self._response = urllib.request.urlopen(request, timeout=self.timeout, context=context)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise KubernetesProviderError(f"Provider port-forward tunnel failed: {exc}") from exc
        return self

    def read_event(self, *, max_bytes: int = MAX_PROVIDER_TUNNEL_BYTES) -> ProviderPortForwardTunnelEvent:
        if self._response is None:
            raise KubernetesProviderError("Provider port-forward tunnel is not open.")
        if self._eof:
            return ProviderPortForwardTunnelEvent(eof=True)
        try:
            raw_line = self._response.readline(max_bytes + 1)
        except TimeoutError:
            return ProviderPortForwardTunnelEvent()
        except (urllib.error.URLError, OSError) as exc:
            raise KubernetesProviderError(f"Provider port-forward tunnel failed: {exc}") from exc
        if not raw_line:
            self._eof = True
            return ProviderPortForwardTunnelEvent(eof=True)
        if len(raw_line) > max_bytes:
            return ProviderPortForwardTunnelEvent(data=raw_line[:max_bytes])
        return _decode_tunnel_event(raw_line)

    def write_client_data(self, data: bytes) -> bool:
        return False

    def close(self) -> None:
        response = self._response
        self._response = None
        if response is not None:
            response.close()


class InMemoryProviderPortForwardTunnel:
    supports_client_data = True

    def __init__(self, payload: Any):
        self.events = _events_from_payload(payload)
        self.client_chunks: list[bytes] = []
        self.offset = 0
        self.closed = False

    def read_event(self, *, max_bytes: int = MAX_PROVIDER_TUNNEL_BYTES) -> ProviderPortForwardTunnelEvent:
        if self.offset >= len(self.events):
            return ProviderPortForwardTunnelEvent(eof=True)
        event = self.events[self.offset]
        self.offset += 1
        return event

    def write_client_data(self, data: bytes) -> bool:
        self.client_chunks.append(bytes(data))
        return True

    def close(self) -> None:
        self.closed = True


def open_provider_port_forward_tunnel(
    provider: K8sProvider,
    path: str,
    *,
    timeout: int,
    target: dict[str, Any],
    duration_seconds: int,
    transport: ProviderTransport | None = None,
):
    client = ProviderJsonClient(provider, transport=transport, timeout=timeout)
    headers = {"Accept": "application/json, application/octet-stream, */*"}
    if client.token:
        headers.update(client._token_headers(client.token))
    body = {"target": target, "duration_seconds": int(duration_seconds)}
    if transport:
        url = _join_url(provider.base_url, path)
        return InMemoryProviderPortForwardTunnel(client._call_transport(url, headers, method="POST", body=body))
    return UrlopenProviderPortForwardTunnel(url=_join_url(provider.base_url, path), headers=headers, timeout=timeout, body=body, verify_tls=client.verify_tls).open()


def _events_from_payload(payload: Any) -> list[ProviderPortForwardTunnelEvent]:
    if isinstance(payload, bytes):
        return [ProviderPortForwardTunnelEvent(data=payload)]
    if isinstance(payload, str):
        return [ProviderPortForwardTunnelEvent(data=line.encode("utf-8")) for line in payload.splitlines() if line]
    if isinstance(payload, dict):
        raw_events = payload.get("events")
        if isinstance(raw_events, list):
            return [_event_from_item(item) for item in raw_events]
        for key in ("data", "chunk", "payload"):
            if key in payload:
                return [_event_from_item(payload)]
    if isinstance(payload, list):
        return [_event_from_item(item) for item in payload]
    return []


def _event_from_item(item: Any) -> ProviderPortForwardTunnelEvent:
    if isinstance(item, bytes):
        return ProviderPortForwardTunnelEvent(data=item)
    if isinstance(item, str):
        return ProviderPortForwardTunnelEvent(data=item.encode("utf-8"))
    if isinstance(item, dict):
        if item.get("eof"):
            return ProviderPortForwardTunnelEvent(eof=True)
        value = item.get("data", item.get("chunk", item.get("payload", "")))
        if item.get("encoding") == "base64":
            try:
                return ProviderPortForwardTunnelEvent(data=base64.b64decode(str(value or "")))
            except (ValueError, TypeError):
                return ProviderPortForwardTunnelEvent()
        return ProviderPortForwardTunnelEvent(data=str(value or "").encode("utf-8"))
    return ProviderPortForwardTunnelEvent(data=str(item).encode("utf-8"))


def _decode_tunnel_event(raw_line: bytes) -> ProviderPortForwardTunnelEvent:
    text = _decode_utf8(raw_line, payload_name="port-forward tunnel line").strip()
    if not text:
        return ProviderPortForwardTunnelEvent()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ProviderPortForwardTunnelEvent(data=raw_line.rstrip(b"\r\n"))
    if not isinstance(payload, dict):
        return ProviderPortForwardTunnelEvent(data=str(payload).encode("utf-8"))
    return _event_from_item(payload)
