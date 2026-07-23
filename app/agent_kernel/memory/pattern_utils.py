from __future__ import annotations

import re
import uuid
from typing import Any

from app.agent_kernel.memory.compaction import compact_text
from app.agent_kernel.memory.types import OperationalPattern


def is_verification_command(command: str) -> bool:
    blob = str(command or "").lower()
    return any(
        term in blob
        for term in (
            "systemctl is-active",
            "systemctl status",
            "journalctl",
            "curl ",
            "wget ",
            "nginx -t",
            "haproxy -c",
            "docker ps",
            "docker stats",
            "kubectl rollout status",
            "kubectl get pods",
            "helm status",
            "ss -l",
            "uptime",
            "free -h",
        )
    )


def normalize_command_pattern(command: str) -> str:
    normalized = " ".join(str(command or "").strip().split())
    normalized = re.sub(r"^sudo\s+", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.lower()[:240]


def classify_command_intent(command: str) -> str:
    blob = str(command or "").lower()
    if any(term in blob for term in ("docker", "compose", "container")):
        return "docker"
    if any(term in blob for term in ("systemctl", "service ", "journalctl")):
        return "service"
    if any(term in blob for term in ("nginx", "apache", "haproxy")):
        return "web"
    if any(term in blob for term in ("ps ", "top", "htop", "uptime", "free ", "df ", "iostat", "vmstat")):
        return "diagnostics"
    if any(term in blob for term in ("kubectl", "helm", "k9s")):
        return "kubernetes"
    if any(term in blob for term in ("grep", "find", "cat ", "tail ", "less ", "awk ", "sed ")):
        return "inspection"
    return "ops"


def classify_sequence_intent(commands: list[str] | tuple[str, ...]) -> str:
    intents = [classify_command_intent(command) for command in commands if str(command or "").strip()]
    if not intents:
        return "ops"
    for preferred in ("docker", "service", "web", "kubernetes", "diagnostics", "inspection"):
        if preferred in intents:
            return preferred
    return intents[0]


def extract_pattern_subject(commands: list[str] | tuple[str, ...]) -> str:
    for command in commands:
        command_text = str(command or "").strip()
        if not command_text:
            continue
        if "nginx" in command_text.lower():
            return "nginx"
        match = re.search(
            r"(?:systemctl\s+(?:restart|reload|is-active|status)\s+)([A-Za-z0-9_.@-]+)",
            command_text,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        match = re.search(r"(?:docker\s+compose\s+)([A-Za-z0-9_.@-]+)", command_text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def describe_pattern_intent(
    commands: list[str] | tuple[str, ...],
    *,
    intent: str,
    sample_outputs: tuple[str, ...] = (),
) -> str:
    joined = " ".join(str(command or "").lower() for command in commands)
    outputs = " ".join(str(item or "").lower() for item in sample_outputs)
    subject = extract_pattern_subject(commands)
    if "nginx -t" in joined and "reload nginx" in joined:
        return "safe nginx reload after config check"
    if "systemctl restart" in joined and "systemctl is-active" in joined:
        return f"{subject or 'service'} restart with health verification"
    if "docker compose pull" in joined and "docker compose up" in joined:
        return "docker compose rollout"
    if "kubectl rollout" in joined and "kubectl get pods" in joined:
        return "kubernetes rollout verification"
    if "journalctl" in joined and "grep" in joined:
        return "log investigation workflow"
    if intent == "diagnostics" and ("load" in outputs or "active" in outputs):
        return "diagnostic verification workflow"
    return intent.replace("_", " ")


def pattern_key_suffix(pattern: OperationalPattern) -> str:
    return uuid.uuid5(uuid.NAMESPACE_DNS, pattern.normalized_command).hex[:16]


def pattern_metadata(pattern: OperationalPattern) -> dict[str, Any]:
    return {
        "pattern_kind": pattern.pattern_kind,
        "normalized_command": pattern.normalized_command,
        "display_command": pattern.display_command,
        "commands": list(pattern.commands),
        "intent": pattern.intent,
        "intent_label": pattern.intent_label,
        "occurrences": pattern.occurrences,
        "successful_runs": pattern.successful_runs,
        "measured_runs": pattern.measured_runs,
        "success_rate": round(pattern.success_rate, 3) if pattern.success_rate is not None else None,
        "requires_manual_review": pattern.measured_runs == 0,
        "verification_rate": round(pattern.verification_rate, 3),
        "has_verification_step": pattern.has_verification_step,
        "actor_kinds": list(pattern.actor_kinds),
        "source_kinds": list(pattern.source_kinds),
        "sample_outputs": list(pattern.sample_outputs),
        "common_cwds": list(pattern.common_cwds),
        "last_seen": pattern.last_seen.isoformat() if pattern.last_seen else None,
    }


def pattern_enhancement_metadata(enhancement: dict[str, Any] | None) -> dict[str, Any]:
    enhancement = enhancement or {}
    metadata: dict[str, Any] = {"llm_enhanced": bool(enhancement)}
    for key in (
        "when_to_use",
        "automation_hint",
        "skill_summary",
        "verification",
        "playbook_summary",
        "prerequisites",
        "rollback_hint",
        "risk_level",
        "runtime_attachment",
    ):
        value = compact_text(str(enhancement.get(key) or ""), limit=220)
        if value:
            metadata[key] = value
    success_signals = [
        compact_text(str(item), limit=140)
        for item in list(enhancement.get("success_signals") or [])[:4]
        if str(item or "").strip()
    ]
    if success_signals:
        metadata["success_signals"] = success_signals
    return metadata


def pattern_success_summary(pattern: OperationalPattern, *, noun: str = "запусков") -> str:
    if pattern.measured_runs:
        rate = float(pattern.success_rate or 0.0)
        return f"{pattern.successful_runs}/{pattern.measured_runs} измеренных {noun} ({rate:.0%})"
    return f"exit code не сохранён; {pattern.occurrences} наблюдений"


def pattern_candidate_lines(pattern: OperationalPattern, *, enhancement: dict[str, Any] | None = None) -> list[str]:
    enhancement = enhancement or {}
    lines = [
        f"Intent: {pattern.intent_label}",
        f"Повторяемость: {pattern.occurrences} запусков",
        f"Успех: {pattern_success_summary(pattern)}",
        f"Источники: {', '.join(pattern.source_kinds)}; акторы: {', '.join(pattern.actor_kinds)}",
    ]
    if pattern.pattern_kind == "sequence":
        lines.insert(0, f"Workflow: {' -> '.join(pattern.commands)}")
    else:
        lines.insert(0, f"Команда: {pattern.display_command}")
    if pattern.common_cwds:
        lines.append("Типовой cwd: " + ", ".join(pattern.common_cwds[:2]))
    if pattern.sample_outputs:
        lines.append("Сигналы успеха/вывода: " + " | ".join(pattern.sample_outputs[:2]))
    if enhancement.get("when_to_use"):
        lines.append("Когда использовать: " + compact_text(str(enhancement["when_to_use"]), limit=180))
    if enhancement.get("playbook_summary"):
        lines.append("Playbook: " + compact_text(str(enhancement["playbook_summary"]), limit=180))
    if enhancement.get("prerequisites"):
        lines.append("Prerequisites: " + compact_text(str(enhancement["prerequisites"]), limit=180))
    if enhancement.get("runtime_attachment"):
        lines.append("Runtime attach: " + compact_text(str(enhancement["runtime_attachment"]), limit=180))
    if enhancement.get("risk_level"):
        lines.append("Риск: " + compact_text(str(enhancement["risk_level"]), limit=80))
    lines.append("Паттерн годится как reusable operational шаблон после ручной проверки.")
    return lines


def looks_mutating_command(command: str) -> bool:
    blob = str(command or "").lower()
    return any(
        term in blob
        for term in (
            "restart",
            "reload",
            "apply",
            "delete",
            "rm ",
            "useradd",
            "systemctl start",
            "systemctl stop",
            "apt ",
            "yum ",
            "dnf ",
            "kubectl apply",
            "docker compose up",
        )
    )


def is_destructive_command(command: str) -> bool:
    blob = str(command or "").lower()
    return any(
        term in blob
        for term in (
            "docker rm ",
            "docker rm -f",
            "docker system prune",
            "docker volume rm",
            "docker network rm",
            "kubectl delete",
            "helm uninstall",
            "rm -rf",
            "rm -f",
            "drop database",
            "systemctl stop",
            "systemctl disable",
        )
    )


def is_setup_command(command: str) -> bool:
    blob = str(command or "").lower().strip()
    return any(
        blob.startswith(prefix)
        for prefix in (
            "mkdir ",
            "install -d",
            "cp ",
            "mv ",
            "chmod ",
            "chown ",
            "tee ",
        )
    )


def pattern_has_mutating_step(pattern: OperationalPattern) -> bool:
    commands = pattern.commands if pattern.pattern_kind == "sequence" else (pattern.display_command,)
    return any(looks_mutating_command(command) for command in commands)


def pattern_has_destructive_step(pattern: OperationalPattern) -> bool:
    commands = pattern.commands if pattern.pattern_kind == "sequence" else (pattern.display_command,)
    return any(is_destructive_command(command) for command in commands)


def pattern_has_setup_step(pattern: OperationalPattern) -> bool:
    commands = pattern.commands if pattern.pattern_kind == "sequence" else (pattern.display_command,)
    return any(is_setup_command(command) for command in commands)


def automation_verification_hint(pattern: OperationalPattern) -> str:
    if pattern.pattern_kind == "sequence" and pattern.has_verification_step:
        return (
            "последний шаг workflow уже выступает как verification; нужно проверить его exit code и сигнал результата."
        )
    if pattern.intent == "service":
        return "проверить `systemctl is-active <service>` и последние строки `journalctl`."
    if pattern.intent == "docker":
        return "проверить состояние контейнеров через `docker ps` и при необходимости `docker stats --no-stream`."
    if pattern.intent == "web":
        return "подтвердить конфиг и health-check веб-сервиса до/после действия."
    if pattern.intent == "kubernetes":
        return "проверить rollout/status нужного workload и последние pod events."
    if pattern.intent == "diagnostics":
        return "сравнить output с предыдущими эпизодами и выделить деградацию/аномалию."
    return "сохранить компактный отчёт и отметить, можно ли повторно автоматизировать этот шаг."


def automation_candidate_lines(pattern: OperationalPattern, *, enhancement: dict[str, Any] | None = None) -> list[str]:
    enhancement = enhancement or {}
    verification_step = automation_verification_hint(pattern)
    safety_mode = "read-only" if not looks_mutating_command(pattern.display_command) else "assisted"
    lines = [
        f"Intent: {pattern.intent_label}",
        f"Режим запуска: {safety_mode}",
    ]
    if pattern.pattern_kind == "sequence":
        for index, command in enumerate(pattern.commands, start=1):
            lines.append(f"Шаг {index}: выполнить `{command}` и сохранить stdout/stderr + exit code.")
        lines.append(f"Шаг {len(pattern.commands) + 1}: {verification_step}")
        lines.append(
            f"Шаг {len(pattern.commands) + 2}: записать краткую выжимку в recent_changes/runbook, если результат полезен."
        )
    else:
        lines.extend(
            [
                f"Базовая команда: {pattern.display_command}",
                "Шаг 1: выполнить команду и сохранить stdout/stderr + exit code.",
                f"Шаг 2: {verification_step}",
                "Шаг 3: записать краткую выжимку в recent_changes/runbook, если результат полезен.",
            ]
        )
    if enhancement.get("playbook_summary"):
        lines.append("Playbook summary: " + compact_text(str(enhancement["playbook_summary"]), limit=180))
    if enhancement.get("prerequisites"):
        lines.append("Prerequisites: " + compact_text(str(enhancement["prerequisites"]), limit=180))
    if pattern.sample_outputs:
        lines.append("Ожидаемые сигналы: " + " | ".join(pattern.sample_outputs[:2]))
    if enhancement.get("automation_hint"):
        lines.append("LLM Hint: " + compact_text(str(enhancement["automation_hint"]), limit=180))
    if enhancement.get("verification"):
        lines.append("Verification focus: " + compact_text(str(enhancement["verification"]), limit=180))
    if enhancement.get("rollback_hint"):
        lines.append("Rollback: " + compact_text(str(enhancement["rollback_hint"]), limit=180))
    if enhancement.get("risk_level"):
        lines.append("Risk: " + compact_text(str(enhancement["risk_level"]), limit=80))
    if enhancement.get("runtime_attachment"):
        lines.append("Runtime attach: " + compact_text(str(enhancement["runtime_attachment"]), limit=180))
    return lines


def skill_draft_lines(pattern: OperationalPattern, *, enhancement: dict[str, Any] | None = None) -> list[str]:
    enhancement = enhancement or {}
    verification_step = automation_verification_hint(pattern)
    lines = [
        f"# Skill Draft: {pattern.intent_label}",
        f"- Trigger: задачи, где нужен {'workflow' if pattern.pattern_kind == 'sequence' else 'шаг'} "
        f"`{pattern.display_command}`.",
        f"- Reuse signal: {pattern.occurrences} повторений, {pattern_success_summary(pattern)}.",
    ]
    if enhancement.get("skill_summary"):
        lines.append(f"- Summary: {compact_text(str(enhancement['skill_summary']), limit=180)}")
    if pattern.pattern_kind == "sequence":
        lines.append(f"- Workflow: {' -> '.join(pattern.commands)}")
    else:
        lines.append(f"- Primary command: {pattern.display_command}")
    lines.append(
        f"- Verification: {compact_text(str(enhancement.get('verification') or verification_step), limit=180)}"
    )
    if enhancement.get("playbook_summary"):
        lines.append(f"- Playbook: {compact_text(str(enhancement['playbook_summary']), limit=180)}")
    if enhancement.get("prerequisites"):
        lines.append(f"- Preconditions: {compact_text(str(enhancement['prerequisites']), limit=180)}")
    if enhancement.get("rollback_hint"):
        lines.append(f"- Rollback: {compact_text(str(enhancement['rollback_hint']), limit=180)}")
    if enhancement.get("runtime_attachment"):
        lines.append(f"- Runtime attach: {compact_text(str(enhancement['runtime_attachment']), limit=180)}")
    hints: list[str] = []
    if pattern.common_cwds:
        hints.append(f"cwd {', '.join(pattern.common_cwds[:2])}")
    if pattern.sample_outputs:
        hints.append(f"signals {' | '.join(pattern.sample_outputs[:2])}")
    if enhancement.get("success_signals"):
        hints.append("llm signals " + " | ".join(str(item) for item in list(enhancement["success_signals"])[:2]))
    if hints:
        lines.append("- Hints: " + "; ".join(hints[:2]))
    else:
        lines.append("- Hints: вернуть короткую operational-выжимку и рекомендации по следующему действию.")
    return lines


def is_automation_candidate(pattern: OperationalPattern) -> bool:
    minimum_occurrences = 2 if pattern.pattern_kind == "sequence" else 3
    success_threshold = 0.75 if pattern.pattern_kind == "sequence" else 0.8
    if pattern.occurrences < minimum_occurrences:
        return False
    if not pattern.measured_runs:
        return False
    if float(pattern.success_rate or 0.0) < success_threshold:
        return False
    if pattern_has_destructive_step(pattern):
        return pattern.pattern_kind == "sequence" and (
            pattern.has_verification_step or pattern.verification_rate >= 0.5
        )
    if pattern_has_mutating_step(pattern) and not (
        pattern.pattern_kind == "sequence" and (pattern.has_verification_step or pattern.verification_rate >= 0.5)
    ):
        return False
    return pattern.intent in {"docker", "service", "web", "diagnostics", "kubernetes", "inspection", "ops"}


def is_skill_draft_candidate(pattern: OperationalPattern) -> bool:
    minimum_occurrences = 2 if pattern.pattern_kind == "sequence" else 3
    success_threshold = 0.85 if pattern.pattern_kind == "sequence" else 0.9
    if pattern.occurrences < minimum_occurrences:
        return False
    if not pattern.measured_runs:
        return False
    if float(pattern.success_rate or 0.0) < success_threshold:
        return False
    if pattern_has_destructive_step(pattern):
        return False
    if pattern_has_mutating_step(pattern) and not (
        pattern.pattern_kind == "sequence" and (pattern.has_verification_step or pattern.verification_rate >= 0.5)
    ):
        return False
    if pattern.pattern_kind == "sequence" and not (pattern.has_verification_step or pattern.verification_rate >= 0.5):
        return False
    return len(pattern.actor_kinds) >= 1 and pattern.intent in {
        "docker",
        "service",
        "web",
        "diagnostics",
        "kubernetes",
        "inspection",
        "ops",
    }


def derive_human_habits(patterns: list[OperationalPattern]) -> list[str]:
    habit_lines: list[str] = []
    for pattern in patterns:
        if "human" not in pattern.actor_kinds:
            continue
        minimum_occurrences = 3 if pattern.pattern_kind == "sequence" else 4
        if pattern.occurrences < minimum_occurrences:
            continue
        if pattern.distinct_sessions < 3:
            continue
        if not pattern.measured_runs:
            continue
        if float(pattern.success_rate or 0.0) < 0.8:
            continue
        if (
            pattern_has_mutating_step(pattern)
            or pattern_has_destructive_step(pattern)
            or pattern_has_setup_step(pattern)
        ):
            continue
        if pattern.pattern_kind == "sequence":
            habit_lines.append(
                f"Повторяется ручной workflow [{pattern.intent}]: "
                f"{' -> '.join(pattern.commands[:3])} "
                f"({pattern.occurrences} запусков в {pattern.distinct_sessions} сессиях)"
            )
        else:
            habit_lines.append(
                f"Повторяется ручной паттерн [{pattern.intent}]: {pattern.display_command} "
                f"({pattern.occurrences} запусков в {pattern.distinct_sessions} сессиях)"
            )
    return habit_lines[:5]


def derive_runbook_patterns(patterns: list[OperationalPattern]) -> list[str]:
    lines: list[str] = []
    for pattern in patterns:
        if pattern.occurrences < 2:
            continue
        if not pattern.measured_runs:
            continue
        if float(pattern.success_rate or 0.0) < 0.6:
            continue
        verified_sequence = pattern.pattern_kind == "sequence" and (
            pattern.has_verification_step or pattern.verification_rate >= 0.5
        )
        if pattern_has_destructive_step(pattern) and not verified_sequence:
            continue
        if pattern_has_mutating_step(pattern) and not verified_sequence:
            continue
        if pattern.pattern_kind == "sequence":
            lines.append(
                f"Проверенный workflow [{pattern.intent}]: {' -> '.join(pattern.commands[:3])} "
                f"({pattern_success_summary(pattern, noun='прогонов')})"
            )
        else:
            lines.append(
                f"Проверенный паттерн [{pattern.intent}]: {pattern.display_command} "
                f"({pattern_success_summary(pattern)})"
            )
    return lines[:6]
