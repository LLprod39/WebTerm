"""Heuristic complexity classification for terminal / agent goals.

Pure functions — no Django, SSH, or LLM. Used by Fast routing to avoid
silently half-executing multi-step ops under a short linear plan, and by
Multi planning to prefer verify-oriented plan structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

ComplexityLevel = Literal["simple", "medium", "complex"]
FastComplexPolicy = Literal["ask", "upgrade", "allow"]

# Multi-word / phrase signals for complex ops (RU + EN).
_COMPLEX_PHRASES: tuple[str, ...] = (
    "root cause",
    "post-change",
    "post change",
    "health check",
    "smoke test",
    "roll back",
    "multi-server",
    "multi server",
    "найди причину",
    "корневая причина",
    "разберись",
    "почини",
    "исправь",
    "проверь после",
    "после изменений",
    "откати",
    "откатить",
    "разверни",
    "задеплой",
    "миграция",
    "мигрируй",
)

_COMPLEX_KEYWORDS: tuple[str, ...] = (
    "migrate",
    "migration",
    "incident",
    "outage",
    "downtime",
    "deploy",
    "rollout",
    "rollback",
    "production",
    "prod",
    "firewall",
    "iptables",
    "ufw",
    "nginx",
    "systemd",
    "docker",
    "compose",
    "kubernetes",
    "k8s",
    "certificate",
    "ssl",
    "tls",
    "database",
    "postgres",
    "mysql",
    "redis",
    "cluster",
    "recovery",
    "restore",
    "backup",
    "инцидент",
    "деплой",
    "релиз",
    "откат",
    "продакшн",
    "production",
    "фаервол",
    "firewall",
    "сертификат",
    "кластер",
    "восстанов",
    "бэкап",
    "backup",
    "диагност",
    "расслед",
)

_MEDIUM_KEYWORDS: tuple[str, ...] = (
    "restart",
    "reload",
    "install",
    "upgrade",
    "update",
    "configure",
    "config",
    "status",
    "logs",
    "journal",
    "перезапуск",
    "установ",
    "обнов",
    "настрой",
    "конфиг",
    "логи",
    "журнал",
    "проверь",
    "check",
    "verify",
    "validate",
)

_SIMPLE_ONLY_HINTS: tuple[str, ...] = (
    "what is",
    "how does",
    "explain",
    "что такое",
    "как работает",
    "объясни",
    "привет",
    "hello",
    "thanks",
    "спасибо",
)


@dataclass(frozen=True)
class ComplexityAssessment:
    level: ComplexityLevel
    score: int
    reasons: tuple[str, ...]

    @property
    def is_complex(self) -> bool:
        return self.level == "complex"

    @property
    def is_simple(self) -> bool:
        return self.level == "simple"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def classify_goal_complexity(
    user_message: str,
    *,
    planned_command_count: int | None = None,
    planner_execution_mode: str | None = None,
) -> ComplexityAssessment:
    """Score a goal and return simple | medium | complex."""
    text = _normalize_text(user_message)
    reasons: list[str] = []
    score = 0

    if not text:
        return ComplexityAssessment(level="simple", score=0, reasons=("empty",))

    if any(hint in text for hint in _SIMPLE_ONLY_HINTS) and len(text) < 80:
        return ComplexityAssessment(level="simple", score=0, reasons=("conversational_or_theory",))

    phrase_hits = [p for p in _COMPLEX_PHRASES if p in text]
    if phrase_hits:
        score += 3 * min(3, len(phrase_hits))
        reasons.append(f"complex_phrases:{len(phrase_hits)}")

    kw_hits = [k for k in _COMPLEX_KEYWORDS if re.search(rf"\b{re.escape(k)}\b", text) or k in text]
    # de-dupe while preserving order
    seen: set[str] = set()
    unique_kw: list[str] = []
    for k in kw_hits:
        if k not in seen:
            seen.add(k)
            unique_kw.append(k)
    if unique_kw:
        score += min(6, len(unique_kw) * 2)
        reasons.append(f"complex_keywords:{','.join(unique_kw[:5])}")

    med_hits = [k for k in _MEDIUM_KEYWORDS if k in text]
    if med_hits:
        score += min(3, len(set(med_hits)))
        reasons.append(f"medium_keywords:{len(set(med_hits))}")

    # Multi-step enumeration: "1) ... 2) ..." or "1. ... 2."
    step_markers = len(re.findall(r"(?:^|\s)(?:\d+[\).]|[-*])\s+\S", text))
    if step_markers >= 3:
        score += 4
        reasons.append(f"enumerated_steps:{step_markers}")
    elif step_markers == 2:
        score += 2
        reasons.append("enumerated_steps:2")

    # Conjunction chains often imply multi-part goals.
    and_count = len(re.findall(r"\b(?:и|and|then|потом|затем|после)\b", text))
    if and_count >= 3:
        score += 3
        reasons.append(f"conjunctions:{and_count}")
    elif and_count == 2:
        score += 1
        reasons.append("conjunctions:2")

    if len(text) >= 280:
        score += 2
        reasons.append("long_goal")
    elif len(text) >= 140:
        score += 1
        reasons.append("medium_length")

    cmd_count = int(planned_command_count or 0)
    if cmd_count >= 8:
        score += 4
        reasons.append(f"plan_commands:{cmd_count}")
    elif cmd_count >= 5:
        score += 2
        reasons.append(f"plan_commands:{cmd_count}")

    planner_mode = str(planner_execution_mode or "").strip().lower()
    if planner_mode == "step" and cmd_count >= 3:
        score += 1
        reasons.append("planner_prefers_step")

    if score >= 6:
        level: ComplexityLevel = "complex"
    elif score >= 3:
        level = "medium"
    else:
        level = "simple"

    if not reasons:
        reasons.append("default")
    return ComplexityAssessment(level=level, score=score, reasons=tuple(reasons))


def resolve_fast_complex_action(
    assessment: ComplexityAssessment,
    *,
    requested_mode: str,
    policy: FastComplexPolicy = "ask",
) -> dict[str, Any]:
    """Decide how Fast mode should treat a classified goal.

    Returns a dict with:
      - action: ``allow`` | ``ask`` | ``upgrade``
      - execution_mode: recommended mode if continuing
      - assistant_text: optional RU message when blocking silent execute
    """
    mode = str(requested_mode or "fast").strip().lower()
    if mode in ("agent", "nova", "react"):
        return {"action": "allow", "execution_mode": "agent", "assistant_text": "", "assessment": assessment}

    if assessment.level != "complex":
        # Medium/simple stay on Fast/step as requested.
        return {
            "action": "allow",
            "execution_mode": mode if mode in ("fast", "step", "auto") else "fast",
            "assistant_text": "",
            "assessment": assessment,
        }

    pol = policy if policy in ("ask", "upgrade", "allow") else "ask"
    if pol == "allow":
        return {
            "action": "allow",
            "execution_mode": "step",  # still force adaptive step over blind fast batch
            "assistant_text": "",
            "assessment": assessment,
        }
    if pol == "upgrade":
        return {
            "action": "upgrade",
            "execution_mode": "agent",
            "assistant_text": (
                "Задача выглядит сложной для Fast (короткий линейный план). "
                "Переключаю на Nova — адаптивный агент с проверками по ходу."
            ),
            "assessment": assessment,
        }
    # default: ask — do not silently half-execute
    return {
        "action": "ask",
        "execution_mode": "fast",
        "assistant_text": (
            "Эта задача похожа на сложную multi-step ops-работу "
            f"(признаки: {', '.join(assessment.reasons[:4])}). "
            "В Fast доступен только короткий линейный план — он часто обрывается на середине. "
            "Переключите режим на **Nova (agent)** для разведки → действий → проверки, "
            "или уточните одну короткую цель для Fast."
        ),
        "assessment": assessment,
    }


def plan_mentions_mutation(tasks: list[dict[str, Any]] | None) -> bool:
    """Heuristic: does any planned multi-agent task look mutating?"""
    mutate_markers = (
        "restart",
        "reload",
        "deploy",
        "install",
        "upgrade",
        "migrate",
        "delete",
        "remove",
        "chmod",
        "chown",
        "edit",
        "patch",
        "apply",
        "fix",
        "rollback",
        "start",
        "stop",
        "enable",
        "disable",
        "write",
        "sed ",
        "systemctl",
        "docker run",
        "docker compose up",
        "nginx -s",
        "перезапуск",
        "исправ",
        "почин",
        "удал",
        "установ",
        "настрой",
        "деплой",
        "откат",
        "миграц",
    )
    for task in tasks or []:
        blob = f"{task.get('name', '')} {task.get('description', '')} {task.get('role', '')}".lower()
        if any(marker in blob for marker in mutate_markers):
            return True
        role = str(task.get("role") or "").lower()
        if role in {"deploy_operator", "incident_commander"}:
            return True
    return False


def ensure_verification_task(
    tasks: list[dict[str, Any]],
    *,
    max_tasks: int = 15,
) -> list[dict[str, Any]]:
    """Append a post_change_verifier task when mutations exist and none is present."""
    prepared = [dict(t) for t in (tasks or [])]
    if not prepared:
        return prepared
    if not plan_mentions_mutation(prepared):
        return prepared

    has_verifier = any(
        str(t.get("role") or "").lower() == "post_change_verifier"
        or "verif" in str(t.get("name") or "").lower()
        or "провер" in str(t.get("name") or "").lower()
        or "smoke" in str(t.get("description") or "").lower()
        for t in prepared
    )
    if has_verifier:
        return prepared
    if len(prepared) >= max_tasks:
        # Force last task toward verification rather than dropping work silently.
        last = dict(prepared[-1])
        last["role"] = "post_change_verifier"
        last["name"] = (str(last.get("name") or "Проверка")[:80] + " + verify")[:200]
        desc = str(last.get("description") or "")
        last["description"] = (
            desc + "\n\nОбязательно: post-change verification — status/health/smoke и отсутствие новых ошибок."
        ).strip()[:500]
        prepared[-1] = last
        return prepared

    prepared.append(
        {
            "name": "Post-change verification",
            "description": (
                "Проверь последствия изменений: service status, health/smoke checks, "
                "свежие ошибки в логах. Не считай цель достигнутой без фактических проверок."
            ),
            "role": "post_change_verifier",
        }
    )
    return prepared
