from __future__ import annotations

from typing import Any

from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.provider_clients import ProviderJsonClient, ProviderTransport, _join_url
from kubernetes_ops.services.provider_exec_streams import InMemoryProviderExecStream, UrlopenProviderExecStream

MAX_PROVIDER_INTERACTIVE_SHELL_BYTES = 1024 * 1024


def open_provider_interactive_shell_stream(
    provider: K8sProvider,
    path: str,
    *,
    timeout: int,
    operation: str,
    target: dict[str, Any],
    stdin: bool = True,
    tty: bool = True,
    transport: ProviderTransport | None = None,
):
    client = ProviderJsonClient(provider, transport=transport, timeout=timeout)
    headers = {"Accept": "application/json, text/plain, */*"}
    if client.token:
        headers.update(client._token_headers(client.token))
    body = {
        "operation": str(operation or ""),
        "target": dict(target or {}),
        "stdin": bool(stdin),
        "tty": bool(tty),
    }
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
