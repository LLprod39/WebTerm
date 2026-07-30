from __future__ import annotations

import importlib
import importlib.util
import socketserver
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(
    not hasattr(socketserver, "UnixStreamServer"),
    reason="The validator Unix-socket server is exercised in the Linux container smoke test",
)


def _load_validator(monkeypatch):
    runner_dir = Path(__file__).resolve().parents[1] / "docker" / "ansible-runner"
    monkeypatch.syspath_prepend(str(runner_dir))
    runtime_metadata = importlib.import_module("runtime_metadata")
    digest = "sha256:" + "c" * 64
    monkeypatch.setattr(
        runtime_metadata,
        "load_runtime_metadata",
        lambda: {"runtime_digest": digest, "python": "3.12.0"},
    )
    spec = importlib.util.spec_from_file_location("webterm_ansible_validator_test", runner_dir / "validator.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validator_drops_supplementary_groups_for_syntax_child(monkeypatch):
    validator = _load_validator(monkeypatch)
    captured = {}
    monkeypatch.setattr(validator, "_write_project", lambda _root, _files: None)

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="syntax ok", stderr="")

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    result = validator._validate("playbook.yml", {"playbook.yml": b"- hosts: all\n"})

    assert result["passed"] is True
    assert captured["user"] == 10001
    assert captured["group"] == 10001
    assert captured["extra_groups"] == []


def test_validator_healthcheck_performs_live_request_and_pool_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("ANSIBLE_VALIDATOR_MAX_CONCURRENCY", "1")
    validator = _load_validator(monkeypatch)
    socket_path = tmp_path / "validator.sock"
    validator.SOCKET_PATH = str(socket_path)
    server = validator.ThreadingUnixServer(str(socket_path), validator.ValidationHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        assert validator.healthcheck() == 0
        # The client can observe EOF just before process_request_thread runs its
        # final semaphore release. Wait for that deterministic hand-off instead
        # of racing the worker thread immediately after the healthcheck.
        assert server._request_slots.acquire(timeout=1.0) is True
        assert server._request_slots.acquire(blocking=False) is False
        server._request_slots.release()
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
        socket_path.unlink(missing_ok=True)
