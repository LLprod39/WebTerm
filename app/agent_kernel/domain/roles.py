from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RoleSpec:
    slug: str
    title: str
    system_hint: str
    default_permission_mode: str
    focus_areas: tuple[str, ...]
    verification_rules: tuple[str, ...]
    allowed_tool_categories: tuple[str, ...] = ("general", "ssh", "monitoring")
    max_task_iterations: int = 5
    task_keywords: tuple[str, ...] = ()


ROLE_SPECS: dict[str, RoleSpec] = {
    "incident_commander": RoleSpec(
        slug="incident_commander",
        title="Incident Commander",
        system_hint=(
            "Ты ведешь расследование инцидента как SRE. Сначала собирай симптомы, затем подтверждай гипотезы, "
            "фиксируй риски и не объявляй успех без проверки сервиса после изменений."
        ),
        default_permission_mode="SAFE",
        focus_areas=("alerts", "logs", "health", "rollback readiness"),
        verification_rules=("Перед завершением проверь состояние сервиса и отсутствие активных ошибок.",),
        allowed_tool_categories=("general", "ssh", "monitoring", "service", "docker", "nginx", "mcp"),
        max_task_iterations=6,
        task_keywords=("incident", "alert", "outage", "downtime", "recover", "restore", "degradation"),
    ),
    "deploy_operator": RoleSpec(
        slug="deploy_operator",
        title="Deploy Operator",
        system_hint=(
            "Ты выполняешь controlled rollout/rollback. Для любых изменений сначала собирай preflight факты, "
            "потом выполняй изменение и сразу запускай post-change verification."
        ),
        default_permission_mode="AUTO_GUARDED",
        focus_areas=("deploy", "docker", "systemd", "config validation"),
        verification_rules=("Любой рестарт или деплой должен сопровождаться проверкой конфигурации и health/smoke check.",),
        allowed_tool_categories=("general", "ssh", "service", "docker", "nginx", "keycloak", "mcp"),
        max_task_iterations=6,
        task_keywords=("deploy", "rollout", "release", "rollback", "restart", "reload", "docker", "compose", "nginx", "keycloak", "migration"),
    ),
    "infra_scout": RoleSpec(
        slug="infra_scout",
        title="Infrastructure Scout",
        system_hint=(
            "Ты проводишь инвентаризацию инфраструктуры. Предпочитай read-only команды, собирай факты о сервисах, "
            "пакетах, cron, сети и Docker без лишних изменений."
        ),
        default_permission_mode="PLAN",
        focus_areas=("inventory", "packages", "network", "docker", "config"),
        verification_rules=("Если пришлось что-то изменить, явно отметь это как исключение.",),
        allowed_tool_categories=("general", "ssh", "monitoring", "service", "docker"),
        max_task_iterations=4,
        task_keywords=("inventory", "inspect", "package", "network", "disk", "cpu", "memory", "cron", "service list", "topology"),
    ),
    "log_investigator": RoleSpec(
        slug="log_investigator",
        title="Log Investigator",
        system_hint=(
            "Ты анализируешь журналы и ошибки. Сжимай длинные логи, ищи корреляции по времени и формулируй "
            "root cause на основе фактов, а не догадок."
        ),
        default_permission_mode="PLAN",
        focus_areas=("logs", "correlation", "root cause", "recent incidents"),
        verification_rules=("Не предлагай фиксы без указания подтверждающих сигналов.",),
        allowed_tool_categories=("general", "ssh", "monitoring", "service"),
        max_task_iterations=5,
        task_keywords=("log", "journal", "traceback", "exception", "stacktrace", "root cause", "stderr"),
    ),
    "security_patrol": RoleSpec(
        slug="security_patrol",
        title="Security Patrol",
        system_hint=(
            "Ты проводишь security review сервера. Ищи лишние открытые порты, sudo/cron аномалии, опасные "
            "конфигурации, persistence-механизмы и drift политики."
        ),
        default_permission_mode="SAFE",
        focus_areas=("ports", "sudo", "cron", "auth", "filesystem drift"),
        verification_rules=("Все действия должны быть минимально инвазивными и безопасными.",),
        allowed_tool_categories=("general", "ssh", "monitoring", "service"),
        max_task_iterations=5,
        task_keywords=("security", "sudo", "ssh", "auth", "port", "firewall", "permission", "suspicious", "persistence"),
    ),
    "post_change_verifier": RoleSpec(
        slug="post_change_verifier",
        title="Post Change Verifier",
        system_hint=(
            "Ты проверяешь последствия изменений. Основная задача — подтвердить работоспособность после мутации: "
            "service status, health checks, smoke tests, отсутствие новых ошибок."
        ),
        default_permission_mode="PLAN",
        focus_areas=("verification", "service status", "smoke checks", "regressions"),
        verification_rules=("Если проверка не выполнена, результат нельзя считать полностью успешным.",),
        allowed_tool_categories=("general", "ssh", "monitoring", "service", "docker", "nginx"),
        max_task_iterations=4,
        task_keywords=("verify", "verification", "smoke", "health check", "regression", "post-change", "validate"),
    ),
    "watcher_daemon": RoleSpec(
        slug="watcher_daemon",
        title="Watcher Daemon",
        system_hint=(
            "Ты фоновый наблюдатель. Отслеживай drift и инциденты, но не делай опасных действий автоматически; "
            "вместо этого формируй предложения и escalation summary."
        ),
        default_permission_mode="PLAN",
        focus_areas=("alerts", "ssl", "containers", "service drift"),
        verification_rules=("Никаких silent mutations; только предложения или безопасные read-only проверки.",),
        allowed_tool_categories=("general", "monitoring"),
        max_task_iterations=3,
        task_keywords=("watch", "monitor", "drift", "background", "observer", "ssl expiry"),
    ),
    "custom": RoleSpec(
        slug="custom",
        title="Ops Agent",
        system_hint=(
            "Ты DevOps/SRE агент. Работай как оператор инфраструктуры, а не как программист: собирай факты, "
            "следуй policy, думай о рисках и проверяй последствия изменений."
        ),
        default_permission_mode="SAFE",
        focus_areas=("ops", "monitoring", "services", "verification"),
        verification_rules=("Перед завершением зафиксируй, что именно было проверено.",),
        allowed_tool_categories=("general", "ssh", "monitoring", "service", "docker", "nginx", "keycloak", "mcp"),
        max_task_iterations=5,
    ),
}

_EXPLICIT_ROLE_RE = re.compile(r"\[role=([a-z_]+)\]", re.IGNORECASE)


def resolve_role_slug(agent_type: str, goal: str = "") -> str:
    goal_text = (goal or "").lower()
    explicit_match = _EXPLICIT_ROLE_RE.search(goal or "")
    if explicit_match:
        explicit_role = explicit_match.group(1).strip().lower()
        if explicit_role in ROLE_SPECS:
            return explicit_role
    if agent_type in {"security_audit", "security_patrol"}:
        return "security_patrol"
    if agent_type in {"deploy_watcher", "docker_status"}:
        return "deploy_operator"
    if agent_type in {"log_analyzer", "log_investigator"}:
        return "log_investigator"
    if agent_type in {"infra_scout", "performance", "disk_report", "service_health"}:
        return "infra_scout"
    if agent_type == "multi_health":
        return "incident_commander"
    if any(word in goal_text for word in ("deploy", "rollout", "release", "docker compose", "nginx reload")):
        return "deploy_operator"
    if any(word in goal_text for word in ("incident", "outage", "alert", "root cause")):
        return "incident_commander"
    return "custom"


def get_role_spec(agent_type: str, goal: str = "") -> RoleSpec:
    return ROLE_SPECS[resolve_role_slug(agent_type, goal)]


def resolve_task_role_slug(name: str, description: str = "", fallback_role: str = "custom") -> str:
    haystack = f"{name}\n{description}".lower()
    if not haystack.strip():
        return fallback_role if fallback_role in ROLE_SPECS else "custom"

    ordered_roles = (
        "log_investigator",
        "security_patrol",
        "post_change_verifier",
        "deploy_operator",
        "incident_commander",
        "watcher_daemon",
        "infra_scout",
    )
    best_role = fallback_role if fallback_role in ROLE_SPECS else "custom"
    best_score = 0
    for role_slug in ordered_roles:
        role_spec = ROLE_SPECS[role_slug]
        score = sum(1 for keyword in role_spec.task_keywords if keyword in haystack)
        if score > best_score:
            best_role = role_slug
            best_score = score

    return best_role
