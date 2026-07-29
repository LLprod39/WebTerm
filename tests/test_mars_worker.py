import asyncio
import pathlib
import sys
import textwrap

import pytest
from django.contrib.auth.models import User
from django.test import override_settings

from mars.models import MarsRun, MarsSession
from mars.orchestrator import ORCHESTRATION_STRATEGY, review_requests_changes
from mars.services import build_mars_agent_docker_command, ensure_personal_workspace
from mars.worker import execute_mars_run


def test_mars_orchestrator_detects_gemini_stream_json_review_status():
    assert review_requests_changes('{"type":"review","content":"STATUS: needs_changes\\nFix missing tests"}')
    assert not review_requests_changes('{"type":"review","content":"STATUS: pass\\nLooks good"}')


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
        'print(\'{"type":"review","content":"Gemini review ok"}\')\n',
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
    assert run.cli_roles == {
        "orchestrator": "mars",
        "architect": "gemini",
        "executor": "codex",
        "repair": "codex",
        "reviewer": "gemini",
        "verifier": "system",
    }
    assert run.runtime_control["orchestration"]["strategy"] == ORCHESTRATION_STRATEGY
    assert run.runtime_control["orchestration"]["skill_routing"]["executor"] == ["frontend-dev"]
    assert run.runtime_control["orchestration"]["skill_routing"]["repair"] == ["frontend-dev"]
    assert "# MARS orchestration final report" in run.final_report
    assert run.events.filter(event_type="orchestrator_started").exists()
    assert run.events.filter(event_type="gemini_architect_started").exists()
    assert run.events.filter(event_type="codex_started").exists()
    assert run.events.filter(event_type="gemini_finished").exists()


@pytest.mark.django_db(transaction=True)
def test_mars_worker_routes_failed_verification_to_codex_repair(tmp_path):
    codex_script = tmp_path / "fake_codex_repair.py"
    codex_script.write_text(
        textwrap.dedent(
            """
            import pathlib
            import sys

            sys.stdin.read()
            output_path = pathlib.Path(sys.argv[sys.argv.index("--output-last-message") + 1])
            workspace_root = pathlib.Path(sys.argv[sys.argv.index("--cd") + 1])
            if "repair" in output_path.name:
                (workspace_root / "repair.ok").write_text("fixed", encoding="utf-8")
                output_path.write_text("Codex repair answer", encoding="utf-8")
            else:
                output_path.write_text("Codex initial answer", encoding="utf-8")
            print('{"type":"message","content":"codex stream"}')
            """
        ),
        encoding="utf-8",
    )
    gemini_script = tmp_path / "fake_gemini_pass.py"
    gemini_script.write_text(
        "print('STATUS: pass\\nGemini review ok')\n",
        encoding="utf-8",
    )
    verify_script = tmp_path / "verify_repair.py"
    verify_script.write_text(
        textwrap.dedent(
            """
            import pathlib
            import sys

            if pathlib.Path("repair.ok").exists():
                print("repair marker exists")
                raise SystemExit(0)
            print("repair marker missing")
            raise SystemExit(2)
            """
        ),
        encoding="utf-8",
    )

    user = User.objects.create_user(username="worker-mars-repair", password="x")

    with override_settings(
        MARS_CODEX_COMMAND=[sys.executable, str(codex_script)],
        MARS_GEMINI_COMMAND=[sys.executable, str(gemini_script)],
        MARS_USER_WORKSPACES_ROOT=tmp_path / "mars_workspaces",
        MARS_CODEX_TIMEOUT_SECONDS=20,
        MARS_CODEX_REPAIR_TIMEOUT_SECONDS=20,
        MARS_GEMINI_TIMEOUT_SECONDS=20,
        MARS_TEST_TIMEOUT_SECONDS=20,
        MARS_VERIFICATION_PROFILES={"repair-test": [sys.executable, str(verify_script)]},
        MEDIA_ROOT=tmp_path / "media",
    ):
        workspace = ensure_personal_workspace(user)
        session = MarsSession.objects.create(
            user=user,
            workspace=workspace,
            task_brief="Create a repairable script",
            generated_plan="# Plan",
            status=MarsSession.STATUS_APPROVED,
        )
        run = MarsRun.objects.create(
            user=user,
            workspace=workspace,
            session=session,
            runtime_control={"stop_requested": False, "verification_profile": "repair-test"},
        )
        asyncio.run(execute_mars_run(run.id))

    run.refresh_from_db()
    assert run.status == MarsRun.STATUS_COMPLETED
    assert "Codex initial answer" in run.codex_summary
    assert "Codex repair answer" in run.codex_summary
    assert "verification attempt 1" in run.test_output
    assert "exit_code=2" in run.test_output
    assert "verification after repair 1" in run.test_output
    assert "repair marker exists" in run.test_output
    assert run.events.filter(event_type="tests_failed").exists()
    assert run.events.filter(event_type="codex_repair_1_started").exists()
    assert run.events.filter(event_type="tests_repair_1_passed").exists()
    assert run.events.filter(event_type="orchestrator_repair_succeeded").exists()
    assert (pathlib.Path(workspace.root_path) / "repair.ok").exists()


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
