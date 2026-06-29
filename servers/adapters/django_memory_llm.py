from __future__ import annotations

import json
from typing import Any

from asgiref.sync import async_to_sync

from app.agent_kernel.memory.compaction import compact_text
from app.agent_kernel.memory.snapshot_utils import content_delta, render_snapshot_lines
from app.agent_kernel.memory.types import OperationalPattern, SnapshotCandidate


def should_distill_with_llm(
    candidates: list[SnapshotCandidate],
    existing_snapshots: list[Any],
) -> bool:
    if not existing_snapshots:
        return True
    snapshot_map = {s.memory_key: s for s in existing_snapshots}
    total_delta = 0.0
    compared = 0
    for candidate in candidates:
        existing = snapshot_map.get(candidate.memory_key)
        if existing is None:
            total_delta += 1.0
            compared += 1
            continue
        delta = content_delta(
            str(getattr(existing, "content", "") or ""),
            candidate.content,
        )
        total_delta += delta
        compared += 1
    if compared == 0:
        return False
    avg_delta = total_delta / compared
    return avg_delta > 0.15


def build_memory_warmup_prompt(server_id: int, *, last_n: int = 3) -> str:
    from servers.models import AgentRun

    recent_runs = list(
        AgentRun.objects.filter(server_id=server_id)
        .select_related("agent")
        .order_by("-started_at")[:max(1, min(int(last_n), 6))]
    )
    if not recent_runs:
        return ""
    lines = []
    for run in recent_runs:
        label = getattr(run.agent, "name", "Agent") if run.agent_id else "Agent"
        snippet_src = run.final_report or run.ai_analysis or ""
        snippet = compact_text(
            " ".join(line for line in snippet_src.splitlines() if line.strip()),
            limit=160,
        )
        ts = run.started_at.strftime("%Y-%m-%d %H:%M") if run.started_at else "?"
        lines.append(f"- [{run.status}] {label} @ {ts}: {snippet}")
    return "\n".join(lines)


def distill_with_llm(
    *,
    server,
    candidates: list[SnapshotCandidate],
    model_alias: str,
) -> dict[str, str]:
    from app.core.llm import LLMProvider

    sections = {candidate.memory_key: candidate.content for candidate in candidates}
    prompt = (
        "Ты перерабатываешь память DevOps-агента о сервере.\n"
        "Нельзя добавлять секреты, токены, пароли, приватные ключи или сырые логи.\n"
        "Приоритизируй повторяющиеся подтвержденные workflow, успешные команды людей и агентов, и короткие runbook-выжимки.\n"
        "Не делай поведенческих выводов по одному-двум эпизодам и не используй формулировки вроде "
        "'предпочитает', 'сразу', 'регулярно', 'игнорирует' без явного многосессионного доказательства.\n"
        "Не превращай destructive/mutating команды вроде `docker rm -f`, `delete`, `stop`, `disable` в рекомендуемый runbook, "
        "если нет явной verify/recreate последовательности.\n"
        "Никогда не утверждай, что контейнер автоматически пересоздаётся после `docker rm`, если в данных нет прямого evidence "
        "про orchestrator, compose-up или явный recreate.\n"
        "Для рисков не используй слова chronic/permanent/always без подтверждения во времени.\n"
        "Раздел human_habits заполняй только если read-only или verification workflow повторялся минимум в 3 отдельных сессиях; "
        "не относись к setup-командам вроде mkdir/cp/chmod и к разовым prepare-steps как к привычкам.\n"
        "Верни JSON-объект только с ключами profile, access, risks, runbook, recent_changes, human_habits.\n"
        "Значение каждого ключа — короткий Markdown bullet list, максимум 6 bullet lines.\n\n"
        f"Сервер: {server.name} ({server.host})\n"
        f"Исходные разделы:\n{json.dumps(sections, ensure_ascii=False)}"
    )
    provider = LLMProvider()
    try:
        chunks: list[str] = []

        async def _collect():
            async for chunk in provider.stream_chat(prompt, purpose="opssummary", specific_model=model_alias):
                chunks.append(chunk)

        async_to_sync(_collect)()
        raw = "".join(chunks).strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        parsed = json.loads(raw[start : end + 1])
        if not isinstance(parsed, dict):
            return {}
        cleaned: dict[str, str] = {}
        for key, value in parsed.items():
            if key in sections:
                cleaned[key] = render_snapshot_lines(value, fallback=sections[key])
        return cleaned
    except Exception:
        return {}


def llm_enhance_patterns(
    *,
    server,
    patterns: list[OperationalPattern],
    model_alias: str,
) -> dict[str, dict[str, Any]]:
    from app.core.llm import LLMProvider

    candidates = [
        {
            "normalized_command": pattern.normalized_command,
            "pattern_kind": pattern.pattern_kind,
            "intent": pattern.intent,
            "intent_label": pattern.intent_label,
            "display_command": pattern.display_command,
            "commands": list(pattern.commands),
            "occurrences": pattern.occurrences,
            "success_rate": round(pattern.success_rate, 3) if pattern.success_rate is not None else None,
            "verification_rate": round(pattern.verification_rate, 3),
            "has_verification_step": bool(pattern.has_verification_step),
            "common_cwds": list(pattern.common_cwds),
            "sample_outputs": list(pattern.sample_outputs),
        }
        for pattern in patterns
        if (
            pattern.success_rate is not None
            and (
                (pattern.pattern_kind == "sequence" and pattern.occurrences >= 2)
                or (pattern.pattern_kind == "command" and pattern.occurrences >= 3 and pattern.success_rate >= 0.8)
            )
        )
    ][:6]
    if not candidates:
        return {}

    prompt = (
        "Ты усиливаешь черновики operational playbooks для DevOps-памяти сервера.\n"
        "Не добавляй секреты, приватные ключи, токены, сырые логи и вымышленные шаги.\n"
        "Для каждого workflow верни только безопасные короткие поля when_to_use, automation_hint, "
        "skill_summary, verification, success_signals, playbook_summary, prerequisites, rollback_hint, "
        "risk_level, runtime_attachment.\n"
        "runtime_attachment должен быть коротким советом, как агенту лучше применить этот recipe в runtime.\n"
        "Ответь JSON-массивом объектов с ключами normalized_command, when_to_use, automation_hint, "
        "skill_summary, verification, success_signals, playbook_summary, prerequisites, rollback_hint, "
        "risk_level, runtime_attachment.\n\n"
        f"Сервер: {server.name} ({server.host})\n"
        f"Workflow candidates:\n{json.dumps(candidates, ensure_ascii=False)}"
    )
    provider = LLMProvider()
    try:
        chunks: list[str] = []

        async def _collect():
            async for chunk in provider.stream_chat(prompt, purpose="opssummary", specific_model=model_alias):
                chunks.append(chunk)

        async_to_sync(_collect)()
        raw = "".join(chunks).strip()
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return {}
        parsed = json.loads(raw[start : end + 1])
        if not isinstance(parsed, list):
            return {}
        cleaned: dict[str, dict[str, Any]] = {}
        for item in parsed:
            if not isinstance(item, dict):
                continue
            normalized_command = str(item.get("normalized_command") or "").strip()
            if not normalized_command:
                continue
            signals = item.get("success_signals")
            cleaned[normalized_command] = {
                "when_to_use": compact_text(str(item.get("when_to_use") or ""), limit=180),
                "automation_hint": compact_text(str(item.get("automation_hint") or ""), limit=180),
                "skill_summary": compact_text(str(item.get("skill_summary") or ""), limit=180),
                "verification": compact_text(str(item.get("verification") or ""), limit=180),
                "playbook_summary": compact_text(str(item.get("playbook_summary") or ""), limit=180),
                "prerequisites": compact_text(str(item.get("prerequisites") or ""), limit=180),
                "rollback_hint": compact_text(str(item.get("rollback_hint") or ""), limit=180),
                "risk_level": compact_text(str(item.get("risk_level") or ""), limit=80),
                "runtime_attachment": compact_text(str(item.get("runtime_attachment") or ""), limit=180),
                "success_signals": [
                    compact_text(str(signal), limit=140)
                    for signal in (signals if isinstance(signals, list) else [])
                    if str(signal or "").strip()
                ][:3],
            }
        return cleaned
    except Exception:
        return {}
