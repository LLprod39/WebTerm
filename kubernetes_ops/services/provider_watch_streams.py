from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.provider_clients import (
    MAX_PROVIDER_STREAM_EVENTS,
    KubernetesProviderError,
    ProviderJsonClient,
    ProviderTransport,
    _decode_json_payload,
    _decode_utf8,
    _join_url,
)

MAX_PROVIDER_WATCH_STREAM_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ProviderWatchStreamBatch:
    events: list[dict[str, Any]]
    truncated: bool = False
    eof: bool = False
    bytes_read: int = 0


class UrlopenProviderWatchEventStream:
    def __init__(self, *, url: str, headers: dict[str, str], timeout: int, verify_tls: bool):
        self.url = url
        self.headers = headers
        self.timeout = timeout
        self.verify_tls = verify_tls
        self._response = None
        self._eof = False
        self._sse_payload_lines: list[str] = []

    def open(self) -> UrlopenProviderWatchEventStream:
        request = urllib.request.Request(url=self.url, method="GET", headers=self.headers)
        context = (
            None if self.verify_tls or not self.url.lower().startswith("https://") else ssl._create_unverified_context()
        )
        try:
            self._response = urllib.request.urlopen(request, timeout=self.timeout, context=context)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise KubernetesProviderError(f"Provider watch stream failed: {exc}") from exc
        return self

    def read_batch(
        self, *, max_events: int, max_bytes: int = MAX_PROVIDER_WATCH_STREAM_BYTES
    ) -> ProviderWatchStreamBatch:
        if self._response is None:
            raise KubernetesProviderError("Provider watch stream is not open.")
        if self._eof:
            return ProviderWatchStreamBatch(events=[], eof=True)
        events: list[dict[str, Any]] = []
        bytes_read = 0
        truncated = False
        try:
            while len(events) < max_events:
                remaining = max_bytes - bytes_read
                if remaining <= 0:
                    truncated = True
                    break
                raw_line = self._response.readline(remaining + 1)
                if not raw_line:
                    self._eof = True
                    self._flush_sse_event(events)
                    break
                bytes_read += len(raw_line)
                if bytes_read > max_bytes:
                    truncated = True
                    break
                self._consume_line(_decode_utf8(raw_line, payload_name="watch event line"), events)
        except TimeoutError:
            return ProviderWatchStreamBatch(events=[], eof=False)
        except (urllib.error.URLError, OSError) as exc:
            raise KubernetesProviderError(f"Provider watch stream failed: {exc}") from exc
        return ProviderWatchStreamBatch(events=events, truncated=truncated, eof=self._eof, bytes_read=bytes_read)

    def close(self) -> None:
        response = self._response
        self._response = None
        if response is not None:
            response.close()

    def _consume_line(self, line: str, events: list[dict[str, Any]]) -> None:
        value = line.strip()
        if not value:
            self._flush_sse_event(events)
            return
        if value.startswith(":") or value.startswith(("event:", "id:", "retry:")):
            return
        if value.startswith("data:"):
            data = value.removeprefix("data:").strip()
            if data and data != "[DONE]":
                self._sse_payload_lines.append(data)
            return
        self._append_json_event(value, events)

    def _flush_sse_event(self, events: list[dict[str, Any]]) -> None:
        raw_payload = "\n".join(self._sse_payload_lines).strip()
        self._sse_payload_lines = []
        if raw_payload and raw_payload != "[DONE]":
            self._append_json_event(raw_payload, events)

    @staticmethod
    def _append_json_event(raw_payload: str, events: list[dict[str, Any]]) -> None:
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return
        if isinstance(payload, dict):
            events.append(payload)


class InMemoryProviderWatchEventStream:
    def __init__(self, payload: Any):
        self._events = _event_items_from_transport_payload(payload)
        self._offset = 0

    def read_batch(
        self, *, max_events: int, max_bytes: int = MAX_PROVIDER_WATCH_STREAM_BYTES
    ) -> ProviderWatchStreamBatch:
        end = min(self._offset + max_events, len(self._events))
        events = self._events[self._offset : end]
        self._offset = end
        return ProviderWatchStreamBatch(events=events, eof=self._offset >= len(self._events))

    def close(self) -> None:
        return None


def open_provider_watch_event_stream(
    provider: K8sProvider,
    path: str,
    *,
    timeout: int,
    transport: ProviderTransport | None = None,
    include_token: bool = True,
    extra_headers: dict[str, str] | None = None,
):
    client = ProviderJsonClient(provider, transport=transport, timeout=timeout)
    headers = {"Accept": "application/json, text/event-stream, application/x-ndjson, */*"}
    if include_token and client.token:
        headers.update(client._token_headers(client.token))
    if extra_headers:
        headers.update(extra_headers)
    if transport:
        url = _join_url(provider.base_url, path)
        return InMemoryProviderWatchEventStream(client._call_transport(url, headers, method="GET", body=None))
    return UrlopenProviderWatchEventStream(
        url=_join_url(provider.base_url, path),
        headers=headers,
        timeout=timeout,
        verify_tls=client.verify_tls,
    ).open()


def _event_items_from_transport_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, bytes):
        payload = _decode_json_payload(payload)
    elif isinstance(payload, str):
        payload = _decode_json_payload(payload.encode("utf-8"))
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = (
            payload.get("items")
            or payload.get("events")
            or payload.get("data")
            or ([payload] if payload.get("type") or isinstance(payload.get("object"), dict) else [])
        )
    else:
        items = []
    return [item for item in items[:MAX_PROVIDER_STREAM_EVENTS] if isinstance(item, dict)]
