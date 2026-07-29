"""Fail-closed authentication and container isolation for the MCP Runner."""

from pathlib import Path

import pytest
import yaml

from mcp_runner.config import RunnerConfig
from mcp_runner.security import RunnerAuthError, authorize_request, public_health_payload

ROOT = Path(__file__).resolve().parents[1]


def _load_compose(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def test_runner_config_rejects_missing_startup_token(monkeypatch):
    monkeypatch.delenv("MCP_RUNNER_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="MCP_RUNNER_TOKEN"):
        RunnerConfig().validate_startup()


def test_runner_auth_dependency_fails_closed_without_token():
    with pytest.raises(RunnerAuthError) as exc_info:
        authorize_request("", None)

    assert exc_info.value.status_code == 503


def test_runner_auth_dependency_accepts_only_exact_bearer_token():
    with pytest.raises(RunnerAuthError) as exc_info:
        authorize_request("runner-test-secret", "Bearer wrong")
    assert exc_info.value.status_code == 401

    assert authorize_request("runner-test-secret", "Bearer runner-test-secret") is None


def test_runner_health_does_not_disclose_session_identifiers():
    payload = public_health_payload(
        {
            "sessions": 1,
            "max_sessions": 50,
            "items": [{"session": "sensitive-session", "server": "internal-server"}],
        }
    )

    assert payload == {"ok": True, "service": "mcp-runner", "sessions": 1, "max_sessions": 50}


def test_production_runner_is_fail_closed_and_least_privileged():
    compose = _load_compose("docker-compose.production.yml")
    runner = compose["services"]["mcp-runner"]

    assert runner["environment"]["MCP_RUNNER_TOKEN"].startswith("${STUDIO_MCP_RUNNER_TOKEN:?")
    assert runner["user"] == "10001:10001"
    assert runner["read_only"] is True
    assert runner["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in runner["security_opt"]
    assert runner["pids_limit"] == 256
    assert any(item.startswith("/tmp:") for item in runner["tmpfs"])
    assert any(item.startswith("/app/.cache:") for item in runner["tmpfs"])


def test_local_runner_is_loopback_only_and_least_privileged():
    compose = _load_compose("docker-compose.postgres-mcp.yml")
    runner = compose["services"]["mcp-runner"]

    assert runner["environment"]["MCP_RUNNER_TOKEN"].startswith("${STUDIO_MCP_RUNNER_TOKEN:?")
    assert runner["ports"] == ["${MCP_RUNNER_BIND_HOST:-127.0.0.1}:${MCP_RUNNER_PORT:-9100}:9000"]
    assert runner["user"] == "10001:10001"
    assert runner["read_only"] is True
    assert runner["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in runner["security_opt"]


def test_runner_image_drops_root_privileges():
    dockerfile = (ROOT / "docker" / "mcp-runner.Dockerfile").read_text(encoding="utf-8")

    assert "USER 10001:10001" in dockerfile
