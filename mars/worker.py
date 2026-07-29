from __future__ import annotations

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connections
from django.utils import timezone
from loguru import logger

from mars.models import MarsRun, MarsSession
from mars.orchestrator import (
    build_architect_prompt,
    build_codex_executor_prompt,
    build_codex_repair_prompt,
    build_gemini_review_prompt,
    default_orchestrator_roles,
    max_repair_rounds,
    merge_runtime_orchestration,
    review_repair_rounds,
    review_requests_changes,
)
from mars.policy import MarsPolicyError, build_workspace_policy, git_status
from mars.services import (
    claim_next_run,
    mars_agent_uses_docker,
    record_event,
    require_personal_workspace,
)
from mars.worker_phases import (
    _check_stop_and_finish,
    _run_codex_phase,
    _run_dir,
    _run_verification,
    _safe_gemini_phase,
    _save_instance,
    _test_history_entry,
)


async def execute_mars_run(run_id: int) -> None:
    run = await sync_to_async(
        lambda: MarsRun.objects.select_related("session", "workspace", "user").get(pk=run_id),
        thread_sensitive=True,
    )()
    started_at = timezone.now()
    run.status = MarsRun.STATUS_RUNNING
    run.started_at = started_at
    await _save_instance(run, ["status", "started_at"])
    await sync_to_async(record_event)(run, "mars_run_started", "MARS execution started")

    try:
        run.cli_roles = default_orchestrator_roles()
        run.runtime_control = merge_runtime_orchestration(
            run.runtime_control,
            selected_skills=run.session.selected_skill_slugs,
        )
        await _save_instance(run, ["cli_roles", "runtime_control"])
        await sync_to_async(record_event)(
            run,
            "orchestrator_started",
            "MARS workflow prepared",
            {"workflow": "automatic"},
        )

        require_personal_workspace(run.user, run.workspace)
        policy = build_workspace_policy(
            root_path=run.workspace.root_path,
            read_allow_roots=run.workspace.read_allow_roots,
            write_allow_roots=run.workspace.write_allow_roots,
            deny_globs=run.workspace.deny_globs,
        )
        before = await sync_to_async(git_status)(str(policy.root))
        if before and not run.allow_dirty:
            raise MarsPolicyError("Workspace has uncommitted changes.")

        run.git_before = before
        await _save_instance(run, ["git_before"])

        docker_runtime = mars_agent_uses_docker()
        run_dir = _run_dir(run.id)

        architect_exit, architect_output = await _safe_gemini_phase(
            run,
            role="architect",
            prompt=build_architect_prompt(run),
            event_prefix="gemini_architect",
            workspace_root=policy.root,
            docker_runtime=docker_runtime,
            required=bool(getattr(settings, "MARS_ORCHESTRATOR_REQUIRE_ARCHITECT", False)),
        )
        architect_brief = architect_output[-40000:]
        if architect_exit != 0:
            await sync_to_async(record_event)(
                run,
                "orchestrator_architect_degraded",
                "Planning phase unavailable; continuing with the approved plan",
                {"exit_code": architect_exit},
            )
        if await _check_stop_and_finish(run):
            return

        codex_exit, _codex_output, final_text = await _run_codex_phase(
            run,
            role="executor",
            prompt=build_codex_executor_prompt(run, architect_brief),
            event_prefix="codex",
            output_path=run_dir / "codex-final.md",
            workspace_root=policy.root,
            run_dir=run_dir,
            docker_runtime=docker_runtime,
        )
        run.codex_summary = final_text
        await _save_instance(run, ["codex_summary"])
        if codex_exit != 0:
            raise RuntimeError(f"Codex exited with code {codex_exit}")
        if await _check_stop_and_finish(run):
            return

        runtime_control = run.runtime_control or {}
        verification_profile = str(
            runtime_control.get("verification_profile") or runtime_control.get("test_command") or ""
        ).strip()
        test_history: list[str] = []
        test_exit, test_output = await _run_verification(
            run,
            workspace_root=policy.root,
            docker_runtime=docker_runtime,
            verification_profile=verification_profile,
            event_prefix="tests",
        )
        test_history.append(_test_history_entry("verification attempt 1", test_exit, test_output))
        run.test_output = "\n\n".join(test_history)[-40000:]
        await _save_instance(run, ["test_output"])

        if test_exit not in (None, 0):
            for repair_round in range(1, max_repair_rounds() + 1):
                repair_exit, _, repair_text = await _run_codex_phase(
                    run,
                    role="repair",
                    prompt=build_codex_repair_prompt(
                        run,
                        repair_reason="Verification command failed.",
                        verification_output=run.test_output,
                        repair_round=repair_round,
                    ),
                    event_prefix=f"codex_repair_{repair_round}",
                    output_path=run_dir / f"codex-repair-{repair_round}.md",
                    workspace_root=policy.root,
                    run_dir=run_dir,
                    docker_runtime=docker_runtime,
                )
                run.codex_summary = "\n\n".join(
                    [run.codex_summary or "", f"## Repair round {repair_round}", repair_text]
                ).strip()
                await _save_instance(run, ["codex_summary"])
                if repair_exit != 0:
                    raise RuntimeError(f"Codex repair round {repair_round} exited with code {repair_exit}")
                if await _check_stop_and_finish(run):
                    return
                test_exit, test_output = await _run_verification(
                    run,
                    workspace_root=policy.root,
                    docker_runtime=docker_runtime,
                    verification_profile=verification_profile,
                    event_prefix=f"tests_repair_{repair_round}",
                )
                test_history.append(
                    _test_history_entry(f"verification after repair {repair_round}", test_exit, test_output)
                )
                run.test_output = "\n\n".join(test_history)[-40000:]
                await _save_instance(run, ["test_output"])
                if test_exit == 0:
                    await sync_to_async(record_event)(
                        run,
                        "orchestrator_repair_succeeded",
                        "Codex repaired verification failure",
                        {"repair_round": repair_round},
                    )
                    break

        run.git_after = await sync_to_async(git_status)(str(policy.root))
        await _save_instance(run, ["git_after"])

        gemini_exit, gemini_output = await _safe_gemini_phase(
            run,
            role="reviewer",
            prompt=build_gemini_review_prompt(run, architect_brief),
            event_prefix="gemini",
            workspace_root=policy.root,
            docker_runtime=docker_runtime,
        )
        run.gemini_review = gemini_output[-40000:]
        await _save_instance(run, ["gemini_review"])
        if gemini_exit != 0:
            await sync_to_async(record_event)(
                run, "gemini_review_failed", "Gemini review failed", {"exit_code": gemini_exit}
            )

        if gemini_exit == 0 and review_requests_changes(run.gemini_review):
            for repair_round in range(1, review_repair_rounds() + 1):
                repair_exit, _, repair_text = await _run_codex_phase(
                    run,
                    role="repair",
                    prompt=build_codex_repair_prompt(
                        run,
                        repair_reason="Gemini review requested changes.",
                        verification_output=run.test_output,
                        gemini_review=run.gemini_review,
                        repair_round=repair_round,
                    ),
                    event_prefix=f"codex_review_repair_{repair_round}",
                    output_path=run_dir / f"codex-review-repair-{repair_round}.md",
                    workspace_root=policy.root,
                    run_dir=run_dir,
                    docker_runtime=docker_runtime,
                )
                run.codex_summary = "\n\n".join(
                    [run.codex_summary or "", f"## Review repair round {repair_round}", repair_text]
                ).strip()
                await _save_instance(run, ["codex_summary"])
                if repair_exit != 0:
                    raise RuntimeError(f"Codex review repair round {repair_round} exited with code {repair_exit}")
                if await _check_stop_and_finish(run):
                    return
                if verification_profile:
                    test_exit, test_output = await _run_verification(
                        run,
                        workspace_root=policy.root,
                        docker_runtime=docker_runtime,
                        verification_profile=verification_profile,
                        event_prefix=f"tests_review_repair_{repair_round}",
                    )
                    test_history.append(
                        _test_history_entry(f"verification after review repair {repair_round}", test_exit, test_output)
                    )
                    run.test_output = "\n\n".join(test_history)[-40000:]
                    await _save_instance(run, ["test_output"])
                run.git_after = await sync_to_async(git_status)(str(policy.root))
                await _save_instance(run, ["git_after"])
                gemini_exit, gemini_output = await _safe_gemini_phase(
                    run,
                    role="reviewer",
                    prompt=build_gemini_review_prompt(run, architect_brief),
                    event_prefix=f"gemini_rereview_{repair_round}",
                    workspace_root=policy.root,
                    docker_runtime=docker_runtime,
                )
                run.gemini_review = gemini_output[-40000:]
                await _save_instance(run, ["gemini_review"])
                if not review_requests_changes(run.gemini_review):
                    await sync_to_async(record_event)(
                        run,
                        "orchestrator_review_repair_succeeded",
                        "Codex addressed Gemini review blockers",
                        {"repair_round": repair_round},
                    )
                    break

        run.final_report = "\n\n".join(
            [
                "# MARS orchestration final report",
                "## Orchestration",
                "Guided planning -> creation -> verification -> repair when needed -> final quality check.",
                "## Planning",
                architect_brief or "Planning phase was unavailable or produced no output.",
                "## Creation",
                run.codex_summary or "",
                "## Verification",
                run.test_output or "No verification command configured.",
                "## Quality check",
                run.gemini_review or "No quality review output.",
                "## Git status after run",
                run.git_after or "Clean worktree.",
            ]
        )
        run.status = MarsRun.STATUS_COMPLETED
        run.completed_at = timezone.now()
        await _save_instance(run, ["final_report", "gemini_review", "status", "completed_at"])
        run.session.status = MarsSession.STATUS_COMPLETED
        await _save_instance(run.session, ["status", "updated_at"])
        await sync_to_async(record_event)(run, "mars_run_completed", "MARS run completed")
    except Exception as exc:
        logger.exception("MARS run {} failed: {}", run.id, exc)
        run.status = MarsRun.STATUS_FAILED
        run.final_report = f"MARS run failed: {exc}"
        run.completed_at = timezone.now()
        await _save_instance(run, ["status", "final_report", "completed_at"])
        await sync_to_async(record_event)(run, "mars_run_failed", str(exc), {"error": str(exc)})
        raise
    finally:
        await sync_to_async(connections.close_all, thread_sensitive=True)()


async def execute_next_queued_run() -> MarsRun | None:
    run = await sync_to_async(claim_next_run, thread_sensitive=True)()
    if run is None:
        return None
    await execute_mars_run(run.id)
    return run
