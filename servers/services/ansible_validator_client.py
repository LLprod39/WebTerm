"""Unix-socket client for the secret-free production Ansible validator."""

from __future__ import annotations

import base64
import http.client
import json
import os
import re
import socket
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class AnsibleValidatorError(RuntimeError):
    pass


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float = 65.0) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        connection.connect(self.socket_path)
        self.sock = connection


def validator_socket_path() -> str:
    return (os.environ.get("WEBTERM_ANSIBLE_VALIDATOR_SOCKET") or "").strip()


def validator_runtime_available() -> bool:
    try:
        validator_runtime_metadata()
    except AnsibleValidatorError:
        return False
    return True


def _request_json(
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    timeout: float = 65.0,
    response_limit: int = 128 * 1024,
) -> dict[str, Any]:
    socket_path = validator_socket_path()
    if not socket_path or not Path(socket_path).is_socket():
        raise AnsibleValidatorError("Isolated Ansible validator is unavailable")
    headers = {"Content-Length": str(len(body))} if body is not None else {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    connection = _UnixHTTPConnection(socket_path, timeout=timeout)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        response_body = response.read(response_limit)
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise AnsibleValidatorError("Isolated Ansible validator is unavailable") from exc
    finally:
        connection.close()
    try:
        document = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnsibleValidatorError("Isolated Ansible validator returned an invalid response") from exc
    if response.status != 200 or not isinstance(document, dict):
        message = str(document.get("message") or "") if isinstance(document, dict) else ""
        raise AnsibleValidatorError(message or "Isolated Ansible validator request failed")
    return document


def validator_runtime_metadata() -> dict[str, Any]:
    document = _request_json("GET", "/health", timeout=5.0)
    runtime = document.get("runtime")
    digest = runtime.get("runtime_digest") if isinstance(runtime, dict) else None
    if (
        document.get("ok") is not True
        or not isinstance(digest, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    ):
        raise AnsibleValidatorError("Isolated Ansible validator returned invalid runtime metadata")
    return runtime


def validate_with_isolated_service(
    playbook_yaml: str,
    *,
    project_files: Mapping[str, bytes] | None = None,
    project_entrypoint: str = "playbook.yml",
) -> dict[str, Any]:
    files = dict(project_files or {})
    files[project_entrypoint] = playbook_yaml.encode("utf-8")
    payload = json.dumps(
        {
            "entrypoint": project_entrypoint,
            "files": {path: base64.b64encode(content).decode("ascii") for path, content in files.items()},
        },
        separators=(",", ":"),
    ).encode("utf-8")
    if len(payload) > 30 * 1024 * 1024:
        raise AnsibleValidatorError("Ansible validation project exceeds the request limit")

    return _request_json("POST", "/validate", body=payload, response_limit=64 * 1024)
