from __future__ import annotations

import json
from typing import Any

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core_ui.decorators import require_feature
from mars.models import MarsRun, MarsSession, MarsWorkspace
from mars.policy import MarsPolicyError
from mars.services import (
    CURATED_SKILLS,
    MarsInterviewError,
    build_interview_questions,
    create_run_for_session,
    ensure_personal_workspace,
    generate_plan,
    record_event,
    recommend_skills,
    serialize_event,
    serialize_run,
    serialize_session,
    serialize_workspace,
)


def _json_body(request) -> dict[str, Any]:
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _ok(data: Any, status: int = 200) -> JsonResponse:
    return JsonResponse(data, safe=False, status=status)


def _err(message: str, status: int = 400, **extra: Any) -> JsonResponse:
    return JsonResponse({"error": message, **extra}, status=status)


def _workspace_for_user(request, workspace_id: int) -> MarsWorkspace | None:
    workspace = ensure_personal_workspace(request.user)
    return workspace if workspace.id == workspace_id else None


def _session_for_user(request, session_id: int) -> MarsSession | None:
    workspace = ensure_personal_workspace(request.user)
    return (
        MarsSession.objects.select_related("workspace")
        .filter(pk=session_id, user=request.user, workspace=workspace)
        .first()
    )


def _run_for_user(request, run_id: int) -> MarsRun | None:
    workspace = ensure_personal_workspace(request.user)
    return (
        MarsRun.objects.select_related("session", "workspace")
        .filter(pk=run_id, user=request.user, workspace=workspace)
        .first()
    )


def _selected_skills(payload: dict[str, Any], fallback: list[str]) -> list[str]:
    raw = payload.get("selected_skill_slugs")
    if not isinstance(raw, list):
        return fallback
    selected: list[str] = []
    for item in raw:
        skill = str(item or "").strip()
        if skill in CURATED_SKILLS and skill not in selected:
            selected.append(skill)
    return selected or fallback


@require_http_methods(["GET", "POST"])
@require_feature("mars")
def api_workspaces(request):
    try:
        workspace = ensure_personal_workspace(request.user)
    except MarsPolicyError as exc:
        return _err(str(exc), 400)

    if request.method == "GET":
        return _ok({"workspaces": [serialize_workspace(workspace)]})
    return _ok({"workspace": serialize_workspace(workspace)}, 201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@require_feature("mars")
def api_workspace_detail(request, workspace_id: int):
    workspace = _workspace_for_user(request, workspace_id)
    if workspace is None:
        return _err("Workspace not found.", 404)

    if request.method == "GET":
        return _ok({"workspace": serialize_workspace(workspace)})

    if request.method == "DELETE":
        return _err("Personal MARS workspace cannot be deleted.", 405)

    return _ok({"workspace": serialize_workspace(workspace)})


@require_http_methods(["POST"])
@require_feature("mars")
def api_sessions(request):
    payload = _json_body(request)
    workspace = ensure_personal_workspace(request.user)
    try:
        workspace_id = int(payload.get("workspace_id") or workspace.id)
    except (TypeError, ValueError):
        workspace_id = workspace.id
    if workspace_id != workspace.id or not workspace.enabled:
        return _err("Workspace not found.", 404)

    task_brief = str(payload.get("task_brief") or "").strip()
    if not task_brief:
        return _err("Task brief is required.")

    recommended = recommend_skills(task_brief)
    selected_skills = _selected_skills(payload, recommended)
    try:
        interview_questions = build_interview_questions(
            task_brief,
            workspace_root=workspace.root_path,
            selected_skills=selected_skills,
        )
    except MarsInterviewError as exc:
        return _err(str(exc), 503, code="codex_interview_failed")

    session = MarsSession.objects.create(
        user=request.user,
        workspace=workspace,
        task_brief=task_brief,
        interview_questions=interview_questions,
        selected_skill_slugs=selected_skills,
    )
    return _ok({"session": serialize_session(session), "recommended_skills": recommended}, 201)


@require_http_methods(["GET"])
@require_feature("mars")
def api_session_detail(request, session_id: int):
    session = _session_for_user(request, session_id)
    if session is None:
        return _err("Session not found.", 404)
    return _ok({"session": serialize_session(session), "recommended_skills": recommend_skills(session.task_brief)})


@require_http_methods(["POST"])
@require_feature("mars")
def api_session_answer(request, session_id: int):
    session = _session_for_user(request, session_id)
    if session is None:
        return _err("Session not found.", 404)

    payload = _json_body(request)
    raw_answers = payload.get("answers") if isinstance(payload.get("answers"), dict) else payload
    answers = dict(session.answers or {})
    for question in session.interview_questions or []:
        question_id = str(question.get("id") or "")
        if question_id in raw_answers:
            answers[question_id] = str(raw_answers.get(question_id) or "").strip()

    session.answers = answers
    session.selected_skill_slugs = _selected_skills(payload, session.selected_skill_slugs or recommend_skills(session.task_brief))
    session.generated_plan = generate_plan(session)
    session.status = MarsSession.STATUS_PLAN_READY
    session.save(update_fields=["answers", "selected_skill_slugs", "generated_plan", "status", "updated_at"])
    return _ok({"session": serialize_session(session)})


@require_http_methods(["POST"])
@require_feature("mars")
def api_session_approve_plan(request, session_id: int):
    session = _session_for_user(request, session_id)
    if session is None:
        return _err("Session not found.", 404)

    payload = _json_body(request)
    session.selected_skill_slugs = _selected_skills(payload, session.selected_skill_slugs or recommend_skills(session.task_brief))
    session.generated_plan = str(payload.get("generated_plan") or generate_plan(session)).strip()
    if not session.generated_plan:
        session.generated_plan = generate_plan(session)
    session.status = MarsSession.STATUS_APPROVED
    session.save(update_fields=["selected_skill_slugs", "generated_plan", "status", "updated_at"])
    return _ok({"session": serialize_session(session)})


@require_http_methods(["POST"])
@require_feature("mars")
def api_session_run(request, session_id: int):
    session = _session_for_user(request, session_id)
    if session is None:
        return _err("Session not found.", 404)
    if session.status != MarsSession.STATUS_APPROVED:
        return _err("Approve the generated plan before starting MARS.", 409, code="plan_not_approved")

    payload = _json_body(request)
    try:
        run = create_run_for_session(
            session,
            allow_dirty=bool(payload.get("allow_dirty")),
            test_command=str(payload.get("test_command") or ""),
        )
    except MarsPolicyError as exc:
        message = str(exc)
        status = 409 if "uncommitted" in message.lower() else 400
        code = "dirty_worktree" if status == 409 else "workspace_policy_error"
        return _err(message, status, code=code)
    return _ok({"run": serialize_run(run)}, 201)


@require_http_methods(["GET"])
@require_feature("mars")
def api_run_detail(request, run_id: int):
    run = _run_for_user(request, run_id)
    if run is None:
        return _err("Run not found.", 404)
    return _ok({"run": serialize_run(run)})


@require_http_methods(["GET"])
@require_feature("mars")
def api_run_events(request, run_id: int):
    run = _run_for_user(request, run_id)
    if run is None:
        return _err("Run not found.", 404)
    try:
        after_id = int(request.GET.get("after_id") or 0)
    except ValueError:
        after_id = 0
    events = run.events.filter(id__gt=after_id).order_by("id")
    return _ok({"events": [serialize_event(event) for event in events]})


@require_http_methods(["POST"])
@require_feature("mars")
def api_run_stop(request, run_id: int):
    run = _run_for_user(request, run_id)
    if run is None:
        return _err("Run not found.", 404)

    runtime_control = dict(run.runtime_control or {})
    runtime_control["stop_requested"] = True
    run.runtime_control = runtime_control
    update_fields = ["runtime_control"]
    if run.status == MarsRun.STATUS_QUEUED:
        run.status = MarsRun.STATUS_STOPPED
        run.completed_at = timezone.now()
        update_fields += ["status", "completed_at"]
    run.save(update_fields=update_fields)
    record_event(run, "mars_stop_requested", "Stop requested by user")
    return _ok({"run": serialize_run(run)})
