from kubernetes_ops.models import K8sProvider
from kubernetes_ops.services.provider_clients import (
    _decode_json_payload,
    _decode_log_payload,
    _default_log_stream_lines,
)
from kubernetes_ops.services.provider_exec_streams import open_provider_exec_stream
from kubernetes_ops.services.provider_log_streams import open_provider_log_line_stream
from kubernetes_ops.services.provider_port_forward_tunnels import open_provider_port_forward_tunnel
from kubernetes_ops.services.provider_watch_streams import open_provider_watch_event_stream


class _FakeLineResponse:
    def __init__(self, lines: list[bytes]):
        self.lines = list(lines)
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def readline(self, limit: int = -1):
        if not self.lines:
            return b""
        value = self.lines.pop(0)
        if limit >= 0 and len(value) > limit:
            self.lines.insert(0, value[limit:])
            return value[:limit]
        return value

    def close(self):
        self.closed = True


def test_provider_client_decodes_multi_event_sse_payload_as_items():
    payload = _decode_json_payload(
        b'data: {"type":"ADDED","object":{"metadata":{"name":"pod-a","resourceVersion":"10"}}}\n\n'
        b'data: {"type":"MODIFIED","object":{"metadata":{"name":"pod-a","resourceVersion":"11"}}}\n\n'
        b"data: [DONE]\n\n"
    )

    assert list(payload) == ["items"]
    assert len(payload["items"]) == 2
    assert payload["items"][0]["type"] == "ADDED"
    assert payload["items"][1]["object"]["metadata"]["resourceVersion"] == "11"


def test_provider_client_decodes_kubernetes_ndjson_watch_payload_as_items():
    payload = _decode_json_payload(
        b'{"type":"ADDED","object":{"metadata":{"name":"deploy-a","resourceVersion":"42"}}}\n'
        b'{"type":"BOOKMARK","object":{"metadata":{"resourceVersion":"43"}}}\n'
    )

    assert len(payload["items"]) == 2
    assert payload["items"][0]["object"]["metadata"]["name"] == "deploy-a"
    assert payload["items"][1]["type"] == "BOOKMARK"


def test_provider_client_preserves_single_sse_object_shape():
    payload = _decode_json_payload(b'data: {"type":"ADDED","object":{"metadata":{"resourceVersion":"7"}}}\n\n')

    assert payload["type"] == "ADDED"
    assert payload["object"]["metadata"]["resourceVersion"] == "7"


def test_provider_client_wraps_plain_text_logs_as_content():
    payload = _decode_log_payload(b"line one\npassword=raw-secret\nlast line\n")

    assert payload == {"content": "line one\npassword=raw-secret\nlast line\n"}


def test_provider_client_keeps_json_log_payload_shape():
    payload = _decode_log_payload(b'{"lines":["line one","line two"]}')

    assert payload == {"lines": ["line one", "line two"]}


def test_default_log_stream_lines_not_truncated_when_stream_ends_at_limit(monkeypatch):
    def fake_urlopen(*args, **kwargs):
        return _FakeLineResponse([b"one\n", b"two\n"])

    monkeypatch.setattr("kubernetes_ops.services.provider_clients.urllib.request.urlopen", fake_urlopen)

    lines, truncated = _default_log_stream_lines(
        "https://rancher.example.test/log",
        {},
        5,
        verify_tls=True,
        max_lines=2,
        max_bytes=100,
    )

    assert lines == ["one", "two"]
    assert truncated is False


def test_default_log_stream_lines_truncated_when_more_lines_exist(monkeypatch):
    def fake_urlopen(*args, **kwargs):
        return _FakeLineResponse([b"one\n", b"two\n", b"three\n"])

    monkeypatch.setattr("kubernetes_ops.services.provider_clients.urllib.request.urlopen", fake_urlopen)

    lines, truncated = _default_log_stream_lines(
        "https://rancher.example.test/log",
        {},
        5,
        verify_tls=True,
        max_lines=2,
        max_bytes=100,
    )

    assert lines == ["one", "two"]
    assert truncated is True


def test_provider_log_line_stream_reads_batches_from_one_response(monkeypatch):
    response = _FakeLineResponse([b"one\n", b"two\n", b"three\n"])
    calls = []

    def fake_urlopen(*args, **kwargs):
        calls.append((args, kwargs))
        return response

    monkeypatch.setattr("kubernetes_ops.services.provider_log_streams.urllib.request.urlopen", fake_urlopen)
    provider = K8sProvider(name="rancher-stream", kind=K8sProvider.KIND_RANCHER, base_url="https://rancher.example.test", auth_mode=K8sProvider.AUTH_NONE)

    stream = open_provider_log_line_stream(provider, "/log?follow=1", timeout=5)
    first = stream.read_batch(max_lines=2, max_bytes=100)
    second = stream.read_batch(max_lines=2, max_bytes=100)
    third = stream.read_batch(max_lines=2, max_bytes=100)
    stream.close()

    assert len(calls) == 1
    assert first.lines == ["one", "two"]
    assert first.eof is False
    assert second.lines == ["three"]
    assert second.eof is True
    assert third.lines == []
    assert third.eof is True
    assert response.closed is True


def test_provider_watch_event_stream_reads_sse_batches_from_one_response(monkeypatch):
    response = _FakeLineResponse(
        [
            b'data: {"type":"ADDED","object":{"metadata":{"name":"pod-a","resourceVersion":"10"}}}\n',
            b"\n",
            b'data: {"type":"BOOKMARK","object":{"metadata":{"resourceVersion":"11"}}}\n',
            b"\n",
            b'{"type":"MODIFIED","object":{"metadata":{"name":"pod-a","resourceVersion":"12"}}}\n',
        ]
    )
    calls = []

    def fake_urlopen(*args, **kwargs):
        calls.append((args, kwargs))
        return response

    monkeypatch.setattr("kubernetes_ops.services.provider_watch_streams.urllib.request.urlopen", fake_urlopen)
    provider = K8sProvider(name="rancher-watch-stream", kind=K8sProvider.KIND_RANCHER, base_url="https://rancher.example.test", auth_mode=K8sProvider.AUTH_NONE)

    stream = open_provider_watch_event_stream(provider, "/watch?watch=1", timeout=5)
    first = stream.read_batch(max_events=2, max_bytes=1000)
    second = stream.read_batch(max_events=2, max_bytes=1000)
    third = stream.read_batch(max_events=2, max_bytes=1000)
    stream.close()

    assert len(calls) == 1
    assert [event["type"] for event in first.events] == ["ADDED", "BOOKMARK"]
    assert first.eof is False
    assert [event["type"] for event in second.events] == ["MODIFIED"]
    assert second.eof is True
    assert third.events == []
    assert third.eof is True
    assert response.closed is True


def test_provider_exec_stream_posts_command_and_reads_json_events(monkeypatch):
    response = _FakeLineResponse(
        [
            b'{"stream":"stdout","data":"hello"}\n',
            b'{"stream":"stderr","data":"warn"}\n',
            b'{"stream":"status","exit_code":0}\n',
        ]
    )
    seen = {}

    def fake_urlopen(request, *args, **kwargs):
        seen["method"] = request.get_method()
        seen["body"] = request.data
        return response

    monkeypatch.setattr("kubernetes_ops.services.provider_exec_streams.urllib.request.urlopen", fake_urlopen)
    provider = K8sProvider(name="rancher-exec-stream", kind=K8sProvider.KIND_RANCHER, base_url="https://rancher.example.test", auth_mode=K8sProvider.AUTH_NONE)

    stream = open_provider_exec_stream(provider, "/exec", timeout=5, command=["env"], container="api", tty=False, stdin=False)
    first = stream.read_event(max_bytes=1000)
    second = stream.read_event(max_bytes=1000)
    third = stream.read_event(max_bytes=1000)
    stream.close()

    assert seen["method"] == "POST"
    assert b'"command": ["env"]' in seen["body"]
    assert first.stream == "stdout"
    assert first.data == "hello"
    assert second.stream == "stderr"
    assert second.data == "warn"
    assert third.stream == "status"
    assert third.exit_code == 0
    assert third.eof is True
    assert response.closed is True


def test_provider_port_forward_tunnel_posts_target_and_reads_base64_chunks(monkeypatch):
    response = _FakeLineResponse(
        [
            b'{"encoding":"base64","data":"SFRUUC8xLjEgMjAwIE9LDQo="}\n',
            b'{"eof":true}\n',
        ]
    )
    seen = {}

    def fake_urlopen(request, *args, **kwargs):
        seen["method"] = request.get_method()
        seen["body"] = request.data
        return response

    monkeypatch.setattr("kubernetes_ops.services.provider_port_forward_tunnels.urllib.request.urlopen", fake_urlopen)
    provider = K8sProvider(name="rancher-port-forward", kind=K8sProvider.KIND_RANCHER, base_url="https://rancher.example.test", auth_mode=K8sProvider.AUTH_NONE)

    stream = open_provider_port_forward_tunnel(
        provider,
        "/portforward",
        timeout=5,
        target={"namespace": "payments", "kind": "Service", "name": "payments-api", "remote_port": 8080},
        duration_seconds=120,
    )
    first = stream.read_event(max_bytes=1000)
    second = stream.read_event(max_bytes=1000)
    stream.close()

    assert seen["method"] == "POST"
    assert b'"duration_seconds": 120' in seen["body"]
    assert b'"remote_port": 8080' in seen["body"]
    assert first.data == b"HTTP/1.1 200 OK\r\n"
    assert second.eof is True
    assert response.closed is True
