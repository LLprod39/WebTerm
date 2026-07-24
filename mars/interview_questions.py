from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from django.conf import settings

from mars.interview_questions_dynamic import (
    QUESTION_KIND_CHOICES,
    _base_dynamic_questions,
    _closing_dynamic_questions,
    _domain_dynamic_questions,
    _question,
    _task_domains,
)
from mars.policy import MarsPolicyError

CURATED_SKILLS = ["frontend-design", "frontend-dev", "react-best-practices", "frontend-testing-debugging"]
PERSONAL_WORKSPACE_NAME = "Personal workspace"

QUESTION_BANK: list[dict[str, Any]] = []
MARS_INTERVIEW_SYSTEM_PROMPT = """You generate a coding-agent clarification interview.
Return only JSON with this shape:
{"questions":[{"id":"short_snake_case","question":"Russian question","kind":"choice_text|multi_choice_text|textarea","options":["2-6 concise Russian options"],"placeholder":"optional Russian placeholder","required":true}]}
Rules:
- Generate 8-10 questions specific to the user's exact software task.
- Do not use generic canned wording if the task gives a concrete domain.
- Each question must help produce an implementation goal, scope, UX, constraints, verification, and risk.
- Options must be task-specific and selectable by a human.
- Keep questions and options short enough for a compact UI.
- No filesystem permissions, secrets, or destructive actions.
"""

MARS_INTERVIEW_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["questions"],
    "properties": {
        "questions": {
            "type": "array",
            "minItems": 5,
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "question", "kind", "options", "placeholder", "required"],
                "properties": {
                    "id": {"type": "string", "minLength": 2, "maxLength": 56},
                    "question": {"type": "string", "minLength": 8, "maxLength": 180},
                    "kind": {"type": "string", "enum": ["choice_text", "multi_choice_text", "textarea"]},
                    "options": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 6,
                        "items": {"type": "string", "minLength": 1, "maxLength": 80},
                    },
                    "placeholder": {"type": "string", "maxLength": 180},
                    "required": {"type": "boolean"},
                },
            },
        },
    },
}


class MarsInterviewError(MarsPolicyError):
    """Raised when Codex CLI cannot produce a valid MARS interview."""


def _build_local_interview_questions(task_brief: str) -> list[dict[str, Any]]:
    domains = _task_domains(task_brief)
    questions = [
        *_base_dynamic_questions(task_brief, domains),
        *_domain_dynamic_questions(task_brief, domains),
        *_closing_dynamic_questions(task_brief, domains),
    ]
    return _normalize_interview_questions({"questions": questions}, task_brief, min_count=8) or questions


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        return {}
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_question_id(raw_value: object, used_ids: set[str], fallback_index: int) -> str:
    raw = re.sub(r"[^a-z0-9_]+", "_", str(raw_value or "").strip().lower()).strip("_")
    if not raw:
        raw = f"ai_question_{fallback_index}"
    raw = raw[:48]
    candidate = raw
    counter = 2
    while candidate in used_ids:
        candidate = f"{raw}_{counter}"[:56]
        counter += 1
    used_ids.add(candidate)
    return candidate


def _string_list(value: object, *, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = re.sub(r"\s+", " ", str(item or "").strip())
        if text and text not in result:
            result.append(text[:80])
        if len(result) >= limit:
            break
    return result


def _normalize_interview_questions(raw_value: object, task_brief: str, *, min_count: int = 5) -> list[dict[str, Any]]:
    payload = raw_value if isinstance(raw_value, dict) else {}
    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list):
        return []

    used_ids: set[str] = set()
    questions: list[dict[str, Any]] = []
    for index, item in enumerate(raw_questions[:12], start=1):
        if not isinstance(item, dict):
            continue
        question_text = re.sub(r"\s+", " ", str(item.get("question") or "").strip())
        if not question_text:
            continue
        kind = str(item.get("kind") or "choice_text").strip()
        if kind not in QUESTION_KIND_CHOICES:
            kind = "multi_choice_text" if "multi" in kind else "choice_text"
        options = _string_list(item.get("options"), limit=6)
        if kind != "textarea" and len(options) < 2:
            continue
        if kind == "textarea" and not options:
            options = ["Написать вручную"]
        question_id = _safe_question_id(item.get("id"), used_ids, index)
        questions.append(
            _question(
                question_id,
                question_text[:180],
                kind,
                options,
                required=bool(item.get("required", True)),
                placeholder=str(item.get("placeholder") or "").strip()[:180],
            )
        )

    if len(questions) < min_count:
        return []
    if not any(question["id"] == "success_criteria" for question in questions):
        questions[0]["id"] = "success_criteria"
    return questions[:10]


async def _call_interview_llm(task_brief: str) -> str:
    from app.agent_kernel.memory.redaction import sanitize_prompt_context_text
    from app.core.llm import LLMProvider

    safe_task = sanitize_prompt_context_text(task_brief).text.strip()[:2500]
    prompt = (
        "Generate a MARS coding-agent interview for this task.\n"
        f"Task: {safe_task}\n\n"
        "Return JSON only. Questions and options must be in Russian and specific to this task."
    )
    provider = LLMProvider()
    chunks: list[str] = []
    async for chunk in provider.stream_chat(
        prompt,
        model="auto",
        purpose="chat",
        system_prompt=MARS_INTERVIEW_SYSTEM_PROMPT,
        json_mode=True,
    ):
        chunks.append(chunk)
    return "".join(chunks)


def _build_llm_interview_questions(task_brief: str) -> list[dict[str, Any]]:
    if not getattr(settings, "MARS_INTERVIEW_LLM_ENABLED", False):
        return []
    loop = asyncio.new_event_loop()
    try:
        raw_response = loop.run_until_complete(_call_interview_llm(task_brief))
    except Exception:
        return []
    finally:
        loop.close()
    if raw_response.strip().lower().startswith("error:"):
        return []
    return _normalize_interview_questions(_extract_json_object(raw_response), task_brief, min_count=8)
