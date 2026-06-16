from __future__ import annotations

import contextlib
import json
import re
from typing import Any

from django.conf import settings

from mars.models import MarsRun, MarsSession
from mars.skill_catalog import available_skill_slugs, format_skill_list_for_prompt, skill_catalog_summary

ORCHESTRATION_STRATEGY = "gemini_architect_codex_executor_codex_repair_gemini_reviewer"
ORCHESTRATION_PHASES = ("architect", "executor", "verifier", "repair", "reviewer")
_STATUS_LINE_RE = re.compile(
    r"^\s*STATUS\s*:\s*(needs[_ -]?changes|changes_requested|fail|failed)\b",
    re.I | re.M,
)


def default_orchestrator_roles() -> dict[str, str]:
    return {
        "orchestrator": "mars",
        "architect": "gemini",
        "executor": "codex",
        "repair": "codex",
        "reviewer": "gemini",
        "verifier": "system",
    }


def max_repair_rounds() -> int:
    return max(0, int(getattr(settings, "MARS_ORCHESTRATOR_MAX_REPAIR_ROUNDS", 1)))


def review_repair_rounds() -> int:
    return max(0, int(getattr(settings, "MARS_ORCHESTRATOR_REVIEW_REPAIR_ROUNDS", 1)))


def _ordered_unique(items: list[str] | tuple[str, ...] | None) -> list[str]:
    values: list[str] = []
    for item in items or []:
        value = str(item or "").strip()
        if value and value not in values:
            values.append(value)
    return values


def build_skill_routing(selected_skills: list[str] | tuple[str, ...] | None) -> dict[str, list[str]]:
    selected = _ordered_unique(selected_skills) or available_skill_slugs()
    phase_terms: dict[str, tuple[str, ...]] = {
        "architect": ("design", "brief", "product", "planning", "research", "figma", "ux", "architecture"),
        "executor": ("dev", "app", "web", "frontend", "react", "python", "build", "game", "component", "implementation"),
        "verifier": ("test", "qa", "playwright", "browser", "security", "validation", "debug", "scan"),
        "repair": ("fix", "debug", "repair", "test", "validation", "security", "react", "dev", "best-practices"),
        "reviewer": ("review", "design", "security", "qa", "validation", "best-practices", "accessibility", "audit"),
    }
    limit = max(1, int(getattr(settings, "MARS_PHASE_SKILL_LIMIT", 10)))
    by_phase: dict[str, list[str]] = {}
    for phase, terms in phase_terms.items():
        scored: list[tuple[int, str]] = []
        for skill in selected:
            text = skill.lower()
            score = sum(1 for term in terms if term in text)
            if score:
                scored.append((score, skill))
        scored.sort(key=lambda item: (-item[0], item[1].lower()))
        by_phase[phase] = [skill for _, skill in scored[:limit]] or selected[:limit]
    for phase in ORCHESTRATION_PHASES:
        if not by_phase[phase]:
            by_phase[phase] = selected[:limit]
    return by_phase


def build_orchestration_metadata(selected_skills: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    skill_routing = build_skill_routing(selected_skills)
    return {
        "strategy": ORCHESTRATION_STRATEGY,
        "visibility": "internal",
        "skill_catalog": skill_catalog_summary(),
        "roles": [
            {
                "role": "architect",
                "agent": "gemini",
                "workspace_mode": "read_only",
                "skills": skill_routing["architect"],
                "responsibility": "Turn the approved user request into an implementation contract for Codex.",
            },
            {
                "role": "executor",
                "agent": "codex",
                "workspace_mode": "read_write",
                "skills": skill_routing["executor"],
                "responsibility": "Create or edit project files according to the contract.",
            },
            {
                "role": "verifier",
                "agent": "system",
                "workspace_mode": "read_write",
                "skills": skill_routing["verifier"],
                "responsibility": "Run the configured verification command.",
            },
            {
                "role": "repair",
                "agent": "codex",
                "workspace_mode": "read_write",
                "skills": skill_routing["repair"],
                "responsibility": "Fix verification failures or explicit review blockers.",
            },
            {
                "role": "reviewer",
                "agent": "gemini",
                "workspace_mode": "read_only",
                "skills": skill_routing["reviewer"],
                "responsibility": "Review the final diff and verification output without changing files.",
            },
        ],
        "skill_routing": skill_routing,
        "max_repair_rounds": max_repair_rounds(),
        "review_repair_rounds": review_repair_rounds(),
    }


def merge_runtime_orchestration(
    runtime_control: dict[str, Any] | None,
    *,
    selected_skills: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    data = dict(runtime_control or {})
    data["orchestration"] = build_orchestration_metadata(selected_skills)
    return data


def _session_answer_lines(session: MarsSession) -> list[str]:
    answer_lines: list[str] = []
    answers = session.answers or {}
    for question in session.interview_questions or []:
        question_id = str(question.get("id") or "")
        answer = str(answers.get(question_id) or "").strip()
        if answer:
            answer_lines.append(f"- {question.get('question')}: {answer}")
    return answer_lines


def build_architect_prompt(run: MarsRun) -> str:
    session = run.session
    answer_lines = _session_answer_lines(session)
    phase_skills = build_skill_routing(session.selected_skill_slugs or [])["architect"]
    return "\n\n".join(
        [
            "You are the Gemini architect inside MARS.",
            "Work in read-only mode. Do not modify files.",
            "Your job is to translate the user's project/script request into an implementation contract for Codex.",
            "Use only the phase skills listed below as instruction priorities.",
            "Phase skills:",
            format_skill_list_for_prompt(phase_skills),
            "Be specific about files, behavior, edge cases, verification, and risks.",
            "Return concise Markdown with these sections:",
            "## Build contract\n## Codex tasks\n## Verification\n## Risks",
            f"Workspace root: {run.workspace.root_path}",
            "Approved user plan:",
            session.generated_plan or "",
            "User project/script request:",
            session.task_brief,
            "Clarifying answers:",
            "\n".join(answer_lines) or "No interview answers were saved.",
        ]
    )


def build_codex_executor_prompt(run: MarsRun, architect_brief: str) -> str:
    session = run.session
    answer_lines = _session_answer_lines(session)
    phase_skills = build_skill_routing(session.selected_skill_slugs or [])["executor"]
    return "\n\n".join(
        [
            "You are the Codex executor inside MARS.",
            "Create or edit the requested project, script, automation, bot, site, or utility.",
            "Do not read or write outside the provided workspace root.",
            "Do not commit, push, or change git remotes.",
            "Use the phase skills as instruction packs, not as permission grants.",
            "Implement only the approved user goal. If a required detail is missing, choose the smallest safe implementation and report the assumption.",
            f"Workspace root: {run.workspace.root_path}",
            "Phase skills:",
            format_skill_list_for_prompt(phase_skills),
            "Gemini architect contract:",
            architect_brief or "No Gemini architect contract was produced; use the approved plan and answers directly.",
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


def build_codex_repair_prompt(
    run: MarsRun,
    *,
    repair_reason: str,
    verification_output: str = "",
    gemini_review: str = "",
    repair_round: int,
) -> str:
    phase_skills = build_skill_routing(run.session.selected_skill_slugs or [])["repair"]
    return "\n\n".join(
        [
            f"You are the Codex repair agent inside MARS. Repair round: {repair_round}.",
            "Fix only the concrete failure or blocker below.",
            "Do not rewrite unrelated parts of the project.",
            "Do not commit, push, or change git remotes.",
            "Use only repair-relevant phase skills.",
            "Phase skills:",
            format_skill_list_for_prompt(phase_skills),
            f"Workspace root: {run.workspace.root_path}",
            "Approved plan:",
            run.session.generated_plan or "",
            "Current Codex summary:",
            run.codex_summary or "",
            "Repair reason:",
            repair_reason,
            "Verification output:",
            verification_output or "No verification output provided.",
            "Gemini review:",
            gemini_review or "No Gemini review provided.",
            "Final response contract:",
            "- Summarize the repair.",
            "- List changed files.",
            "- State what should be rechecked.",
        ]
    )


def build_gemini_review_prompt(run: MarsRun, architect_brief: str) -> str:
    phase_skills = build_skill_routing(run.session.selected_skill_slugs or [])["reviewer"]
    return "\n\n".join(
        [
            "You are the Gemini reviewer inside MARS.",
            "Review this coding-agent run in read-only mode. Do not modify files.",
            "Focus on correctness, security, changed files, missing verification, and whether the project/script satisfies the approved request.",
            "Use only reviewer-relevant phase skills.",
            "Phase skills:",
            format_skill_list_for_prompt(phase_skills),
            "Start your response with exactly one status line:",
            "STATUS: pass",
            "or",
            "STATUS: needs_changes",
            "Use STATUS: needs_changes only for concrete blockers that Codex should repair.",
            f"Workspace root: {run.workspace.root_path}",
            "Gemini architect contract:",
            architect_brief or "No architect contract was produced.",
            "Approved plan:",
            run.session.generated_plan or "",
            "Codex summary:",
            run.codex_summary or "",
            "Verification output:",
            run.test_output or "No verification command configured.",
            "Git diff summary:",
            run.git_after or "",
        ]
    )


def _walk_json_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for item in value.values():
            strings.extend(_walk_json_strings(item))
        return strings
    if isinstance(value, list):
        strings: list[str] = []
        for item in value:
            strings.extend(_walk_json_strings(item))
        return strings
    return []


def _gemini_text_fragments(output: str) -> str:
    fragments: list[str] = []
    for line in (output or "").splitlines():
        with contextlib.suppress(json.JSONDecodeError):
            fragments.extend(_walk_json_strings(json.loads(line)))
    return "\n".join(fragments)


def review_requests_changes(review_output: str) -> bool:
    return bool(_STATUS_LINE_RE.search(review_output or "") or _STATUS_LINE_RE.search(_gemini_text_fragments(review_output)))
