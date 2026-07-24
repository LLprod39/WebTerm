import json
import socketserver
import threading

import pytest

from servers.services.ansible_validator_client import (
    validate_with_isolated_service,
    validator_runtime_available,
    validator_runtime_metadata,
)

DIGEST = "sha256:" + "b" * 64


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        headers = {}
        request_line = self.rfile.readline()
        assert request_line.startswith(b"POST /validate")
        while True:
            line = self.rfile.readline()
            if line in {b"\r\n", b""}:
                break
            key, _, value = line.decode("ascii").partition(":")
            headers[key.lower()] = value.strip()
        payload = json.loads(self.rfile.read(int(headers["content-length"])))
        assert payload["entrypoint"] == "playbook.yml"
        body = b'{"status":"passed","passed":true,"method":"isolated-validator"}'
        self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)


class _HealthHandler(socketserver.StreamRequestHandler):
    def handle(self):
        assert self.rfile.readline().startswith(b"GET /health")
        while self.rfile.readline() not in {b"\r\n", b""}:
            pass
        body = json.dumps({"ok": True, "runtime": {"runtime_digest": DIGEST, "python": "3.12.0"}}).encode()
        self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)


def test_validator_client_uses_unix_socket(tmp_path, monkeypatch):
    if not hasattr(socketserver, "UnixStreamServer"):
        pytest.skip("Unix-domain sockets are exercised by the Linux Compose smoke")
    socket_path = tmp_path / "validator.sock"
    server = socketserver.UnixStreamServer(str(socket_path), _Handler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    monkeypatch.setenv("WEBTERM_ANSIBLE_VALIDATOR_SOCKET", str(socket_path))
    try:
        result = validate_with_isolated_service("- hosts: all\n")
    finally:
        thread.join(timeout=2)
        server.server_close()

    assert result["passed"] is True


def test_validator_health_is_a_real_request_with_runtime_metadata(tmp_path, monkeypatch):
    if not hasattr(socketserver, "UnixStreamServer"):
        pytest.skip("Unix-domain sockets are exercised by the Linux Compose smoke")
    socket_path = tmp_path / "validator.sock"
    server = socketserver.UnixStreamServer(str(socket_path), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    monkeypatch.setenv("WEBTERM_ANSIBLE_VALIDATOR_SOCKET", str(socket_path))
    try:
        assert validator_runtime_metadata()["runtime_digest"] == DIGEST
        assert validator_runtime_available() is True
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
