from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from core_ui.models import UserAppPermission
from mars.models import MarsRun, MarsSession
from mars.policy import MarsPolicyError
from mars.runtime_cli import build_mars_agent_docker_command, mars_agent_uses_docker
from mars.services import create_run_for_session, ensure_personal_workspace
from mars.worker_phases import _run_verification


@pytest.mark.django_db
def test_mars_rejects_arbitrary_verification_command_before_queue(tmp_path: Path) -> None:
    user = User.objects.create_user(username="mars-verification-policy", password="x")
    with override_settings(MARS_USER_WORKSPACES_ROOT=tmp_path / "workspaces"):
        workspace = ensure_personal_workspace(user)
        session = MarsSession.objects.create(
            user=user,
            workspace=workspace,
            task_brief="Verify safely",
            generated_plan="# Plan",
            status=MarsSession.STATUS_APPROVED,
        )

        with pytest.raises(MarsPolicyError, match="verification profile"):
            create_run_for_session(
                session,
                allow_dirty=True,
                test_command="python -c 'import os; print(os.environ)'",
            )

    assert MarsRun.objects.filter(session=session).count() == 0


@pytest.mark.django_db
def test_mars_api_rejects_arbitrary_verification_command_without_queueing(tmp_path: Path) -> None:
    user = User.objects.create_user(username="mars-verification-api", password="x")
    UserAppPermission.objects.create(user=user, feature="mars", allowed=True)
    client = Client()
    client.force_login(user)

    with override_settings(MARS_USER_WORKSPACES_ROOT=tmp_path / "workspaces"):
        workspace = ensure_personal_workspace(user)
        session = MarsSession.objects.create(
            user=user,
            workspace=workspace,
            task_brief="Verify safely",
            generated_plan="# Plan",
            status=MarsSession.STATUS_APPROVED,
        )
        response = client.post(
            f"/api/mars/sessions/{session.id}/run/",
            data=json.dumps({"allow_dirty": True, "test_command": "bash -c 'id'"}),
            content_type="application/json",
        )

    assert response.status_code == 400
    assert "verification profile" in response.json()["error"]
    assert MarsRun.objects.filter(session=session).count() == 0


@pytest.mark.django_db
def test_mars_stores_only_approved_verification_profile(tmp_path: Path) -> None:
    user = User.objects.create_user(username="mars-verification-profile", password="x")
    with override_settings(MARS_USER_WORKSPACES_ROOT=tmp_path / "workspaces"):
        workspace = ensure_personal_workspace(user)
        session = MarsSession.objects.create(
            user=user,
            workspace=workspace,
            task_brief="Build frontend",
            generated_plan="# Plan",
            status=MarsSession.STATUS_APPROVED,
        )
        run = create_run_for_session(session, allow_dirty=True, test_command="npm run build")

    assert run.runtime_control["verification_profile"] == "frontend-build"
    assert "test_command" not in run.runtime_control


def test_mars_host_runtime_is_fail_closed() -> None:
    with (
        override_settings(MARS_AGENT_RUNTIME="host", MARS_ALLOW_UNSAFE_HOST_RUNTIME_FOR_TESTS=False),
        pytest.raises(MarsPolicyError, match="isolated Docker runtime"),
    ):
        mars_agent_uses_docker()


def test_mars_verification_container_has_no_network_or_provider_keys(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "provider-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "provider-secret")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy-user:proxy-secret@proxy.invalid:8080")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with override_settings(
        MARS_AGENT_DOCKER_IMAGE="mars-agent@sha256:" + "a" * 64,
        MARS_AGENT_DOCKER_NETWORK="bridge",
        MARS_AGENT_DOCKER_CPUS="",
        MARS_AGENT_DOCKER_MEMORY="",
        MARS_AGENT_DOCKER_PIDS_LIMIT=0,
    ):
        command = build_mars_agent_docker_command(
            phase="verify-1",
            workspace_root=workspace,
            workspace_mode="rw",
            inner_command=["npm", "run", "build"],
        )

    network_index = command.index("--network")
    assert command[network_index + 1] == "none"
    assert "OPENAI_API_KEY" not in command
    assert "GEMINI_API_KEY" not in command
    assert "HTTPS_PROXY" not in command


def test_mars_ai_container_requires_explicit_network_and_credentials_opt_in(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "provider-secret")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with override_settings(
        MARS_AGENT_DOCKER_IMAGE="mars-agent@sha256:" + "a" * 64,
        MARS_AGENT_DOCKER_NETWORK="mars-egress",
        MARS_AGENT_DOCKER_CPUS="",
        MARS_AGENT_DOCKER_MEMORY="",
        MARS_AGENT_DOCKER_PIDS_LIMIT=0,
    ):
        command = build_mars_agent_docker_command(
            phase="codex-1",
            workspace_root=workspace,
            workspace_mode="rw",
            inner_command=["codex", "exec", "-"],
            allow_network=True,
            include_provider_credentials=True,
        )

    network_index = command.index("--network")
    assert command[network_index + 1] == "mars-egress"
    assert command[command.index("OPENAI_API_KEY") - 1] == "-e"


@pytest.mark.asyncio
async def test_mars_worker_rejects_legacy_free_form_command_before_process_spawn(tmp_path: Path, monkeypatch) -> None:
    async def forbidden_spawn(*_args, **_kwargs):
        raise AssertionError("unapproved verification must not spawn a process")

    monkeypatch.setattr("mars.worker_phases._stream_process", forbidden_spawn)

    with pytest.raises(MarsPolicyError, match="verification profile"):
        await _run_verification(
            SimpleNamespace(id=7),
            workspace_root=tmp_path,
            docker_runtime=True,
            verification_profile="bash -c 'id'",
            event_prefix="tests",
        )
