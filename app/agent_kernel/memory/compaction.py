from __future__ import annotations

from typing import Any

NOISE_LINE_MARKERS = (
    "Итерация ",
    "Iteration ",
    "Step ",
    "tool=",
    "ssh_execute",
    "read_console",
    "send_ctrl_c",
    "open_connection",
    "command_done",
    "report ->",
    "final answer",
    "Последние инструменты:",
)
PROFILE_KEYWORDS = (
    "ubuntu",
    "debian",
    "centos",
    "red hat",
    "wsl",
    "docker",
    "kubernetes",
    "k8s",
    "nginx",
    "keycloak",
    "postgres",
    "postgresql",
    "redis",
    "systemd",
    "proxy",
    "vpn",
    "mount",
    "kernel",
    "os ",
    "операцион",
)
RISK_KEYWORDS = (
    "critical",
    "warning",
    "risk",
    "alert",
    "ошиб",
    "паден",
    "деградац",
    "cpu",
    "memory",
    "mem ",
    "disk",
    "swap",
    "oom",
    "unreachable",
    "latency",
    "restart",
    "перегруз",
)
RUNBOOK_KEYWORDS = (
    "рекоменд",
    "нужно",
    "следует",
    "проверь",
    "monitor",
    "watch ",
    "inventory",
    "runbook",
    "verify",
    "validation",
    "deep dive",
    "audit",
    "escalate",
    "установить",
    "использ",
)
CANONICAL_NOTE_TITLES = {
    "Автопрофиль сервера",
    "Авториски сервера",
    "Авто runbook сервера",
}


def compact_text(text: str, *, limit: int = 2000) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value

    lines = [line.rstrip() for line in value.splitlines() if line.strip()]
    if len(lines) <= 6:
        return value[: limit - 1].rstrip() + "…"

    head = lines[:3]
    tail = lines[-3:]
    compacted = "\n".join([*head, "...", *tail])
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 1].rstrip() + "…"


def unique_preserving_order(items: list[str], *, limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = " ".join(str(item or "").split()).strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
        if limit is not None and len(result) >= limit:
            break
    return result


def _normalize_signal_line(line: str) -> str:
    normalized = str(line or "").strip()
    normalized = normalized.lstrip("-*0123456789. ").strip()
    if normalized.startswith("#"):
        normalized = normalized.lstrip("#").strip()
    return " ".join(normalized.split())


def extract_signal_lines(text: str, *, max_items: int = 6, max_line_length: int = 220) -> list[str]:
    candidates: list[tuple[int, int, str]] = []
    for index, raw_line in enumerate((text or "").splitlines()):
        line = _normalize_signal_line(raw_line)
        if not line or len(line) < 12:
            continue
        lower = line.lower()
        if any(marker.lower() in lower for marker in NOISE_LINE_MARKERS):
            continue
        if line.endswith(":") and len(line) <= 40:
            continue
        score = 0
        if any(keyword in lower for keyword in PROFILE_KEYWORDS):
            score += 2
        if any(keyword in lower for keyword in RISK_KEYWORDS):
            score += 3
        if any(keyword in lower for keyword in RUNBOOK_KEYWORDS):
            score += 2
        if raw_line.lstrip().startswith(("-", "*")):
            score += 1
        candidates.append((score, index, compact_text(line, limit=max_line_length)))

    ranked = sorted(candidates, key=lambda item: (-item[0], item[1]))
    return unique_preserving_order([line for _score, _index, line in ranked], limit=max_items)


def filter_signal_lines(lines: list[str], keywords: tuple[str, ...], *, max_items: int = 5) -> list[str]:
    matched = []
    for line in lines:
        lower = line.lower()
        if any(keyword in lower for keyword in keywords):
            matched.append(line)
    return unique_preserving_order(matched, limit=max_items)


def build_canonical_note_content(lines: list[str], *, fallback: str = "") -> str:
    points = unique_preserving_order(lines, limit=8)
    if not points and fallback:
        points = [compact_text(fallback, limit=180)]
    return "\n".join(f"- {item}" for item in points[:8])


def summarize_iterations(iterations: list[dict[str, Any]], *, max_items: int = 6) -> list[str]:
    summary: list[str] = []
    for item in iterations[-max_items:]:
        action = item.get("action") or "final"
        observation = compact_text(str(item.get("observation") or ""), limit=180)
        summary.append(f"Итерация {item.get('iteration', '?')}: {action} -> {observation}")
    return summary


def build_run_summary_payload(
    *,
    run,
    role_slug: str,
    final_status: str,
    final_report: str,
    iterations: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
    verification_summary: str,
) -> dict[str, Any]:
    recent_tools = unique_preserving_order(
        [str(item.get("tool") or item.get("action") or "") for item in tool_calls[-8:] if item],
        limit=6,
    )
    verified = "закрыты" in (verification_summary or "").lower()
    compact_report = compact_text(final_report, limit=2200)
    signal_lines = extract_signal_lines(compact_report, max_items=6)
    if not signal_lines:
        signal_lines = summarize_iterations(iterations, max_items=4)

    profile_lines = filter_signal_lines(signal_lines, PROFILE_KEYWORDS, max_items=4)
    risk_lines = filter_signal_lines(signal_lines, RISK_KEYWORDS, max_items=4)
    runbook_lines = filter_signal_lines(signal_lines, RUNBOOK_KEYWORDS, max_items=4)

    if verified and verification_summary:
        runbook_lines.append(compact_text(verification_summary, limit=160))

    if not runbook_lines and recent_tools:
        runbook_lines.append("Полезные инструменты: " + ", ".join(recent_tools[:4]))

    findings_text = "\n".join(f"- {line}" for line in signal_lines[:4]) or "- Существенных сигналов не зафиксировано"
    status_line = f"Статус: {final_status}; роль: {role_slug}"
    verification_line = compact_text(verification_summary, limit=180) if verification_summary else ""
    digest_parts = [status_line, "Выжимка:\n" + findings_text]
    if verification_line:
        digest_parts.append("Контроль изменений: " + verification_line)
    if runbook_lines:
        digest_parts.append(
            "Следующие действия:\n" + "\n".join(f"- {line}" for line in unique_preserving_order(runbook_lines, limit=3))
        )
    digest_text = compact_text("\n\n".join(digest_parts), limit=1100)

    canonical_notes: list[dict[str, Any]] = []
    if profile_lines:
        canonical_notes.append(
            {
                "title": "Автопрофиль сервера",
                "category": "system",
                "content": build_canonical_note_content(profile_lines, fallback="Профиль сервера уточняется новыми наблюдениями."),
                "confidence": 0.84 if verified else 0.74,
                "source": "ai_auto",
                "verified": verified,
            }
        )
    if risk_lines or final_status in {"failed", "stopped"}:
        risk_content = build_canonical_note_content(
            risk_lines,
            fallback=f"Последний run завершился статусом {final_status} и требует внимания оператора.",
        )
        canonical_notes.append(
            {
                "title": "Авториски сервера",
                "category": "issues",
                "content": risk_content,
                "confidence": 0.78 if verified else 0.7,
                "source": "ai_auto",
                "verified": verified,
            }
        )
    if runbook_lines:
        canonical_notes.append(
            {
                "title": "Авто runbook сервера",
                "category": "solutions",
                "content": build_canonical_note_content(runbook_lines),
                "confidence": 0.8 if verified else 0.68,
                "source": "ai_auto",
                "verified": verified,
            }
        )

    # GAP 6: skill_draft_hint — если run успешен + verified + использовал SSH из 3+ шагов
    has_ssh_steps = any(
        str(item.get("tool") or "").lower() in {"ssh_execute", "read_console"}
        for item in tool_calls
    )
    ssh_tool_count = sum(
        1 for item in tool_calls
        if str(item.get("tool") or "").lower() in {"ssh_execute", "read_console"}
    )
    if (
        verified
        and final_status == "completed"
        and has_ssh_steps
        and ssh_tool_count >= 3
        and runbook_lines
    ):
        skill_summary_lines = unique_preserving_order(runbook_lines[:4], limit=4)
        workflow_steps = unique_preserving_order(
            [str(item.get("tool") or "") for item in tool_calls if item.get("tool")],
            limit=6,
        )
        canonical_notes.append(
            {
                "title": f"Skill Draft Hint: {getattr(run.agent, 'name', 'Agent')} run #{run.pk}",
                "category": "solutions",
                "content": build_canonical_note_content(
                    ["Автоматически детектированный skill draft из успешного run."]
                    + skill_summary_lines,
                ),
                "confidence": 0.82,
                "source": "ai_run_summary",
                "is_skill_draft_hint": True,
                "workflow_steps": workflow_steps,
                "verification_summary": compact_text(verification_summary, limit=200),
                "verified": True,
            }
        )

    persist_run_digest = bool(risk_lines or final_status in {"failed", "stopped"})

    return {
        "title": f"Run digest #{run.pk}: {getattr(run.agent, 'name', 'Agent')}",
        "status": final_status,
        "role": role_slug,
        "verification_summary": verification_summary,
        "recent_tools": recent_tools,
        "verified": verified,
        "facts": [],
        "changes": [],
        "incidents": [],
        "canonical_notes": canonical_notes,
        "signal_findings": signal_lines[:4],
        "persist_run_digest": persist_run_digest,
        "summary_text": digest_text,
    }
