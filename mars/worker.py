from __future__ import annotations

import asyncio
import contextlib
import json
import shlex
from pathlib import Path
from typing import Any

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connections
from django.utils import timezone
from loguru import logger

from mars.models import MarsRun, MarsSession
from mars.policy import MarsPolicyError, build_workspace_policy, git_status
from mars.services import (
    build_mars_agent_docker_command,
    claim_next_run,
    cli_path_for_command,
    docker_container_child_path,
    docker_workspace_path,
    mars_agent_uses_docker,
    record_event,
    require_personal_workspace,
    subprocess_env_for_cli,
)


def _command_prefix(value: Any, default: str) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    raw = str(value or default).strip()
    return [raw] if raw else [default]


def _run_dir(run_id: int) -> Path:
    path = Path(settings.MEDIA_ROOT) / "mars_runs" / str(run_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _build_codex_prompt(run: MarsRun) -> str:
    session = run.session
    answer_lines: list[str] = []
    answers = session.answers or {}
    for question in session.interview_questions or []:
        question_id = str(question.get("id") or "")
        answer = str(answers.get(question_id) or "").strip()
        if answer:
            answer_lines.append(f"- {question.get('question')}: {answer}")
    return "\n\n".join(
        [
            "You are MARS Coding Agent running inside a bounded workspace.",
            "Do not read or write outside the provided workspace root.",
            "Do not commit, push, or change git remotes.",
            "Use the selected skills as instruction packs, not as permission grants.",
            "Implement only the approved user goal. If a required detail is missing, choose the smallest safe implementation and report the assumption.",
            f"Workspace root: {run.workspace.root_path}",
            f"Selected skills: {', '.join(session.selected_skill_slugs or [])}",
            "Approved plan:",
            session.generated_plan or "",
            "Task brief:",
            session.task_brief,
            "User interview answers:",
            "\n".join(answer_lines) or "No interview answers were saved.",
            "Final response contract:",
            "- Summarize what changed.",
            "- List changed files.",
            "- Include verification commands and results.",
            "- Call out remaining risks or skipped checks.",
        ]
    )


def _build_gemini_prompt(run: MarsRun) -> str:
    return "\n\n".join(
        [
            "Review this coding-agent run in read-only mode.",
            "Focus on correctness, security, changed files, and missing verification.",
            "Do not modify files.",
            f"Workspace root: {run.workspace.root_path}",
            "Approved plan:",
            run.session.generated_plan or "",
            "Codex summary:",
            run.codex_summary or "",
            "Git diff summary:",
            run.git_after or "",
        ]
    )


async def _save_instance(instance, update_fields: list[str]) -> None:
    await sync_to_async(instance.save, thread_sensitive=True)(update_fields=update_fields)


async def _stop_requested(run_id: int) -> bool:
    run = await sync_to_async(lambda: MarsRun.objects.filter(pk=run_id).only("runtime_control", "status").first())()
    if run is None:
        return True
    if run.status == MarsRun.STATUS_STOPPED:
        return True
    return bool((run.runtime_control or {}).get("stop_requested"))


async def _stream_process(
    run: MarsRun,
    *,
    command: list[str],
    cwd: str,
    stdin_text: str = "",
    event_prefix: str,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    await sync_to_async(record_event)(run, f"{event_prefix}_started", f"Starting {event_prefix}", {"command": command})
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.PIPE if stdin_text else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if stdin_text and process.stdin:
        process.stdin.write(stdin_text.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

    output_chunks: list[str] = []

    async def read_stream(stream: asyncio.StreamReader | None, stream_name: str) -> None:
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            output_chunks.append(text)
            payload: dict[str, Any] = {"stream": stream_name, "text": text[:4000]}
            with contextlib.suppress(json.JSONDecodeError):
                payload["json"] = json.loads(text)
            await sync_to_async(record_event)(run, f"{event_prefix}_{stream_name}", text[:1000], payload)
            if await _stop_requested(run.id):
                process.terminate()
                await sync_to_async(record_event)(run, "mars_run_stop_requested", "Stop requested")
                break

    stdout_task = asyncio.create_task(read_stream(process.stdout, "stdout"))
    stderr_task = asyncio.create_task(read_stream(process.stderr, "stderr"))
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        await sync_to_async(record_event)(run, f"{event_prefix}_timeout", f"{event_prefix} timed out")
        await process.wait()
    finally:
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

    exit_code = int(process.returncode or 0)
    await sync_to_async(record_event)(run, f"{event_prefix}_finished", f"{event_prefix} exited {exit_code}", {"exit_code": exit_code})
    return exit_code, "\n".join(output_chunks)[-120_000:]


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
        codex_final = run_dir / "codex-final.md"
        codex_prefix = _command_prefix(
            getattr(settings, "MARS_AGENT_DOCKER_CODEX_COMMAND", "codex")
            if docker_runtime
            else getattr(settings, "MARS_CODEX_COMMAND", None),
            "codex",
        )
        codex_output_path = (
            docker_container_child_path("/mars-run", run_dir, codex_final)
            if docker_runtime
            else cli_path_for_command(codex_prefix, codex_final)
        )
        codex_inner_cmd = codex_prefix + [
            "--ask-for-approval",
            "never",
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--json",
            "--cd",
            docker_workspace_path() if docker_runtime else cli_path_for_command(codex_prefix, policy.root),
            "--sandbox",
            "workspace-write",
            "--output-last-message",
            codex_output_path,
            "-",
        ]
        codex_cmd = (
            build_mars_agent_docker_command(
                phase=f"codex-{run.id}",
                workspace_root=policy.root,
                workspace_mode="rw",
                inner_command=codex_inner_cmd,
                extra_mounts=[(run_dir, "/mars-run", "rw")],
                include_codex_home=True,
            )
            if docker_runtime
            else codex_inner_cmd
        )
        codex_exit, codex_output = await _stream_process(
            run,
            command=codex_cmd,
            cwd=str(policy.root),
            stdin_text=_build_codex_prompt(run),
            event_prefix="codex",
            timeout_seconds=int(getattr(settings, "MARS_CODEX_TIMEOUT_SECONDS", 1800)),
            env=None if docker_runtime else subprocess_env_for_cli(codex_prefix),
        )
        final_text = codex_final.read_text(encoding="utf-8", errors="replace") if codex_final.exists() else codex_output[-12000:]
        run.codex_summary = final_text
        await _save_instance(run, ["codex_summary"])
        if codex_exit != 0:
            raise RuntimeError(f"Codex exited with code {codex_exit}")
        if await _stop_requested(run.id):
            run.status = MarsRun.STATUS_STOPPED
            run.completed_at = timezone.now()
            await _save_instance(run, ["status", "completed_at"])
            return

        runtime_control = run.runtime_control or {}
        test_command = str(runtime_control.get("test_command") or "").strip()
        if test_command:
            test_parts = shlex.split(test_command, posix=False)
            test_cmd = (
                build_mars_agent_docker_command(
                    phase=f"tests-{run.id}",
                    workspace_root=policy.root,
                    workspace_mode="rw",
                    inner_command=test_parts,
                )
                if docker_runtime
                else test_parts
            )
            test_exit, test_output = await _stream_process(
                run,
                command=test_cmd,
                cwd=str(policy.root),
                event_prefix="tests",
                timeout_seconds=int(getattr(settings, "MARS_TEST_TIMEOUT_SECONDS", 900)),
            )
            run.test_output = test_output[-40000:]
            await _save_instance(run, ["test_output"])
            if test_exit != 0:
                await sync_to_async(record_event)(run, "tests_failed", "Configured verification failed", {"exit_code": test_exit})
        else:
            await sync_to_async(record_event)(run, "tests_skipped", "No verification command configured")

        run.git_after = await sync_to_async(git_status)(str(policy.root))
        await _save_instance(run, ["git_after"])

        gemini_prefix = _command_prefix(
            getattr(settings, "MARS_AGENT_DOCKER_GEMINI_COMMAND", "gemini")
            if docker_runtime
            else getattr(settings, "MARS_GEMINI_COMMAND", None),
            "gemini",
        )
        gemini_inner_cmd = gemini_prefix + [
            "--prompt",
            _build_gemini_prompt(run),
            "--approval-mode",
            "plan",
            "--output-format",
            "stream-json",
            "--include-directories",
            docker_workspace_path() if docker_runtime else cli_path_for_command(gemini_prefix, policy.root),
        ]
        gemini_cmd = (
            build_mars_agent_docker_command(
                phase=f"gemini-{run.id}",
                workspace_root=policy.root,
                workspace_mode="ro",
                inner_command=gemini_inner_cmd,
                include_gemini_home=True,
            )
            if docker_runtime
            else gemini_inner_cmd
        )
        gemini_exit, gemini_output = await _stream_process(
            run,
            command=gemini_cmd,
            cwd=str(policy.root),
            event_prefix="gemini",
            timeout_seconds=int(getattr(settings, "MARS_GEMINI_TIMEOUT_SECONDS", 900)),
        )
        run.gemini_review = gemini_output[-40000:]
        if gemini_exit != 0:
            await sync_to_async(record_event)(run, "gemini_review_failed", "Gemini review failed", {"exit_code": gemini_exit})

        run.final_report = "\n\n".join(
            [
                "# MARS final report",
                "## Codex",
                run.codex_summary or "",
                "## Verification",
                run.test_output or "No verification command configured.",
                "## Gemini review",
                run.gemini_review or "No Gemini review output.",
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
