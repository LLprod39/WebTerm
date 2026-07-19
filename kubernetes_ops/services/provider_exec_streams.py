from __future__ import annotations

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

MAX_PROVIDER_EXEC_STREAM_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ProviderExecStreamEvent:
    stream: str
    data: str = ""
    exit_code: int | None = None
    eof: bool = False


class UrlopenProviderExecStream:
    supports_stdin = False

    def __init__(self, *, url: str, headers: dict[str, str], timeout: int, verify_tls: bool, body: dict[str, Any]):
        self.url = url
        self.headers = headers
        self.timeout = timeout
        self.verify_tls = verify_tls
        self.body = body
        self._response = None
        self._eof = False

    def open(self) -> UrlopenProviderExecStream:
        headers = {**self.headers, "Content-Type": self.headers.get("Content-Type", "application/json")}
        request = urllib.request.Request(url=self.url, method="POST", headers=headers, data=json.dumps(self.body).encode("utf-8"))
        context = None if self.verify_tls or not self.url.lower().startswith("https://") else ssl._create_unverified_context()
        try:
            self._response = urllib.request.urlopen(request, timeout=self.timeout, context=context)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise KubernetesProviderError(f"Provider exec stream failed: {exc}") from exc
        return self

    def read_event(self, *, max_bytes: int = MAX_PROVIDER_EXEC_STREAM_BYTES) -> ProviderExecStreamEvent:
        if self._response is None:
            raise KubernetesProviderError("Provider exec stream is not open.")
        if self._eof:
            return ProviderExecStreamEvent(stream="status", eof=True)
        try:
            raw_line = self._response.readline(max_bytes + 1)
        except TimeoutError:
            return ProviderExecStreamEvent(stream="heartbeat")
        except (urllib.error.URLError, OSError) as exc:
            raise KubernetesProviderError(f"Provider exec stream failed: {exc}") from exc
        if not raw_line:
            self._eof = True
            return ProviderExecStreamEvent(stream="status", eof=True)
        if len(raw_line) > max_bytes:
            return ProviderExecStreamEvent(stream="stderr", data="[truncated]")
        return _coerce_exec_event(_decode_utf8(raw_line, payload_name="exec event line").rstrip("\r\n"))

    def write_stdin(self, data: str) -> bool:
        return False

    def close(self) -> None:
        response = self._response
        self._response = None
        if response is not None:
            response.close()


class InMemoryProviderExecStream:
    supports_stdin = True

    def __init__(self, payload: Any):
        self.events = _events_from_payload(payload)
        self.stdin: list[str] = []
        self.offset = 0
        self.closed = False

    def read_event(self, *, max_bytes: int = MAX_PROVIDER_EXEC_STREAM_BYTES) -> ProviderExecStreamEvent:
        if self.offset >= len(self.events):
            return ProviderExecStreamEvent(stream="status", eof=True)
        event = self.events[self.offset]
        self.offset += 1
        return event

    def write_stdin(self, data: str) -> bool:
        self.stdin.append(str(data))
        return True

    def close(self) -> None:
        self.closed = True


def open_provider_exec_stream(
    provider: K8sProvider,
    path: str,
    *,
    timeout: int,
    command: list[str],
    container: str = "",
    tty: bool = False,
    stdin: bool = False,
    transport: ProviderTransport | None = None,
):
    client = ProviderJsonClient(provider, transport=transport, timeout=timeout)
    headers = {"Accept": "application/json, text/plain, */*"}
    if client.token:
        headers.update(client._token_headers(client.token))
    body = {"command": list(command), "container": str(container or ""), "tty": bool(tty), "stdin": bool(stdin)}
    if transport:
        url = _join_url(provider.base_url, path)
        return InMemoryProviderExecStream(client._call_transport(url, headers, method="POST", body=body))
    return UrlopenProviderExecStream(
        url=_join_url(provider.base_url, path),
        headers=headers,
        timeout=timeout,
        verify_tls=client.verify_tls,
        body=body,
    ).open()


def _coerce_exec_event(raw_payload: str) -> ProviderExecStreamEvent:
    value = str(raw_payload or "")
    if not value:
        return ProviderExecStreamEvent(stream="heartbeat")
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return ProviderExecStreamEvent(stream="stdout", data=value)
    if not isinstance(payload, dict):
        return ProviderExecStreamEvent(stream="stdout", data=str(payload))
    stream = str(payload.get("stream") or payload.get("type") or "stdout").strip().lower()
    if stream in {"exit", "status", "close"}:
        return ProviderExecStreamEvent(stream="status", exit_code=_exit_code(payload), eof=True)
    if stream not in {"stdout", "stderr", "heartbeat"}:
        stream = "stdout"
    data = payload.get("data", payload.get("line", payload.get("message", "")))
    return ProviderExecStreamEvent(stream=stream, data=str(data or ""), exit_code=_exit_code(payload), eof=bool(payload.get("eof", False)))


def _events_from_payload(payload: Any) -> list[ProviderExecStreamEvent]:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        return [_coerce_exec_event(line) for line in payload.splitlines() if line.strip()]
    if isinstance(payload, dict):
        raw_events = payload.get("events")
        if isinstance(raw_events, list):
            return [_coerce_exec_event(json.dumps(item) if isinstance(item, dict) else str(item)) for item in raw_events]
        events: list[ProviderExecStreamEvent] = []
        for key in ("stdout", "stderr"):
            values = payload.get(key)
            if isinstance(values, list):
                events.extend(ProviderExecStreamEvent(stream=key, data=str(item)) for item in values)
            elif isinstance(values, str):
                events.extend(ProviderExecStreamEvent(stream=key, data=line) for line in values.splitlines())
        if "exit_code" in payload:
            events.append(ProviderExecStreamEvent(stream="status", exit_code=_exit_code(payload), eof=True))
        return events
    if isinstance(payload, list):
        return [_coerce_exec_event(json.dumps(item) if isinstance(item, dict) else str(item)) for item in payload]
    return []


def _exit_code(payload: dict[str, Any]) -> int | None:
    try:
        value = payload.get("exit_code", payload.get("exitCode", payload.get("code")))
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
