from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.provider_clients import (
    MAX_PROVIDER_LOG_STREAM_BYTES,
    KubernetesProviderError,
    ProviderJsonClient,
    ProviderTransport,
    _coerce_log_transport_payload,
    _decode_utf8,
    _join_url,
    _log_lines_from_payload,
)


@dataclass(frozen=True)
class ProviderLogStreamBatch:
    lines: list[str]
    truncated: bool = False
    eof: bool = False
    bytes_read: int = 0


class UrlopenProviderLogLineStream:
    def __init__(self, *, url: str, headers: dict[str, str], timeout: int, verify_tls: bool):
        self.url = url
        self.headers = headers
        self.timeout = timeout
        self.verify_tls = verify_tls
        self._response = None
        self._eof = False

    def open(self) -> "UrlopenProviderLogLineStream":
        request = urllib.request.Request(url=self.url, method="GET", headers=self.headers)
        context = None if self.verify_tls or not self.url.lower().startswith("https://") else ssl._create_unverified_context()
        try:
            self._response = urllib.request.urlopen(request, timeout=self.timeout, context=context)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise KubernetesProviderError(f"Provider log stream failed: {exc}") from exc
        return self

    def read_batch(self, *, max_lines: int, max_bytes: int = MAX_PROVIDER_LOG_STREAM_BYTES) -> ProviderLogStreamBatch:
        if self._response is None:
            raise KubernetesProviderError("Provider log stream is not open.")
        if self._eof:
            return ProviderLogStreamBatch(lines=[], eof=True)
        lines: list[str] = []
        bytes_read = 0
        truncated = False
        try:
            while len(lines) < max_lines:
                remaining = max_bytes - bytes_read
                if remaining <= 0:
                    truncated = True
                    break
                raw_line = self._response.readline(remaining + 1)
                if not raw_line:
                    self._eof = True
                    break
                bytes_read += len(raw_line)
                if bytes_read > max_bytes:
                    truncated = True
                    break
                lines.append(_decode_utf8(raw_line, payload_name="log line").rstrip("\r\n"))
        except TimeoutError:
            return ProviderLogStreamBatch(lines=[], eof=False)
        except (urllib.error.URLError, OSError) as exc:
            raise KubernetesProviderError(f"Provider log stream failed: {exc}") from exc
        return ProviderLogStreamBatch(lines=lines, truncated=truncated, eof=self._eof, bytes_read=bytes_read)

    def close(self) -> None:
        response = self._response
        self._response = None
        if response is not None:
            response.close()


class InMemoryProviderLogLineStream:
    def __init__(self, payload: Any):
        normalized = _coerce_log_transport_payload(payload)
        self._lines = _log_lines_from_payload(normalized)
        self._offset = 0

    def read_batch(self, *, max_lines: int, max_bytes: int = MAX_PROVIDER_LOG_STREAM_BYTES) -> ProviderLogStreamBatch:
        lines: list[str] = []
        bytes_read = 0
        truncated = False
        while self._offset < len(self._lines) and len(lines) < max_lines:
            line = str(self._lines[self._offset])
            line_bytes = len(line.encode("utf-8")) + 1
            if bytes_read + line_bytes > max_bytes:
                truncated = True
                break
            lines.append(line)
            bytes_read += line_bytes
            self._offset += 1
        return ProviderLogStreamBatch(lines=lines, truncated=truncated, eof=self._offset >= len(self._lines), bytes_read=bytes_read)

    def close(self) -> None:
        return None


def open_provider_log_line_stream(
    provider: K8sProvider,
    path: str,
    *,
    timeout: int,
    transport: ProviderTransport | None = None,
    include_token: bool = True,
    extra_headers: dict[str, str] | None = None,
):
    client = ProviderJsonClient(provider, transport=transport, timeout=timeout)
    headers = {"Accept": "text/plain, application/json, */*"}
    if include_token and client.token:
        headers.update(client._token_headers(client.token))
    if extra_headers:
        headers.update(extra_headers)
    if transport:
        url = _join_url(provider.base_url, path)
        return InMemoryProviderLogLineStream(client._call_transport(url, headers, method="GET", body=None))
    return UrlopenProviderLogLineStream(
        url=_join_url(provider.base_url, path),
        headers=headers,
        timeout=timeout,
        verify_tls=client.verify_tls,
    ).open()
