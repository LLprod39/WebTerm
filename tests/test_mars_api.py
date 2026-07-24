import json
import os
import subprocess
import sys
import textwrap
import time

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import Client, override_settings

from core_ui.models import UserAppPermission
from mars.consumers import MarsRunConsumer
from mars.models import MarsRun, MarsRunEvent, MarsSession, MarsWorkspace, default_deny_globs
from mars.services import (
    PERSONAL_WORKSPACE_NAME,
    build_interview_questions,
    ensure_personal_workspace,
    personal_workspace_root,
)


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _write_fake_interview_codex(tmp_path):
    script = tmp_path / "fake_interview_codex.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import pathlib
            import sys

            prompt = sys.stdin.read()
            output_path = pathlib.Path(sys.argv[sys.argv.index("--output-last-message") + 1])
            if "3D" in prompt or "змей" in prompt:
                questions = [
                    {"id": "success_criteria", "question": "Какой результат нужен именно для 3D змейки?", "kind": "choice_text", "options": ["Играбельный прототип", "Полный MVP"], "required": True},
                    {"id": "snake_camera", "question": "Какая камера нужна для змейки?", "kind": "choice_text", "options": ["Изометрия", "Сверху"], "required": True},
                    {"id": "snake_controls", "question": "Как управлять змейкой?", "kind": "choice_text", "options": ["Клавиатура", "Touch"], "required": True},
                    {"id": "snake_rules", "question": "Какие правила нужны?", "kind": "multi_choice_text", "options": ["Рост", "Бонусы", "Пауза"], "required": True},
                    {"id": "verification", "question": "Как проверить игру?", "kind": "multi_choice_text", "options": ["npm run build", "Playwright"], "required": True}
                ]
            else:
                questions = [
                    {"id": "success_criteria", "question": "Какой результат нужен именно для Django API?", "kind": "choice_text", "options": ["API работает", "Контракт покрыт тестами"], "required": True},
                    {"id": "api_contract", "question": "Какой контракт endpoint нужен?", "kind": "multi_choice_text", "options": ["GET", "POST", "Permissions"], "required": True},
                    {"id": "data_model", "question": "Какая модель данных нужна?", "kind": "multi_choice_text", "options": ["Существующая модель", "Новая модель"], "required": True},
                    {"id": "auth_rules", "question": "Какие правила доступа нужны?", "kind": "multi_choice_text", "options": ["Owner only", "Feature gate"], "required": True},
                    {"id": "verification", "question": "Как проверить API?", "kind": "multi_choice_text", "options": ["pytest", "Django check"], "required": True}
                ]
            output_path.write_text(json.dumps({"questions": questions}, ensure_ascii=False), encoding="utf-8")
            print(json.dumps({"type": "message", "content": "fake codex interview"}))
            """
        ),
        encoding="utf-8",
    )
    return script


def _grant_feature(user: User, *features: str) -> None:
    for feature in features:
        UserAppPermission.objects.update_or_create(
            user=user,
            feature=feature,
            defaults={"allowed": True},
        )


def _init_git_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "mars@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "MARS Test"], cwd=root, check=True)
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True, text=True)
    return root


def _create_personal_workspace_run(user: User):
    root = personal_workspace_root(user)
    root.mkdir(parents=True)
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True, text=True)
    workspace = MarsWorkspace.objects.create(
        user=user,
        name=PERSONAL_WORKSPACE_NAME,
        root_path=str(root),
        read_allow_roots=[str(root)],
        write_allow_roots=[str(root)],
        deny_globs=default_deny_globs(),
        enabled=True,
    )
    session = MarsSession.objects.create(
        user=user,
        workspace=workspace,
        task_brief="Read existing MARS run",
        status=MarsSession.STATUS_APPROVED,
    )
    run = MarsRun.objects.create(user=user, workspace=workspace, session=session)
    MarsRunEvent.objects.create(run=run, event_type="mars_run_queued", message="Queued")
    return root, run


def _create_workspace(client: Client, root) -> int:
    response = client.get("/api/mars/workspaces/")
    assert response.status_code == 200, response.content
    workspace = response.json()["workspaces"][0]
    assert workspace["root_path"].startswith(str(root))
    return workspace["id"]


def _create_approved_session(client: Client, workspace_id: int) -> int:
    create = client.post(
        "/api/mars/sessions/",
        data=_json({"workspace_id": workspace_id, "task_brief": "Add a React page"}),
        content_type="application/json",
    )
    assert create.status_code == 201, create.content
    session_id = create.json()["session"]["id"]
    assert len(create.json()["session"]["interview_questions"]) >= 5

    answer = client.post(
        f"/api/mars/sessions/{session_id}/answer/",
        data=_json({"answers": {"success_criteria": "Page renders."}}),
        content_type="application/json",
    )
    assert answer.status_code == 200, answer.content
    assert answer.json()["session"]["status"] == "plan_ready"
    assert "MARS execution plan" in answer.json()["session"]["generated_plan"]
    assert "## Goal" in answer.json()["session"]["generated_plan"]

    approve = client.post(f"/api/mars/sessions/{session_id}/approve-plan/", content_type="application/json")
    assert approve.status_code == 200, approve.content
    assert approve.json()["session"]["status"] == "approved"
    return session_id


def test_mars_interview_questions_are_task_specific(tmp_path):
    script = _write_fake_interview_codex(tmp_path)

    with override_settings(
        MARS_INTERVIEW_CODEX_COMMAND=[sys.executable, str(script)],
        MEDIA_ROOT=script.parent / "media",
    ):
        game_questions = build_interview_questions(
            "Сделай 3D игру змейка в браузере",
            workspace_root=script.parent,
        )
        api_questions = build_interview_questions(
            "Добавь Django API endpoint для workspace permissions",
            workspace_root=script.parent,
        )

    assert len(game_questions) >= 5
    assert len(api_questions) >= 5
    assert any("змейки" in question["question"].lower() or "snake" in question["id"] for question in game_questions)
    assert any("Изометрия" in question.get("options", []) for question in game_questions)
    assert any("api" in question["question"].lower() or question["id"] == "api_contract" for question in api_questions)
    assert game_questions != api_questions


@pytest.mark.django_db
def test_mars_session_fails_closed_when_codex_interview_fails(tmp_path):
    script = tmp_path / "fake_failing_codex.py"
    script.write_text("import sys\nprint('codex unavailable', file=sys.stderr)\nsys.exit(2)\n", encoding="utf-8")
    user = User.objects.create_user(username="mars-fail", password="x")
    _grant_feature(user, "mars")
    client = Client()
    client.force_login(user)

    with override_settings(
        MARS_USER_WORKSPACES_ROOT=tmp_path / "mars_workspaces",
        MARS_INTERVIEW_CODEX_COMMAND=[sys.executable, str(script)],
        MEDIA_ROOT=tmp_path / "media",
    ):
        workspace_id = _create_workspace(client, tmp_path / "mars_workspaces")
        response = client.post(
            "/api/mars/sessions/",
            data=_json({"workspace_id": workspace_id, "task_brief": "Build a page"}),
            content_type="application/json",
        )

    assert response.status_code == 503
    assert response.json()["code"] == "codex_interview_failed"
    assert "Codex CLI interview failed" in response.json()["error"]


@pytest.mark.django_db
def test_ensure_personal_workspace_recovers_stale_git_config_lock(tmp_path):
    user = User.objects.create_user(username="mars-stale-lock", password="x")

    with override_settings(
        MARS_USER_WORKSPACES_ROOT=tmp_path / "mars_workspaces",
        MARS_GIT_CONFIG_LOCK_STALE_SECONDS=1,
        MARS_GIT_CONFIG_LOCK_RETRIES=2,
        MARS_GIT_CONFIG_LOCK_RETRY_DELAY_SECONDS=0,
    ):
        root = personal_workspace_root(user)
        root.mkdir(parents=True)
        subprocess.run(["git", "init", str(root)], check=True, capture_output=True, text=True)
        lock_path = root / ".git" / "config.lock"
        lock_path.write_text("stale\n", encoding="utf-8")
        old_time = time.time() - 10
        os.utime(lock_path, (old_time, old_time))

        workspace = ensure_personal_workspace(user)

        email = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "user.email"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD"], check=False)

    assert workspace.root_path == str(root)
    assert email == f"mars-user-{user.id}@local.invalid"
    assert head.returncode == 0
    assert not lock_path.exists()


@pytest.mark.django_db
def test_mars_run_events_use_existing_workspace_when_git_config_lock_blocks_init(tmp_path):
    user = User.objects.create_user(username="mars-events-lock", password="x")
    _grant_feature(user, "mars")
    client = Client()
    client.force_login(user)

    with override_settings(
        MARS_USER_WORKSPACES_ROOT=tmp_path / "mars_workspaces",
        MARS_GIT_CONFIG_LOCK_STALE_SECONDS=600,
        MARS_GIT_CONFIG_LOCK_RETRIES=1,
        MARS_GIT_CONFIG_LOCK_RETRY_DELAY_SECONDS=0,
    ):
        root, run = _create_personal_workspace_run(user)
        lock_path = root / ".git" / "config.lock"
        lock_path.write_text("active\n", encoding="utf-8")

        response = client.get(f"/api/mars/runs/{run.id}/events/")

    assert response.status_code == 200, response.content
    assert response.json()["events"][0]["event_type"] == "mars_run_queued"
    assert lock_path.exists()


@pytest.mark.django_db
def test_mars_readonly_detail_endpoints_use_existing_workspace_when_git_config_lock_blocks_init(tmp_path):
    user = User.objects.create_user(username="mars-detail-lock", password="x")
    _grant_feature(user, "mars")
    client = Client()
    client.force_login(user)

    with override_settings(
        MARS_USER_WORKSPACES_ROOT=tmp_path / "mars_workspaces",
        MARS_GIT_CONFIG_LOCK_STALE_SECONDS=600,
        MARS_GIT_CONFIG_LOCK_RETRIES=1,
        MARS_GIT_CONFIG_LOCK_RETRY_DELAY_SECONDS=0,
    ):
        root, run = _create_personal_workspace_run(user)
        lock_path = root / ".git" / "config.lock"
        lock_path.write_text("active\n", encoding="utf-8")

        workspaces_response = client.get("/api/mars/workspaces/")
        workspace_response = client.get(f"/api/mars/workspaces/{run.workspace_id}/")
        session_response = client.get(f"/api/mars/sessions/{run.session_id}/")

    assert workspaces_response.status_code == 200, workspaces_response.content
    assert workspaces_response.json()["workspaces"][0]["id"] == run.workspace_id
    assert workspace_response.status_code == 200, workspace_response.content
    assert workspace_response.json()["workspace"]["id"] == run.workspace_id
    assert session_response.status_code == 200, session_response.content
    assert session_response.json()["session"]["id"] == run.session_id
    assert lock_path.exists()


@pytest.mark.django_db
def test_mars_session_create_uses_existing_workspace_when_git_config_lock_blocks_init(tmp_path):
    script = _write_fake_interview_codex(tmp_path)
    user = User.objects.create_user(username="mars-session-lock", password="x")
    _grant_feature(user, "mars")
    client = Client()
    client.force_login(user)

    with override_settings(
        MARS_USER_WORKSPACES_ROOT=tmp_path / "mars_workspaces",
        MARS_GIT_CONFIG_LOCK_STALE_SECONDS=600,
        MARS_GIT_CONFIG_LOCK_RETRIES=1,
        MARS_GIT_CONFIG_LOCK_RETRY_DELAY_SECONDS=0,
        MARS_INTERVIEW_CODEX_COMMAND=[sys.executable, str(script)],
        MEDIA_ROOT=tmp_path / "media",
    ):
        root, run = _create_personal_workspace_run(user)
        lock_path = root / ".git" / "config.lock"
        lock_path.write_text("active\n", encoding="utf-8")

        response = client.post(
            "/api/mars/sessions/",
            data=_json({"workspace_id": run.workspace_id, "task_brief": "Build a React page"}),
            content_type="application/json",
        )

    assert response.status_code == 201, response.content
    assert response.json()["session"]["workspace_id"] == run.workspace_id
    assert len(response.json()["session"]["interview_questions"]) >= 5
    assert lock_path.exists()


@pytest.mark.django_db(transaction=True)
def test_mars_websocket_access_uses_existing_workspace_when_git_config_lock_blocks_init(tmp_path):
    user = User.objects.create_user(username="mars-ws-lock", password="x")
    _grant_feature(user, "mars")

    with override_settings(
        MARS_USER_WORKSPACES_ROOT=tmp_path / "mars_workspaces",
        MARS_GIT_CONFIG_LOCK_STALE_SECONDS=600,
        MARS_GIT_CONFIG_LOCK_RETRIES=1,
        MARS_GIT_CONFIG_LOCK_RETRY_DELAY_SECONDS=0,
    ):
        root, run = _create_personal_workspace_run(user)
        lock_path = root / ".git" / "config.lock"
        lock_path.write_text("active\n", encoding="utf-8")

        allowed = async_to_sync(MarsRunConsumer()._user_can_access_run)(user.id, run.id)

    assert allowed is True
    assert lock_path.exists()


@pytest.mark.django_db
def test_mars_feature_denies_non_staff_without_permission():
    user = User.objects.create_user(username="no-mars", password="x")
    client = Client()
    client.force_login(user)

    response = client.get("/api/mars/workspaces/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_mars_workspace_session_run_stop_and_events_flow(tmp_path):
    user = User.objects.create_user(username="mars-user", password="x")
    _grant_feature(user, "mars")
    client = Client()
    client.force_login(user)

    codex_script = _write_fake_interview_codex(tmp_path)
    with override_settings(
        MARS_USER_WORKSPACES_ROOT=tmp_path / "mars_workspaces",
        MARS_INTERVIEW_CODEX_COMMAND=[sys.executable, str(codex_script)],
        MEDIA_ROOT=tmp_path / "media",
    ):
        workspace_id = _create_workspace(client, tmp_path / "mars_workspaces")
        workspaces = client.get("/api/mars/workspaces/")
        assert workspaces.status_code == 200
        assert workspaces.json()["workspaces"][0]["id"] == workspace_id

        session_id = _create_approved_session(client, workspace_id)
        run_response = client.post(
            f"/api/mars/sessions/{session_id}/run/",
            data=_json({"allow_dirty": False}),
            content_type="application/json",
        )
        assert run_response.status_code == 201, run_response.content
        run_id = run_response.json()["run"]["id"]
        assert run_response.json()["run"]["status"] == "queued"
        assert "orchestration" not in run_response.json()["run"]["runtime_control"]

        orchestration = MarsRun.objects.get(pk=run_id).runtime_control["orchestration"]
        assert orchestration["visibility"] == "internal"
        assert orchestration["skill_catalog"]["hidden_from_user"] is True
        # Clean CI may have only the four built-in fallback skills. Installed
        # Codex/plugin skills are optional and must not affect this contract.
        assert orchestration["skill_catalog"]["available_count"] >= 4
        assert orchestration["skill_routing"]["architect"]
        assert orchestration["skill_routing"]["executor"]

        projects = client.get("/api/mars/projects/")
        assert projects.status_code == 200
        assert projects.json()["projects"][0]["session"]["id"] == session_id
        assert projects.json()["projects"][0]["latest_run"]["id"] == run_id
        assert projects.json()["projects"][0]["run_count"] == 1

        events = client.get(f"/api/mars/runs/{run_id}/events/")
        assert events.status_code == 200
        assert events.json()["events"][0]["event_type"] == "mars_run_queued"

        stop = client.post(f"/api/mars/runs/{run_id}/stop/")
        assert stop.status_code == 200
        assert stop.json()["run"]["status"] == "stopped"
        assert MarsRun.objects.get(pk=run_id).runtime_control["stop_requested"] is True
        assert MarsRunEvent.objects.filter(run_id=run_id, event_type="mars_stop_requested").exists()


@pytest.mark.django_db
def test_mars_workspace_is_personal_and_hides_legacy_roots(tmp_path):
    user = User.objects.create_user(username="mars-git", password="x")
    _grant_feature(user, "mars")
    client = Client()
    client.force_login(user)
    legacy_parent = tmp_path / "legacy"
    legacy_parent.mkdir()
    legacy_root = _init_git_repo(legacy_parent)
    MarsWorkspace.objects.create(user=user, name="legacy", root_path=str(legacy_root))

    codex_script = _write_fake_interview_codex(tmp_path)
    with override_settings(
        MARS_USER_WORKSPACES_ROOT=tmp_path / "mars_workspaces",
        MARS_INTERVIEW_CODEX_COMMAND=[sys.executable, str(codex_script)],
        MEDIA_ROOT=tmp_path / "media",
    ):
        response = client.post(
            "/api/mars/workspaces/",
            data=_json({"name": "attempted-root", "root_path": str(legacy_root)}),
            content_type="application/json",
        )
        assert response.status_code == 201, response.content
        workspace = response.json()["workspace"]
        assert workspace["name"] == "Personal workspace"
        assert workspace["root_path"].startswith(str(tmp_path / "mars_workspaces"))
        assert str(legacy_root) not in workspace["root_path"]

        listing = client.get("/api/mars/workspaces/")
        assert listing.status_code == 200
        assert [item["id"] for item in listing.json()["workspaces"]] == [workspace["id"]]

        legacy = MarsWorkspace.objects.get(name="legacy")
        legacy_detail = client.get(f"/api/mars/workspaces/{legacy.id}/")
        assert legacy_detail.status_code == 404


@pytest.mark.django_db
def test_mars_run_blocks_dirty_worktree_until_explicit_confirm(tmp_path):
    user = User.objects.create_user(username="mars-dirty", password="x")
    _grant_feature(user, "mars")
    client = Client()
    client.force_login(user)

    codex_script = _write_fake_interview_codex(tmp_path)
    with override_settings(
        MARS_USER_WORKSPACES_ROOT=tmp_path / "mars_workspaces",
        MARS_INTERVIEW_CODEX_COMMAND=[sys.executable, str(codex_script)],
        MEDIA_ROOT=tmp_path / "media",
    ):
        workspace_id = _create_workspace(client, tmp_path / "mars_workspaces")
        session_id = _create_approved_session(client, workspace_id)
        (tmp_path / "mars_workspaces" / f"user_{user.id}" / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        blocked = client.post(
            f"/api/mars/sessions/{session_id}/run/",
            data=_json({"allow_dirty": False}),
            content_type="application/json",
        )
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "dirty_worktree"

        accepted = client.post(
            f"/api/mars/sessions/{session_id}/run/",
            data=_json({"allow_dirty": True}),
            content_type="application/json",
        )
        assert accepted.status_code == 201, accepted.content
        assert accepted.json()["run"]["allow_dirty"] is True
