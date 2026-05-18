from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

GREETING_WORDS = {
    "hi",
    "hello",
    "hey",
    "привет",
    "здравствуй",
    "здравствуйте",
    "добрый день",
    "доброе утро",
    "добрый вечер",
}

THANKS_WORDS = {
    "thanks",
    "thank you",
    "спасибо",
    "благодарю",
}

QUESTION_STARTS = {
    "что",
    "как",
    "почему",
    "зачем",
    "когда",
    "где",
    "можешь объяснить",
    "расскажи",
    "what",
    "how",
    "why",
    "when",
    "where",
}

TASK_MARKERS = {
    "сделай",
    "добавь",
    "исправь",
    "почини",
    "создай",
    "напиши",
    "проверь",
    "обнови",
    "переделай",
    "реализуй",
    "удали",
    "найди",
    "запусти",
    "fix",
    "add",
    "create",
    "write",
    "implement",
    "update",
    "remove",
    "check",
    "run",
}

VAGUE_WORDS = {
    "fix",
    "improve",
    "optimize",
    "refactor",
    "улучши",
    "исправь",
    "оптимизируй",
    "сделай лучше",
    "почини",
}


@dataclass
class DelegationDraft:
    prompt: str
    source: str = ""
    branch: str = ""
    title: str = ""


@dataclass(frozen=True)
class CoordinatorDecision:
    ready: bool
    question: str = ""
    draft: DelegationDraft | None = None


class MessageIntent(str, Enum):
    GREETING = "greeting"
    THANKS = "thanks"
    QUESTION = "question"
    TASK = "task"
    UNKNOWN = "unknown"


class Coordinator:
    """Small deterministic coordinator for Telegram messages.

    It does not pretend to be a coding model. It keeps the handoff to Jules scoped
    and asks for missing repository/task details before starting a remote session.
    """

    def __init__(self, *, default_source: str, default_branch: str) -> None:
        self.default_source = default_source
        self.default_branch = default_branch

    def build_draft(self, text: str, *, source: str = "", branch: str = "", title: str = "") -> DelegationDraft:
        return DelegationDraft(
            prompt=text.strip(),
            source=source.strip() or self.default_source,
            branch=branch.strip() or self.default_branch,
            title=title.strip() or self._title_from_prompt(text),
        )

    def evaluate(self, draft: DelegationDraft) -> CoordinatorDecision:
        missing: list[str] = []
        if not draft.source:
            missing.append("Jules source/repository")
        if not draft.branch:
            missing.append("branch")
        if not draft.prompt:
            missing.append("task description")

        if missing:
            return CoordinatorDecision(
                ready=False,
                question=(
                    "Need more context before I delegate this to Jules: "
                    + ", ".join(missing)
                    + ". Send it as: source=<source> branch=<branch> task=<what to do>."
                ),
                draft=draft,
            )

        if self._is_too_vague(draft.prompt):
            return CoordinatorDecision(
                ready=False,
                question=(
                    "The task is too broad for a long-running Jules session. Add the target area, expected behavior, "
                    "and how Jules should verify it. Example: source=<source> branch=<branch> task=Fix X in Y, add tests Z."
                ),
                draft=draft,
            )

        return CoordinatorDecision(ready=True, draft=draft)

    def build_jules_prompt(self, draft: DelegationDraft) -> str:
        return "\n".join(
            [
                "Work as an autonomous coding agent on this repository.",
                "Follow the repository AGENTS.md instructions if present.",
                "Use any tools, MCP servers, skills, or repository automation available in your Jules environment when they help.",
                "If a needed tool or permission is missing, report the blocker instead of guessing.",
                "Keep the change scoped to the task. Add or update focused tests when behavior changes.",
                "Run the most relevant checks you can. If a check cannot run, explain the blocker.",
                "",
                "Task:",
                draft.prompt,
            ]
        )

    def classify_message(self, text: str) -> MessageIntent:
        cleaned = " ".join(text.lower().strip().split())
        if not cleaned:
            return MessageIntent.UNKNOWN
        if cleaned in GREETING_WORDS:
            return MessageIntent.GREETING
        if cleaned in THANKS_WORDS:
            return MessageIntent.THANKS
        if "?" in cleaned or any(cleaned.startswith(prefix) for prefix in QUESTION_STARTS):
            return MessageIntent.QUESTION
        if any(marker in cleaned for marker in TASK_MARKERS):
            return MessageIntent.TASK
        if len(cleaned.split()) >= 6:
            return MessageIntent.TASK
        return MessageIntent.UNKNOWN

    def update_draft_from_text(self, draft: DelegationDraft, text: str) -> DelegationDraft:
        updates = self.parse_key_values(text)
        prompt = updates.get("task") or updates.get("prompt") or draft.prompt
        source = updates.get("source") or updates.get("repo") or draft.source
        branch = updates.get("branch") or draft.branch
        title = updates.get("title") or draft.title
        if not updates and text.strip():
            prompt = f"{draft.prompt}\n\nAdditional context:\n{text.strip()}" if draft.prompt else text.strip()
        return DelegationDraft(prompt=prompt, source=source, branch=branch, title=title)

    @staticmethod
    def parse_key_values(text: str) -> dict[str, str]:
        result: dict[str, str] = {}
        normalized = text.replace("\r\n", "\n").strip()
        for part in normalized.splitlines():
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            if key in {"source", "repo", "branch", "task", "prompt", "title"} and value:
                result[key] = value
        return result

    @staticmethod
    def _title_from_prompt(prompt: str) -> str:
        title = " ".join(prompt.strip().split())
        if len(title) <= 70:
            return title or "Jules task"
        return title[:69].rstrip() + "..."

    @staticmethod
    def _is_too_vague(prompt: str) -> bool:
        cleaned = " ".join(prompt.lower().split())
        if len(cleaned) < 18:
            return True
        return cleaned in VAGUE_WORDS or any(cleaned == word for word in VAGUE_WORDS)
