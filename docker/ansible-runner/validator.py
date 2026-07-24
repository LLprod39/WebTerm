"""Minimal, networkless Unix-socket service for Ansible syntax checks."""

from __future__ import annotations

import base64
import binascii
import json
import os
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path, PurePosixPath
from typing import Any

from runtime_metadata import load_runtime_metadata

SOCKET_PATH = os.environ.get("ANSIBLE_VALIDATOR_SOCKET", "/run/playbook-validator/validator.sock")
MAX_REQUEST_BYTES = 30 * 1024 * 1024
MAX_FILES = 250
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
RUNNER_UID = 10001
RUNNER_GID = 10001
MAX_CONCURRENCY = max(1, min(int(os.environ.get("ANSIBLE_VALIDATOR_MAX_CONCURRENCY", "4")), 32))
READ_TIMEOUT_SECONDS = max(1.0, min(float(os.environ.get("ANSIBLE_VALIDATOR_READ_TIMEOUT_SECONDS", "10")), 60.0))
RUNTIME_METADATA = load_runtime_metadata()


class ValidationRequestError(ValueError):
    pass


def _safe_path(raw: Any) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise ValidationRequestError("Project path is invalid")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValidationRequestError("Project path escapes its workspace")
    return path


def _decode_project(document: Any) -> tuple[str, dict[str, bytes]]:
    if not isinstance(document, dict) or not isinstance(document.get("files"), dict):
        raise ValidationRequestError("Project payload is invalid")
    entrypoint = _safe_path(document.get("entrypoint") or "playbook.yml").as_posix()
    encoded_files = document["files"]
    if not encoded_files or len(encoded_files) > MAX_FILES:
        raise ValidationRequestError("Project file count is invalid")
    files: dict[str, bytes] = {}
    total = 0
    for raw_path, encoded in encoded_files.items():
        path = _safe_path(raw_path).as_posix()
        if not isinstance(encoded, str):
            raise ValidationRequestError("Project file payload is invalid")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValidationRequestError("Project file payload is invalid") from exc
        if len(content) > MAX_FILE_BYTES:
            raise ValidationRequestError("Project file exceeds the validation limit")
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise ValidationRequestError("Project exceeds the validation limit")
        files[path] = content
    if entrypoint not in files:
        raise ValidationRequestError("Project entrypoint is missing")
    return entrypoint, files


def _write_project(root: Path, files: dict[str, bytes]) -> None:
    for relative, content in files.items():
        target = root.joinpath(*PurePosixPath(relative).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (root / "inventory.ini").write_text("localhost ansible_connection=local\n", encoding="utf-8")
    (root / "ansible.cfg").write_text(
        "[defaults]\nhost_key_checking = True\nretry_files_enabled = False\nstdout_callback = default\n",
        encoding="utf-8",
    )
    paths = [root, *root.rglob("*")]
    for path in paths:
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
    for path in reversed(paths):
        os.chown(path, RUNNER_UID, RUNNER_GID)


def _validate(entrypoint: str, files: dict[str, bytes]) -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="syntax_"))
    try:
        _write_project(root, files)
        environment = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(root),
            "LC_ALL": "C.UTF-8",
            "ANSIBLE_CONFIG": str(root / "ansible.cfg"),
            "ANSIBLE_COLLECTIONS_PATH": "/usr/share/ansible/collections",
            "ANSIBLE_FORCE_COLOR": "0",
            "ANSIBLE_NOCOLOR": "1",
            "ANSIBLE_HOST_KEY_CHECKING": "True",
            "ANSIBLE_LOCAL_TEMP": str(root / ".ansible-tmp"),
        }
        try:
            result = subprocess.run(
                ["ansible-playbook", "--syntax-check", "-i", "inventory.ini", entrypoint],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                user=RUNNER_UID,
                group=RUNNER_GID,
                extra_groups=[],
            )
        except subprocess.TimeoutExpired:
            return {"status": "failed", "passed": False, "message": "Ansible syntax check timed out"}
        output = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
        return {
            "status": "passed" if result.returncode == 0 else "failed",
            "passed": result.returncode == 0,
            "message": output[-4000:] or f"ansible-playbook exited with {result.returncode}",
            "method": "isolated-validator",
            "runtime_digest": RUNTIME_METADATA["runtime_digest"],
            "collection_setup": {"status": "not_modified", "installed": []},
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


class ValidationHandler(BaseHTTPRequestHandler):
    server_version = "WebTermAnsibleValidator/1"

    def address_string(self) -> str:
        return "local"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(READ_TIMEOUT_SECONDS)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"ok": True, "runtime": RUNTIME_METADATA})
        else:
            self._json(404, {"message": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/validate":
            self._json(404, {"message": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValidationRequestError("Validation request size is invalid")
            document = json.loads(self.rfile.read(length).decode("utf-8"))
            entrypoint, files = _decode_project(document)
            self._json(200, _validate(entrypoint, files))
        except (ValidationRequestError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._json(400, {"status": "failed", "passed": False, "message": str(exc)})
        except TimeoutError:
            self._json(408, {"status": "failed", "passed": False, "message": "Validation request timed out"})
        except Exception:
            self._json(500, {"status": "failed", "passed": False, "message": "Validation service failed"})


class ThreadingUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._request_slots = threading.BoundedSemaphore(MAX_CONCURRENCY)
        super().__init__(*args, **kwargs)

    def process_request(self, request: socket.socket, client_address: Any) -> None:
        if not self._request_slots.acquire(blocking=False):
            try:
                body = b'{"status":"failed","passed":false,"message":"Validation service is busy"}'
                request.sendall(
                    b"HTTP/1.0 503 Service Unavailable\r\nContent-Type: application/json\r\nContent-Length: "
                    + str(len(body)).encode("ascii")
                    + b"\r\nConnection: close\r\n\r\n"
                    + body
                )
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(self, request: socket.socket, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


def healthcheck() -> int:
    request = b"GET /health HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(2.0)
            connection.connect(SOCKET_PATH)
            connection.sendall(request)
            response = bytearray()
            while len(response) < 128 * 1024:
                chunk = connection.recv(8192)
                if not chunk:
                    break
                response.extend(chunk)
    except (OSError, TimeoutError):
        return 1
    header, _, body = bytes(response).partition(b"\r\n\r\n")
    if not header.startswith(b"HTTP/") or b" 200 " not in header.split(b"\r\n", 1)[0]:
        return 1
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 1
    if not isinstance(payload, dict):
        return 1
    runtime = payload.get("runtime")
    return 0 if payload.get("ok") is True and isinstance(runtime, dict) and runtime.get("runtime_digest") else 1


def main() -> None:
    socket_path = Path(SOCKET_PATH)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists() or socket_path.is_socket():
        socket_path.unlink()
    with ThreadingUnixServer(str(socket_path), ValidationHandler) as server:
        os.chmod(socket_path, 0o600)
        server.serve_forever(poll_interval=0.25)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--healthcheck":
        raise SystemExit(healthcheck())
    main()
