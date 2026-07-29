from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction

from mars.git_config import ensure_git_config, run_git
from mars.interview_codex import _build_codex_interview_questions
from mars.interview_questions import (
    CURATED_SKILLS,
    MARS_INTERVIEW_OUTPUT_SCHEMA,
    MARS_INTERVIEW_SYSTEM_PROMPT,
    MarsInterviewError,
)
from mars.models import MarsRun, MarsRunEvent, MarsSession, MarsWorkspace, default_deny_globs
from mars.orchestrator import merge_runtime_orchestration
from mars.policy import MarsPolicyError, build_workspace_policy, git_status
from mars.runtime_cli import (
    build_mars_agent_docker_command,
    cli_path_for_command,
    docker_container_child_path,
    docker_workspace_path,
    mars_agent_uses_docker,
    subprocess_env_for_cli,
)
from mars.skill_catalog import recommend_task_skills
from mars.verification import normalize_verification_profile

PERSONAL_WORKSPACE_NAME = "Personal workspace"

__all__ = [
    "CURATED_SKILLS",
    "MARS_INTERVIEW_OUTPUT_SCHEMA",
    "MARS_INTERVIEW_SYSTEM_PROMPT",
    "MarsInterviewError",
    "PERSONAL_WORKSPACE_NAME",
    "build_interview_questions",
    "build_mars_agent_docker_command",
    "claim_next_run",
    "cli_path_for_command",
    "create_run_for_session",
    "docker_container_child_path",
    "docker_workspace_path",
    "ensure_personal_workspace",
    "ensure_personal_workspace_directory",
    "existing_personal_workspace",
    "generate_plan",
    "mars_agent_uses_docker",
    "mars_user_workspaces_base",
    "normalize_workspace_payload",
    "personal_workspace_root",
    "recommend_skills",
    "record_event",
    "require_personal_workspace",
    "serialize_event",
    "serialize_run",
    "serialize_session",
    "serialize_workspace",
    "subprocess_env_for_cli",
    "workspace_is_personal",
]


def mars_user_workspaces_base() -> Path:
    configured = Path(getattr(settings, "MARS_USER_WORKSPACES_ROOT", "agent_projects/mars_workspaces")).expanduser()
    if not configured.is_absolute():
        configured = Path(settings.BASE_DIR) / configured
    return configured.resolve(strict=False)


def personal_workspace_root(user) -> Path:
    if not getattr(user, "id", None):
        raise MarsPolicyError("Authenticated user is required for a personal workspace.")
    return (mars_user_workspaces_base() / f"user_{user.id}").resolve(strict=False)


def ensure_personal_workspace_directory(user) -> Path:
    root = personal_workspace_root(user)
    base = mars_user_workspaces_base()
    try:
        root.relative_to(base)
    except ValueError as exc:
        raise MarsPolicyError("Personal workspace root escaped the configured base directory.") from exc

    root.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        init = subprocess.run(["git", "init", str(root)], capture_output=True, text=True, timeout=20, check=False)
        if init.returncode != 0:
            raise MarsPolicyError((init.stderr or init.stdout or "Unable to initialize personal workspace.").strip())

    ensure_git_config(root, "user.email", f"mars-user-{user.id}@local.invalid")
    ensure_git_config(root, "user.name", f"MARS User {user.id}")

    has_head = run_git(root, "rev-parse", "--verify", "HEAD", check=False).returncode == 0
    if not has_head:
        readme = root / "README.md"
        if not readme.exists():
            readme.write_text(
                "# MARS personal workspace\n\nFiles created by MARS for this user stay in this repository.\n",
                encoding="utf-8",
            )
        run_git(root, "add", "README.md")
        commit = run_git(root, "commit", "-m", "Initialize MARS personal workspace", check=False)
        if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr).lower():
            raise MarsPolicyError(
                (commit.stderr or commit.stdout or "Unable to initialize personal workspace.").strip()
            )
    return root


def existing_personal_workspace(user) -> MarsWorkspace | None:
    for workspace in MarsWorkspace.objects.filter(user=user, name=PERSONAL_WORKSPACE_NAME):
        if workspace_is_personal(user, workspace):
            return workspace
    return None


def ensure_personal_workspace(user) -> MarsWorkspace:
    root = ensure_personal_workspace_directory(user)
    data = {
        "root_path": str(root),
        "read_allow_roots": [str(root)],
        "write_allow_roots": [str(root)],
        "deny_globs": default_deny_globs(),
        "enabled": True,
    }
    workspace, _ = MarsWorkspace.objects.get_or_create(
        user=user,
        name=PERSONAL_WORKSPACE_NAME,
        defaults=data,
    )
    changed_fields: list[str] = []
    for field, value in data.items():
        if getattr(workspace, field) != value:
            setattr(workspace, field, value)
            changed_fields.append(field)
    if changed_fields:
        workspace.save(update_fields=changed_fields + ["updated_at"])
    return workspace


def workspace_is_personal(user, workspace: MarsWorkspace) -> bool:
    expected_root = personal_workspace_root(user)
    try:
        actual_root = Path(workspace.root_path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return False
    return workspace.user_id == user.id and actual_root == expected_root and workspace.name == PERSONAL_WORKSPACE_NAME


def require_personal_workspace(user, workspace: MarsWorkspace) -> None:
    if not workspace_is_personal(user, workspace):
        raise MarsPolicyError("MARS can only run inside the user's personal workspace.")


def serialize_workspace(workspace: MarsWorkspace) -> dict[str, Any]:
    return {
        "id": workspace.id,
        "name": workspace.name,
        "root_path": workspace.root_path,
        "read_allow_roots": workspace.read_allow_roots or [],
        "write_allow_roots": workspace.write_allow_roots or [],
        "deny_globs": workspace.deny_globs or [],
        "enabled": workspace.enabled,
        "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
        "updated_at": workspace.updated_at.isoformat() if workspace.updated_at else None,
    }


def serialize_session(session: MarsSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "workspace_id": session.workspace_id,
        "workspace": serialize_workspace(session.workspace),
        "task_brief": session.task_brief,
        "answers": session.answers or {},
        "interview_questions": session.interview_questions or [],
        "selected_skill_slugs": [],
        "generated_plan": session.generated_plan,
        "status": session.status,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


def _public_runtime_control(runtime_control: dict[str, Any] | None) -> dict[str, Any]:
    control = dict(runtime_control or {})
    control.pop("orchestration", None)
    control.pop("skill_routing", None)
    control.pop("skill_catalog", None)
    return control


def serialize_run(run: MarsRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "session_id": run.session_id,
        "workspace_id": run.workspace_id,
        "workspace": serialize_workspace(run.workspace),
        "cli_roles": {},
        "status": run.status,
        "runtime_control": _public_runtime_control(run.runtime_control),
        "allow_dirty": run.allow_dirty,
        "final_report": run.final_report,
        "codex_summary": run.codex_summary,
        "gemini_review": run.gemini_review,
        "test_output": run.test_output,
        "git_before": run.git_before,
        "git_after": run.git_after,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def serialize_event(event: MarsRunEvent) -> dict[str, Any]:
    payload = dict(event.payload or {})
    payload.pop("command", None)
    return {
        "id": event.id,
        "run_id": event.run_id,
        "event_type": event.event_type,
        "message": event.message,
        "payload": payload,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def normalize_workspace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    root_path = str(payload.get("root_path") or "").strip()
    root = build_workspace_policy(
        root_path=root_path,
        read_allow_roots=list(payload.get("read_allow_roots") or [root_path]),
        write_allow_roots=list(payload.get("write_allow_roots") or [root_path]),
        deny_globs=list(payload.get("deny_globs") or default_deny_globs()),
    ).root
    name = str(payload.get("name") or Path(root).name or "Workspace").strip()[:160]
    deny_globs = list(payload.get("deny_globs") or default_deny_globs())
    return {
        "name": name,
        "root_path": str(root),
        "read_allow_roots": [str(item) for item in payload.get("read_allow_roots") or [str(root)]],
        "write_allow_roots": [str(item) for item in payload.get("write_allow_roots") or [str(root)]],
        "deny_globs": deny_globs,
        "enabled": bool(payload.get("enabled", True)),
    }


def recommend_skills(task_brief: str) -> list[str]:
    return recommend_task_skills(task_brief)


def build_interview_questions(
    task_brief: str,
    *,
    workspace_root: str | Path,
    selected_skills: list[str] | None = None,
) -> list[dict[str, Any]]:
    return _build_codex_interview_questions(
        task_brief,
        workspace_root=workspace_root,
        selected_skills=selected_skills,
    )


def generate_plan(session: MarsSession) -> str:
    answers = session.answers or {}
    skills = session.selected_skill_slugs or recommend_skills(session.task_brief)
    goal = str(answers.get("success_criteria") or session.task_brief or "Not specified yet.").strip()
    question_lines = []
    for question in session.interview_questions or []:
        question_id = str(question.get("id") or "")
        answer = str(answers.get(question_id) or "").strip()
        if answer:
            question_lines.append(f"- {question.get('question')}: {answer}")
    return "\n".join(
        [
            "# MARS execution plan",
            "",
            "## Goal",
            goal,
            "",
            "## Execution checklist",
            "1. Lock the personal workspace policy and inspect only files inside that root.",
            "2. Use selected skill instructions: " + ", ".join(skills) + ".",
            "3. Build the smallest complete version that satisfies the approved goal.",
            "4. Run the requested verification checks or explain why a check is not available.",
            "5. Ask Gemini CLI for a read-only review of the produced diff.",
            "6. Return a final report with changed files, verification output, and remaining risk.",
            "",
            "## Task brief",
            session.task_brief,
            "",
            "## Interview answers",
            "\n".join(question_lines) or "No interview answers yet.",
        ]
    )


def record_event(
    run: MarsRun, event_type: str, message: str = "", payload: dict[str, Any] | None = None
) -> MarsRunEvent:
    event = MarsRunEvent.objects.create(
        run=run,
        event_type=event_type,
        message=message,
        payload=payload or {},
    )
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"mars_run_{run.id}",
            {"type": "mars.event", "event": serialize_event(event)},
        )
    return event


def claim_next_run() -> MarsRun | None:
    with transaction.atomic():
        run = (
            MarsRun.objects.select_for_update(skip_locked=True)
            .filter(status=MarsRun.STATUS_QUEUED)
            .select_related("session", "workspace", "user")
            .order_by("created_at", "id")
            .first()
        )
        if run is None:
            return None
        run.status = MarsRun.STATUS_RUNNING
        run.save(update_fields=["status"])
        return run


def create_run_for_session(
    session: MarsSession,
    *,
    allow_dirty: bool,
    verification_profile: str = "",
    test_command: str = "",
) -> MarsRun:
    require_personal_workspace(session.user, session.workspace)
    dirty_status = git_status(session.workspace.root_path)
    if dirty_status and not allow_dirty:
        raise MarsPolicyError("Workspace has uncommitted changes. Confirm dirty worktree before running MARS.")
    profile = normalize_verification_profile(verification_profile or test_command)
    runtime_control = merge_runtime_orchestration(
        {"stop_requested": False, "verification_profile": profile},
        selected_skills=session.selected_skill_slugs,
    )
    run = MarsRun.objects.create(
        session=session,
        workspace=session.workspace,
        user=session.user,
        allow_dirty=allow_dirty,
        runtime_control=runtime_control,
        git_before=dirty_status,
    )
    session.status = MarsSession.STATUS_RUNNING
    session.save(update_fields=["status", "updated_at"])
    record_event(run, "mars_run_queued", "MARS run queued", {"allow_dirty": allow_dirty})
    return run
