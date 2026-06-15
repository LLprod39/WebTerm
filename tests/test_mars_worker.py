import asyncio
import sys
import textwrap

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from mars.models import MarsRun, MarsSession
from mars.services import build_mars_agent_docker_command, ensure_personal_workspace
from mars.worker import execute_mars_run


@pytest.mark.django_db(transaction=True)
def test_mars_worker_completes_run_with_fake_codex_and_gemini(tmp_path):
    codex_script = tmp_path / "fake_codex.py"
    codex_script.write_text(
        textwrap.dedent(
            """
            import pathlib
            import sys

            sys.stdin.read()
            output_path = pathlib.Path(sys.argv[sys.argv.index("--output-last-message") + 1])
            output_path.write_text("Codex final answer", encoding="utf-8")
            print('{"type":"message","content":"codex stream"}')
            """
        ),
        encoding="utf-8",
    )
    gemini_script = tmp_path / "fake_gemini.py"
    gemini_script.write_text(
        "print('{\"type\":\"review\",\"content\":\"Gemini review ok\"}')\n",
        encoding="utf-8",
    )

    user = User.objects.create_user(username="worker-mars", password="x")

    with override_settings(
        MARS_CODEX_COMMAND=[sys.executable, str(codex_script)],
        MARS_GEMINI_COMMAND=[sys.executable, str(gemini_script)],
        MARS_USER_WORKSPACES_ROOT=tmp_path / "mars_workspaces",
        MARS_CODEX_TIMEOUT_SECONDS=20,
        MARS_GEMINI_TIMEOUT_SECONDS=20,
        MEDIA_ROOT=tmp_path / "media",
    ):
        workspace = ensure_personal_workspace(user)
        session = MarsSession.objects.create(
            user=user,
            workspace=workspace,
            task_brief="Update UI",
            selected_skill_slugs=["frontend-dev"],
            generated_plan="# Plan",
            status=MarsSession.STATUS_APPROVED,
        )
        run = MarsRun.objects.create(user=user, workspace=workspace, session=session)
        asyncio.run(execute_mars_run(run.id))

    run.refresh_from_db()
    assert run.status == MarsRun.STATUS_COMPLETED
    assert "Codex final answer" in run.codex_summary
    assert "Gemini review ok" in run.gemini_review
    assert run.events.filter(event_type="codex_started").exists()
    assert run.events.filter(event_type="gemini_finished").exists()


def test_mars_docker_command_mounts_only_user_workspace(tmp_path):
    workspace = tmp_path / "mars_workspaces" / "user_42"
    workspace.mkdir(parents=True)
    unrelated_server_root = tmp_path / "server_root"
    unrelated_server_root.mkdir()

    with override_settings(
        MARS_AGENT_DOCKER_IMAGE="mars-agent:test",
        MARS_AGENT_DOCKER_NETWORK="bridge",
        MARS_AGENT_DOCKER_CPUS="",
        MARS_AGENT_DOCKER_MEMORY="",
        MARS_AGENT_DOCKER_PIDS_LIMIT=0,
        MARS_DOCKER_CONTAINER_PATH_PREFIX="",
        MARS_DOCKER_HOST_PATH_PREFIX="",
    ):
        command = build_mars_agent_docker_command(
            phase="codex-42",
            workspace_root=workspace,
            workspace_mode="rw",
            inner_command=["codex", "exec", "-"],
        )

    volume_args = [command[index + 1] for index, item in enumerate(command) if item == "-v"]
    assert f"{workspace.resolve()}:/workspace:rw" in volume_args
    assert str(unrelated_server_root.resolve()) not in " ".join(command)
    assert "--cap-drop" in command
    assert "ALL" in command
    assert "no-new-privileges:true" in command
    image_index = command.index("mars-agent:test")
    assert command[image_index + 1 :] == ["codex", "exec", "-"]
