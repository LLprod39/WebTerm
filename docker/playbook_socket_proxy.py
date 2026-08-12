"""Minimal body-aware HTTP proxy from TCP to the host Docker Unix socket."""

from __future__ import annotations

import http.client
import json
import os
import selectors
import socket
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

SOCKET_PATH = os.getenv("DOCKER_SOCKET_PATH", "/var/run/docker.sock")
POLICY_KIND = os.getenv("DOCKER_PROXY_POLICY", "playbook").strip().lower()
LISTEN_HOST = os.getenv("DOCKER_PROXY_HOST", os.getenv("PLAYBOOK_DOCKER_PROXY_HOST", "0.0.0.0"))
LISTEN_PORT = int(os.getenv("DOCKER_PROXY_PORT", os.getenv("PLAYBOOK_DOCKER_PROXY_PORT", "2375")))
MAX_REQUEST_BODY = 1024 * 1024
if POLICY_KIND == "agent-command":
    from agent_command_socket_proxy_policy import (
        AgentCommandProxyPolicyConfig,
        authorize_agent_command_docker_request,
    )

    POLICY_CONFIG = AgentCommandProxyPolicyConfig(
        runner_image=os.environ["AGENT_COMMAND_RUNNER_IMAGE"],
        network=os.getenv("AGENT_COMMAND_DOCKER_NETWORK", "bridge"),
        ssh_agent_socket=os.getenv("AGENT_COMMAND_SSH_AUTH_SOCK", ""),
    )
    authorize_docker_request = authorize_agent_command_docker_request
elif POLICY_KIND == "ai-cli":
    from ai_cli_socket_proxy_policy import AiCliProxyPolicyConfig, authorize_ai_cli_docker_request

    POLICY_CONFIG = AiCliProxyPolicyConfig(
        codex_runner_image=os.environ["AI_CLI_CODEX_RUNNER_IMAGE"],
        grok_runner_image=os.environ["AI_CLI_GROK_RUNNER_IMAGE"],
        egress_network=os.environ["AI_CLI_DOCKER_NETWORK"],
        credential_volume_prefix=os.getenv("AI_CLI_CREDENTIAL_VOLUME_PREFIX", "webterm-ai-cli-cred-"),
        egress_proxy_url=os.getenv("AI_CLI_EGRESS_PROXY_URL", "http://ai-cli-egress-proxy:3128"),
    )
    authorize_docker_request = authorize_ai_cli_docker_request
elif POLICY_KIND == "plugin-backend":
    from plugin_backend_socket_proxy_policy import (
        PluginBackendProxyPolicyConfig,
        authorize_plugin_backend_docker_request,
    )

    POLICY_CONFIG = PluginBackendProxyPolicyConfig(
        runner_image=os.environ["PLUGIN_BACKEND_RUNNER_IMAGE"],
        egress_network=os.getenv("PLUGIN_BACKEND_DOCKER_EGRESS_NETWORK", ""),
    )
    authorize_docker_request = authorize_plugin_backend_docker_request
elif POLICY_KIND == "playbook":
    from playbook_socket_proxy_policy import ProxyPolicyConfig, authorize_docker_request

    POLICY_CONFIG = ProxyPolicyConfig(
        runtime_volume=os.environ["PLAYBOOK_RUNTIME_VOLUME_NAME"],
        network=os.getenv("WEBTERM_ANSIBLE_DOCKER_NETWORK", "bridge"),
        host_alias=os.getenv("WEBTERM_ANSIBLE_DOCKER_HOST_ALIAS", "host.docker.internal"),
        runner_image=os.getenv("WEBTERM_ANSIBLE_IMAGE", "webterm-ansible:latest"),
    )
else:
    raise RuntimeError(f"Unsupported Docker proxy policy: {POLICY_KIND}")


class UnixHTTPConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(SOCKET_PATH)


def inspect_container(identifier: str) -> dict | None:
    connection = UnixHTTPConnection("localhost", timeout=5)
    try:
        connection.request("GET", f"/containers/{quote(identifier, safe='')}/json", headers={"Connection": "close"})
        response = connection.getresponse()
        body = response.read(MAX_REQUEST_BODY + 1)
        if response.status == 404:
            return None
        if response.status != 200 or len(body) > MAX_REQUEST_BODY:
            raise RuntimeError(f"Docker inspect failed with status {response.status}")
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Docker inspect returned an invalid body")
        return payload
    finally:
        connection.close()


def _relay_bidirectional(client: socket.socket, backend: socket.socket) -> None:
    selector = selectors.DefaultSelector()
    selector.register(client, selectors.EVENT_READ, backend)
    selector.register(backend, selectors.EVENT_READ, client)
    active = {client, backend}
    try:
        while active:
            events = selector.select(timeout=300)
            if not events:
                return
            for key, _mask in events:
                data = key.fileobj.recv(65536)
                if not data:
                    selector.unregister(key.fileobj)
                    active.discard(key.fileobj)
                    with suppress(OSError):
                        key.data.shutdown(socket.SHUT_WR)
                    continue
                key.data.sendall(data)
    finally:
        selector.close()


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "WebTermFilteredDockerProxy/1"

    def _body(self) -> bytes:
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("chunked request bodies are not supported")
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length < 0 or length > MAX_REQUEST_BODY:
            raise ValueError("request body is too large")
        return self.rfile.read(length) if length else b""

    def _health(self) -> bool:
        if self.command != "GET" or self.path != "/health":
            return False
        try:
            connection = UnixHTTPConnection("localhost", timeout=2)
            connection.request("GET", "/_ping", headers={"Connection": "close"})
            response = connection.getresponse()
            healthy = response.status == 200 and response.read(16).strip() == b"OK"
            connection.close()
        except (OSError, http.client.HTTPException):
            healthy = False
        body = b'{"status":"ok"}' if healthy else b'{"status":"unavailable"}'
        self.send_response(200 if healthy else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True
        return True

    def _proxy(self) -> None:
        if self._health():
            return
        try:
            body = self._body()
        except (ValueError, TypeError) as exc:
            self.send_error(413, str(exc))
            return
        decision = authorize_docker_request(
            self.command,
            self.path,
            body,
            config=POLICY_CONFIG,
            inspect_container=inspect_container,
        )
        if not decision.allowed:
            self.send_error(403, decision.reason)
            return

        backend = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        backend.settimeout(300)
        response_started = False
        try:
            backend.connect(SOCKET_PATH)
            upgrade = self.headers.get("Upgrade", "").strip()
            headers = []
            for key, value in self.headers.items():
                if key.lower() in {"host", "connection", "proxy-connection", "content-length"}:
                    continue
                headers.append(f"{key}: {value}\r\n")
            headers.append("Host: localhost\r\n")
            headers.append(f"Content-Length: {len(body)}\r\n")
            headers.append(f"Connection: {'Upgrade' if upgrade else 'close'}\r\n")
            request = f"{self.command} {self.path} HTTP/1.1\r\n{''.join(headers)}\r\n".encode("latin-1") + body
            backend.sendall(request)

            response_head = bytearray()
            while b"\r\n\r\n" not in response_head:
                chunk = backend.recv(4096)
                if not chunk or len(response_head) + len(chunk) > 65536:
                    raise RuntimeError("invalid Docker API response")
                response_head.extend(chunk)
            head, remainder = bytes(response_head).split(b"\r\n\r\n", 1)
            response_started = True
            self.connection.sendall(head + b"\r\n\r\n" + remainder)
            status_line = head.split(b"\r\n", 1)[0]
            if b" 101 " in status_line:
                _relay_bidirectional(self.connection, backend)
            else:
                while True:
                    chunk = backend.recv(65536)
                    if not chunk:
                        break
                    self.connection.sendall(chunk)
        except (OSError, RuntimeError) as exc:
            if not response_started:
                self.send_error(502, str(exc))
            else:
                self.log_error("Docker API relay failed: %s", exc)
        finally:
            backend.close()
            self.close_connection = True

    do_DELETE = _proxy
    do_GET = _proxy
    do_HEAD = _proxy
    do_POST = _proxy

    def log_message(self, format: str, *args) -> None:
        print(f"filtered-docker-proxy policy={POLICY_KIND} client={self.client_address[0]} {format % args}", flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), ProxyHandler)
    server.daemon_threads = True
    server.serve_forever()
