from __future__ import annotations

import asyncio
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from django.conf import settings

from mars.interview_questions import (
    CURATED_SKILLS,
    MARS_INTERVIEW_OUTPUT_SCHEMA,
    MARS_INTERVIEW_SYSTEM_PROMPT,
    MarsInterviewError,
    _extract_json_object,
    _normalize_interview_questions,
)
from mars.runtime_cli import (
    _command_prefix,
    build_mars_agent_docker_command,
    cli_path_for_command,
    docker_container_child_path,
    docker_workspace_path,
    mars_agent_uses_docker,
    subprocess_env_for_cli,
)
from mars.subprocess_compat import run_process_capture


def _build_codex_interview_prompt(task_brief: str, workspace_root: Path, selected_skills: list[str] | None = None) -> str:
    safe_task = re.sub(r"\s+", " ", (task_brief or "").strip())[:2500]
    skills = ", ".join(selected_skills or CURATED_SKILLS)
    return "\n\n".join(
        [
            MARS_INTERVIEW_SYSTEM_PROMPT,
            "You are the real Codex CLI interview step for MARS.",
            "Generate the questions yourself for this exact task; do not reuse generic templates.",
            "Do not modify files. Do not run destructive commands. Read-only workspace inspection is allowed only if useful.",
            f"Workspace root: {workspace_root}",
            f"Available instruction-pack skills: {skills}",
            "User task:",
            safe_task,
            "Return JSON only. The final response must validate against the provided output schema.",
        ]
    )


def _extract_codex_final_text(stdout_text: str, output_text: str) -> str:
    if output_text.strip():
        return output_text
    candidates: list[str] = []
    for line in stdout_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            candidates.append(line)
            continue
        if isinstance(event, dict):
            for key in ("message", "content", "text", "final_output", "last_message"):
                value = event.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value)
            if isinstance(event.get("payload"), dict):
                payload = event["payload"]
                for key in ("message", "content", "text"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        candidates.append(value)
    return "\n".join(candidates[-3:])


async def _run_codex_interview_process(
    *,
    task_brief: str,
    workspace_root: Path,
    selected_skills: list[str] | None = None,
) -> list[dict[str, Any]]:
    interview_dir = Path(settings.MEDIA_ROOT) / "mars_interviews"
    interview_dir.mkdir(parents=True, exist_ok=True)
    timeout_seconds = int(getattr(settings, "MARS_INTERVIEW_CODEX_TIMEOUT_SECONDS", 180))
    command = _command_prefix(
        getattr(settings, "MARS_AGENT_DOCKER_CODEX_COMMAND", "codex")
        if mars_agent_uses_docker()
        else getattr(settings, "MARS_INTERVIEW_CODEX_COMMAND", None) or getattr(settings, "MARS_CODEX_COMMAND", None),
        "codex",
    )

    with tempfile.TemporaryDirectory(prefix="interview_", dir=interview_dir) as tmp_name:
        tmp_dir = Path(tmp_name)
        schema_path = tmp_dir / "interview-schema.json"
        output_path = tmp_dir / "codex-interview.json"
        schema_path.write_text(json.dumps(MARS_INTERVIEW_OUTPUT_SCHEMA, ensure_ascii=False), encoding="utf-8")

        workspace_cli_path = docker_workspace_path() if mars_agent_uses_docker() else cli_path_for_command(command, workspace_root)
        schema_cli_path = (
            docker_container_child_path("/mars-interview", tmp_dir, schema_path)
            if mars_agent_uses_docker()
            else cli_path_for_command(command, schema_path)
        )
        output_cli_path = (
            docker_container_child_path("/mars-interview", tmp_dir, output_path)
            if mars_agent_uses_docker()
            else cli_path_for_command(command, output_path)
        )
        codex_inner_cmd = command + [
            "--ask-for-approval",
            "never",
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--json",
            "--cd",
            workspace_cli_path,
            "--sandbox",
            "read-only",
            "--output-schema",
            schema_cli_path,
            "--output-last-message",
            output_cli_path,
            "-",
        ]
        codex_cmd = (
            build_mars_agent_docker_command(
                phase="interview",
                workspace_root=workspace_root,
                workspace_mode="ro",
                inner_command=codex_inner_cmd,
                extra_mounts=[(tmp_dir, "/mars-interview", "rw")],
                include_codex_home=True,
            )
            if mars_agent_uses_docker()
            else codex_inner_cmd
        )
        prompt = _build_codex_interview_prompt(task_brief, workspace_root, selected_skills)

        try:
            returncode, stdout_text, stderr_text = await run_process_capture(
                codex_cmd,
                cwd=str(workspace_root),
                env=None if mars_agent_uses_docker() else subprocess_env_for_cli(command),
                stdin_text=prompt,
                timeout_seconds=timeout_seconds,
            )
        except OSError as exc:
            raise MarsInterviewError(f"Codex CLI is not available for MARS interview: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise MarsInterviewError("Codex CLI interview timed out.") from exc

        if returncode != 0:
            combined_output = "\n".join(
                part for part in [stderr_text.strip(), stdout_text.strip()] if part
            ) or "No Codex output."
            details = combined_output.strip().splitlines()
            raise MarsInterviewError(f"Codex CLI interview failed: {' '.join(details[-3:])[:600]}")

        output_text = output_path.read_text(encoding="utf-8", errors="replace") if output_path.exists() else ""
        raw_text = _extract_codex_final_text(stdout_text, output_text)
        questions = _normalize_interview_questions(_extract_json_object(raw_text), task_brief, min_count=5)
        if len(questions) < 5:
            raise MarsInterviewError("Codex CLI did not return valid interview JSON.")
        return questions


def _build_codex_interview_questions(
    task_brief: str,
    *,
    workspace_root: str | Path,
    selected_skills: list[str] | None = None,
) -> list[dict[str, Any]]:
    root = Path(workspace_root).expanduser().resolve(strict=False)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            _run_codex_interview_process(
                task_brief=task_brief,
                workspace_root=root,
                selected_skills=selected_skills,
            )
        )
    finally:
        loop.close()

