from __future__ import annotations

import copy
import re
from typing import Any

from studio.pilot_capability_packs import enrich_mcp_node_data_with_pilot_spec
from studio.templates_data import PIPELINE_TEMPLATES

PILOT_TEMPLATE_SLUGS = {
    "pilot-keycloak-access-change",
    "pilot-kubernetes-rollout",
    "pilot-gitlab-failed-pipeline-mr",
    "pilot-database-diagnostics-maintenance",
    "pilot-observability-incident-response",
    "pilot-linux-package-maintenance",
    "pilot-linux-disk-cleanup",
    "pilot-backup-restore-check",
    "pilot-service-config-validate-restart",
}

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
_EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![A-Za-z0-9._%+-])")
_URL_RE = re.compile(r"https?://[^\s,;\"')\]}]+", re.IGNORECASE)
_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:@~/-]{0,127}$")
_STOP_ENTITY_VALUES = {
    "and",
    "or",
    "the",
    "a",
    "an",
    "to",
    "for",
    "in",
    "on",
    "with",
    "has",
    "have",
    "then",
    "after",
    "before",
    "only",
    "role",
    "roles",
    "group",
    "groups",
    "user",
    "users",
    "service",
    "services",
    "namespace",
    "deployment",
    "pipeline",
    "project",
    "branch",
    "commit",
    "approval",
    "approve",
    "healthcheck",
    "url",
    "realm",
    "config",
    "configuration",
    "package",
    "packages",
    "pkg",
    "pkgs",
    "logs",
    "log",
    "recent",
    "и",
    "или",
    "в",
    "на",
    "для",
    "с",
    "со",
    "по",
    "к",
    "у",
    "а",
    "то",
    "затем",
    "после",
    "перед",
    "роль",
    "роли",
    "группа",
    "группу",
    "пользователя",
    "пользователь",
    "сервис",
    "службу",
    "аппрув",
    "есть",
    "конфиг",
    "конфигурацию",
    "пакет",
    "пакеты",
    "пакетов",
    "логи",
    "лог",
}
_RUNTIME_PLACEHOLDER_NAMES = {"approve_url", "reject_url"}
_MONITORING_RUNTIME_PLACEHOLDER_NAMES = {
    "alert_id",
    "alert_source",
    "alert_severity",
    "alert_type",
    "service_name",
}
_OPERATIONAL_PLACEHOLDER_FIELDS = {
    "arguments",
    "packages",
    "path",
    "service",
    "url",
    "preflight_commands",
    "verification_commands",
}
_KNOWN_SERVICE_NAMES = (
    "nginx",
    "apache2",
    "httpd",
    "postgresql",
    "postgres",
    "mysql",
    "mariadb",
    "redis",
    "docker",
    "containerd",
    "ssh",
    "sshd",
    "rabbitmq-server",
    "rabbitmq",
    "elasticsearch",
    "kibana",
    "prometheus",
    "grafana-server",
    "grafana",
)

PILOT_TEMPLATE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "pilot-keycloak-access-change": (
        "keycloak",
        "keycloack",
        "kc",
        "iam",
        "identity",
        "access",
        "realm",
        "role",
        "roles",
        "group",
        "groups",
        "user",
        "users",
        "client",
        "киклок",
        "кейклок",
        "доступ",
        "роль",
        "роли",
        "групп",
        "пользовател",
    ),
    "pilot-kubernetes-rollout": (
        "kubernetes",
        "k8s",
        "kubectl",
        "cluster",
        "namespace",
        "deployment",
        "rollout",
        "pod",
        "pods",
        "workload",
        "helm",
        "crashloop",
        "crashloopbackoff",
        "кубер",
        "кубернет",
        "кластер",
        "неймспейс",
        "деплоймент",
        "поды",
        "роллаут",
    ),
    "pilot-gitlab-failed-pipeline-mr": (
        "gitlab",
        "ci",
        "ci/cd",
        "failed pipeline",
        "pipeline failed",
        "merge request",
        "mr",
        "job failed",
        "build failed",
        "пайплайн упал",
        "упал pipeline",
        "сборк",
        "джоб",
        "мердж",
    ),
    "pilot-database-diagnostics-maintenance": (
        "database",
        "db",
        "postgres",
        "postgresql",
        "mysql",
        "mariadb",
        "mongodb",
        "sql",
        "slow query",
        "slow queries",
        "locks",
        "replication",
        "schema",
        "база",
        "бд",
        "постгрес",
        "запрос",
        "лок",
        "репликац",
    ),
    "pilot-observability-incident-response": (
        "observability",
        "grafana",
        "prometheus",
        "loki",
        "pagerduty",
        "jira",
        "sentry",
        "oncall",
        "outage",
        "slo",
        "error rate",
        "latency",
        "графана",
        "прометей",
        "дежурн",
        "авари",
    ),
    "pilot-linux-package-maintenance": (
        "package",
        "packages",
        "pkg",
        "pkgs",
        "apt",
        "apt-get",
        "yum",
        "dnf",
        "security update",
        "security patch",
        "update packages",
        "upgrade packages",
        "patch packages",
        "package update",
        "обнови пакеты",
        "обновить пакеты",
        "обновление пакетов",
        "пакеты обнов",
        "патч",
    ),
    "pilot-linux-disk-cleanup": (
        "disk cleanup",
        "disk full",
        "disk usage",
        "free space",
        "cleanup disk",
        "clean disk",
        "journal vacuum",
        "journalctl vacuum",
        "tmp cleanup",
        "tmp files",
        "var tmp",
        "du",
        "df",
        "место на диске",
        "диск заполнен",
        "диск забит",
        "очисти диск",
        "очистка диска",
        "свободное место",
        "journal vacuum",
        "временные файлы",
    ),
    "pilot-backup-restore-check": (
        "backup",
        "backups",
        "restore check",
        "restore test",
        "backup check",
        "backup verification",
        "verify backup",
        "latest backup",
        "archive integrity",
        "dump",
        "snapshot backup",
        "бэкап",
        "бекап",
        "резервн",
        "backup свеж",
        "проверь backup",
        "проверить backup",
        "восстановлен",
    ),
    "pilot-service-config-validate-restart": (
        "linux",
        "service",
        "systemd",
        "nginx",
        "apache",
        "restart",
        "reload",
        "config",
        "configuration",
        "healthcheck",
        "health check",
        "journalctl",
        "сервис",
        "служб",
        "рестарт",
        "перезапуск",
        "перезапусти",
        "конфиг",
        "логи",
        "лог",
    ),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalise_query(value: str) -> str:
    return re.sub(r"\s+", " ", _text(value).lower())


def _contains_term(haystack: str, term: str) -> bool:
    needle = _normalise_query(term)
    if not needle:
        return False
    if len(needle) <= 3 and re.fullmatch(r"[a-z0-9]+", needle):
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None
    return needle in haystack


def _binding_query(assistant_context: dict[str, Any]) -> str:
    return " ".join(
        _text(assistant_context.get(field))
        for field in ("binding_query", "pipeline_name", "user_message")
        if _text(assistant_context.get(field))
    )


def _clean_entity_value(value: str) -> str | None:
    cleaned = _text(value).strip("`'\".:,;()[]{}<>")
    if not cleaned:
        return None
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return None
    if _normalise_query(cleaned) in _STOP_ENTITY_VALUES:
        return None
    return cleaned[:160]


def _extract_keyword_value(query: str, keywords: tuple[str, ...]) -> str | None:
    keyword_pattern = "|".join(f"(?:{keyword})" for keyword in keywords)
    pattern = rf"(?<![\w.-])(?:{keyword_pattern})(?![\w.-])\s*(?:[:=#-]|\bis\b|\bэто\b|\bэто\s+)?\s*([^\s,;]+)"
    match = re.search(pattern, query, flags=re.IGNORECASE)
    if not match:
        return None
    return _clean_entity_value(match.group(1))


def _extract_after_action(query: str, actions: tuple[str, ...]) -> str | None:
    action_pattern = "|".join(f"(?:{action})" for action in actions)
    pattern = rf"(?<![\w.-])(?:{action_pattern})(?![\w.-])\s+([^\s,;]+)"
    match = re.search(pattern, query, flags=re.IGNORECASE)
    if not match:
        return None
    return _clean_entity_value(match.group(1))


def _extract_keycloak_arguments(query: str) -> dict[str, str]:
    bindings: dict[str, str] = {}
    realm = _extract_keyword_value(query, (r"realm", r"реалм\w*"))
    username = None
    email_match = _EMAIL_RE.search(query)
    if email_match:
        username = _clean_entity_value(email_match.group(1))
    if not username:
        username = _extract_keyword_value(
            query,
            (r"username", r"user", r"account", r"login", r"пользовател\w*", r"юзер\w*", r"аккаунт\w*", r"логин\w*"),
        )
    role = _extract_keyword_value(query, (r"role", r"роль", r"роли", r"рол\w*"))
    group = _extract_keyword_value(query, (r"group", r"группа", r"группу", r"группе", r"групп\w*"))

    normalized = _normalise_query(query)
    operation = None
    if re.search(r"\b(remove|revoke|delete|unassign|detach)\b|удал|снят|сними|отозва|забра", normalized):
        operation = "remove"
    elif re.search(r"\b(add|grant|assign|attach|give|create)\b|добав|назнач|выда|добавь|созда", normalized):
        operation = "add"

    for key, value in (
        ("realm", realm),
        ("username", username),
        ("role", role),
        ("group", group),
        ("operation", operation),
    ):
        if value:
            bindings[key] = value
    return bindings


def _extract_kubernetes_arguments(query: str) -> dict[str, str]:
    bindings: dict[str, str] = {}
    cluster = _extract_keyword_value(query, (r"cluster", r"кластер\w*"))
    namespace = _extract_keyword_value(query, (r"namespace", r"неймспейс\w*", r"пространств\w*"))
    if not namespace:
        namespace_match = re.search(r"(?<![\w.-])-n\s+([^\s,;]+)", query, flags=re.IGNORECASE)
        if namespace_match:
            namespace = _clean_entity_value(namespace_match.group(1))

    workload_kind = None
    workload_name = None
    for kind, keywords in (
        ("deployment", (r"deployment", r"deploy", r"деплоймент\w*")),
        ("statefulset", (r"statefulset", r"sts")),
        ("daemonset", (r"daemonset", r"ds")),
    ):
        value = _extract_keyword_value(query, keywords)
        if value:
            workload_kind = kind
            workload_name = value
            break
    if not workload_name:
        workload_name = _extract_keyword_value(query, (r"workload", r"ворклоад\w*"))

    normalized = _normalise_query(query)
    action = None
    if re.search(r"\b(rollout\s+restart|restart)\b|перезапуск|перезапусти|рестарт", normalized):
        action = "restart"
    elif re.search(r"\brollback\b|откат", normalized):
        action = "rollback"
    elif re.search(r"\bscale\b|масштаб", normalized):
        action = "scale"

    for key, value in (
        ("cluster", cluster),
        ("namespace", namespace),
        ("kind", workload_kind),
        ("workload_name", workload_name),
        ("deployment", workload_name if workload_kind == "deployment" else None),
        ("action", action),
    ):
        if value:
            bindings[key] = value
    return bindings


def _extract_gitlab_arguments(query: str) -> dict[str, str]:
    bindings: dict[str, str] = {}
    patterns = {
        "project_id": r"(?:project|project[_\s-]?id|проект\w*)\s*(?:[:=#]|\bid\b)?\s*(\d+)",
        "pipeline_id": r"(?:pipeline|pipeline[_\s-]?id|пайплайн\w*)\s*(?:[:=#]|\bid\b)?\s*(\d+)",
        "branch": r"(?:branch|ref|ветк\w*)\s*[:=]?\s*([A-Za-z0-9._/-]+)",
        "commit_sha": r"(?:commit|commit[_\s-]?sha|sha|коммит\w*)\s*[:=]?\s*([a-fA-F0-9]{7,40})",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            value = _clean_entity_value(match.group(1))
            if value:
                bindings[key] = value
    return bindings


def _extract_database_arguments(query: str) -> dict[str, str]:
    bindings: dict[str, str] = {}
    database = _extract_keyword_value(query, (r"database", r"db", r"база", r"бд"))
    schema = _extract_keyword_value(query, (r"schema", r"схема", r"схему", r"схем\w*"))
    if database:
        bindings["database"] = database
    if schema:
        bindings["schema"] = schema
    return bindings


def _extract_incident_arguments(query: str) -> dict[str, str]:
    bindings: dict[str, str] = {}
    explicit_service = _extract_keyword_value(query, (r"service", r"сервис\w*", r"служб\w*"))
    if explicit_service:
        bindings["service_name"] = explicit_service
    else:
        bindings.update(_extract_service_arguments(query))

    alert_id = _extract_keyword_value(
        query,
        (r"alert[_\s-]?id", r"alert", r"incident[_\s-]?id", r"incident", r"fingerprint", r"алерт\w*", r"инцидент\w*"),
    )
    if alert_id:
        bindings["alert_id"] = alert_id

    normalized = _normalise_query(query)
    source_terms = (
        ("grafana", "Grafana"),
        ("prometheus", "Prometheus"),
        ("loki", "Loki"),
        ("pagerduty", "PagerDuty"),
        ("jira", "Jira"),
        ("sentry", "Sentry"),
    )
    for term, source in source_terms:
        if _contains_term(normalized, term):
            bindings["alert_source"] = source
            break

    if re.search(r"\b(critical|crit|page|sev0|sev1)\b|критич|авари", normalized):
        bindings["alert_severity"] = "critical"
    elif re.search(r"\b(warning|warn|high|sev2|sev3)\b|предупреж|высок", normalized):
        bindings["alert_severity"] = "warning"
    elif re.search(r"\b(info|low|notice)\b|инфо|низк", normalized):
        bindings["alert_severity"] = "info"
    return bindings


def _extract_package_arguments(query: str) -> dict[str, str]:
    bindings: dict[str, str] = {}
    segments: list[str] = []
    patterns = (
        r"(?:packages?|pkgs?|pkg|пакет\w*)\s*(?:[:=]|для|to|with)?\s*([^.;\n]+)",
        r"(?:apt(?:-get)?|yum|dnf)\s+(?:update|upgrade|install|remove)?\s*([^.;\n]+)",
        r"(?:update|upgrade|patch|обнови\w*|обновить|пропатч\w*)\s+(?:packages?|pkgs?|пакет\w*)?\s*([^.;\n]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            segments.append(match.group(1))

    packages: list[str] = []
    stop_words = {
        "after",
        "before",
        "then",
        "with",
        "approval",
        "approve",
        "server",
        "host",
        "only",
        "после",
        "перед",
        "затем",
        "аппрув",
        "подтверждения",
        "сервер",
        "хост",
        "только",
    }
    for segment in segments:
        segment = re.split(
            r"\b(?:after|before|then|with|approval|approve|server|host|on|после|перед|затем|с|аппрув|подтверждения|сервер|хост|на)\b",
            segment,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        for token in re.split(r"[\s,]+", segment):
            package = _clean_entity_value(token)
            if not package:
                continue
            normalized = _normalise_query(package)
            if normalized in stop_words or normalized in _STOP_ENTITY_VALUES:
                continue
            if not _PACKAGE_NAME_RE.fullmatch(package):
                continue
            if package not in packages:
                packages.append(package)
    if packages:
        bindings["packages"] = ",".join(packages[:12])
    return bindings


def _extract_backup_arguments(query: str) -> dict[str, str]:
    bindings: dict[str, str] = {}
    path = _extract_keyword_value(query, (r"path", r"dir", r"directory", r"backup[_\s-]?path", r"каталог\w*", r"путь"))
    if not path:
        path_match = re.search(r"(?<![\w.-])(/(?:[A-Za-z0-9._@~+-]+/)*[A-Za-z0-9._@~+-]*backup[A-Za-z0-9._@~+/-]*)", query, flags=re.IGNORECASE)
        if not path_match:
            path_match = re.search(r"(?<![\w.-])(/(?:var/backups|backups|srv/backups|opt/backups)(?:/[A-Za-z0-9._@~+-]+)*)", query, flags=re.IGNORECASE)
        if path_match:
            path = _clean_entity_value(path_match.group(1))
    max_age = None
    age_match = re.search(r"(?:max[_\s-]?age|age|fresh|свежее|старше)\s*(?:[:=]|\bthan\b)?\s*(\d+)\s*(h|hour|hours|час|часов|d|day|days|день|дней)?", query, flags=re.IGNORECASE)
    if age_match:
        amount = int(age_match.group(1))
        unit = (age_match.group(2) or "h").lower()
        max_age = str(amount * 24 if unit.startswith(("d", "day", "д")) else amount)
    if path:
        bindings["backup_path"] = path
    if max_age:
        bindings["max_age_hours"] = max_age
    return bindings


def _extract_service_arguments(query: str) -> dict[str, str]:
    bindings: dict[str, str] = {}
    service_name = None
    normalized = _normalise_query(query)
    for candidate in _KNOWN_SERVICE_NAMES:
        if _contains_term(normalized, candidate):
            service_name = candidate
            break
    if not service_name:
        service_name = _extract_keyword_value(query, (r"service", r"сервис\w*", r"служб\w*"))
    if not service_name:
        service_name = _extract_after_action(
            query,
            (
                r"restart",
                r"reload",
                r"validate",
                r"check",
                r"перезапусти\w*",
                r"рестарт\w*",
                r"проверь\w*",
                r"проверить",
            ),
        )
    url_match = _URL_RE.search(query)
    if service_name:
        bindings["service_name"] = service_name
    if url_match:
        bindings["healthcheck_url"] = url_match.group(0)
    return bindings


def _extract_template_argument_bindings(template_slug: str, assistant_context: dict[str, Any]) -> dict[str, str]:
    query = _binding_query(assistant_context)
    if not query:
        return {}
    if template_slug == "pilot-keycloak-access-change":
        return _extract_keycloak_arguments(query)
    if template_slug == "pilot-kubernetes-rollout":
        return _extract_kubernetes_arguments(query)
    if template_slug == "pilot-gitlab-failed-pipeline-mr":
        return _extract_gitlab_arguments(query)
    if template_slug == "pilot-database-diagnostics-maintenance":
        return _extract_database_arguments(query)
    if template_slug == "pilot-observability-incident-response":
        return _extract_incident_arguments(query)
    if template_slug == "pilot-linux-package-maintenance":
        return _extract_package_arguments(query)
    if template_slug == "pilot-backup-restore-check":
        return _extract_backup_arguments(query)
    if template_slug == "pilot-service-config-validate-restart":
        return _extract_service_arguments(query)
    return {}


def _replace_bound_placeholders(value: Any, bindings: dict[str, str]) -> Any:
    if isinstance(value, str):
        return _PLACEHOLDER_RE.sub(lambda match: bindings.get(match.group(1), match.group(0)), value)
    if isinstance(value, list):
        return [_replace_bound_placeholders(item, bindings) for item in value]
    if isinstance(value, dict):
        return {key: _replace_bound_placeholders(item, bindings) for key, item in value.items()}
    return value


def _find_placeholders(value: Any) -> set[str]:
    if isinstance(value, str):
        return set(_PLACEHOLDER_RE.findall(value))
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            result.update(_find_placeholders(item))
        return result
    if isinstance(value, dict):
        result: set[str] = set()
        for item in value.values():
            result.update(_find_placeholders(item))
        return result
    return set()


def _trigger_runtime_placeholders(template: dict[str, Any]) -> set[str]:
    placeholders: set[str] = set()
    for node in template.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_type = node.get("type")
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        if node_type == "trigger/webhook":
            payload_map = data.get("webhook_payload_map")
            if isinstance(payload_map, dict):
                placeholders.update(_text(key) for key in payload_map if _text(key))
        elif node_type == "trigger/monitoring":
            placeholders.update(_MONITORING_RUNTIME_PLACEHOLDER_NAMES)
    return placeholders


def _is_runtime_placeholder(name: str, webhook_placeholders: set[str]) -> bool:
    return (
        name in _RUNTIME_PLACEHOLDER_NAMES
        or name in webhook_placeholders
        or name.endswith("_output")
        or name.endswith("_error")
    )


def _unresolved_operational_placeholders(
    template: dict[str, Any],
    *,
    bindings: dict[str, str],
) -> tuple[list[str], list[str]]:
    trigger_placeholders = _trigger_runtime_placeholders(template)
    missing: set[str] = set()
    runtime: set[str] = set()
    for node in template.get("nodes", []):
        if not isinstance(node, dict) or not isinstance(node.get("data"), dict):
            continue
        data = node["data"]
        for field in _OPERATIONAL_PLACEHOLDER_FIELDS:
            if field not in data:
                continue
            for placeholder in _find_placeholders(data[field]):
                if placeholder in bindings:
                    continue
                if _is_runtime_placeholder(placeholder, trigger_placeholders):
                    runtime.add(placeholder)
                else:
                    missing.add(placeholder)
    return sorted(missing), sorted(runtime)


def _pilot_templates() -> list[dict[str, Any]]:
    return [template for template in PIPELINE_TEMPLATES if template.get("slug") in PILOT_TEMPLATE_SLUGS]


def _template_label(node: dict[str, Any]) -> str:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    return _text(data.get("label") or node.get("label") or node.get("id"))


def _compact_template_node(node: dict[str, Any]) -> dict[str, Any]:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    payload: dict[str, Any] = {
        "id": _text(node.get("id")),
        "type": _text(node.get("type")),
        "label": _template_label(node),
    }
    for field in (
        "mcp_server_name",
        "tool_name",
        "permission_mode",
        "capability_pack",
        "operation_kind",
        "risk_level",
        "action",
        "packages",
        "service",
        "sections",
        "expected_status",
        "manual_link_only",
    ):
        value = data.get(field)
        if value not in (None, "", []):
            payload[field] = value
    return payload


def _compact_template_edge(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": _text(edge.get("source")),
        "target": _text(edge.get("target")),
        "source_handle": _text(edge.get("source_handle") or edge.get("sourceHandle") or "out"),
        "label": _text(edge.get("label")) or None,
    }


def _score_template(template: dict[str, Any], query: str) -> tuple[int, list[str]]:
    slug = _text(template.get("slug"))
    matched: list[str] = []
    score = 0
    for term in PILOT_TEMPLATE_KEYWORDS.get(slug, ()):
        if not _contains_term(query, term):
            continue
        matched.append(term)
        score += 3 if " " in term or "/" in term else 1
    if slug and _contains_term(query, slug):
        score += 5
        matched.append(slug)
    return score, list(dict.fromkeys(matched))


def recommend_pilot_pipeline_templates(
    *,
    user_message: str,
    pipeline_name: str = "",
    limit: int = 3,
) -> list[dict[str, Any]]:
    query = _normalise_query(f"{pipeline_name} {user_message}")
    recommendations: list[dict[str, Any]] = []
    for template in _pilot_templates():
        score, matched_terms = _score_template(template, query)
        if score <= 0:
            continue
        nodes = [node for node in template.get("nodes", []) if isinstance(node, dict)]
        edges = [edge for edge in template.get("edges", []) if isinstance(edge, dict)]
        recommendations.append(
            {
                "slug": _text(template.get("slug")),
                "name": _text(template.get("name")),
                "description": _text(template.get("description")),
                "category": _text(template.get("category")),
                "tags": [str(tag) for tag in (template.get("tags") or []) if str(tag).strip()],
                "match_score": score,
                "matched_terms": matched_terms[:8],
                "node_types": list(dict.fromkeys(_text(node.get("type")) for node in nodes if _text(node.get("type")))),
                "skeleton": {
                    "nodes": [_compact_template_node(node) for node in nodes],
                    "edges": [_compact_template_edge(edge) for edge in edges],
                },
            }
        )
    recommendations.sort(key=lambda item: (-int(item["match_score"]), item["slug"]))
    return recommendations[: max(0, limit)]


def get_pilot_pipeline_template(slug: str) -> dict[str, Any] | None:
    normalized = _text(slug)
    for template in _pilot_templates():
        if template.get("slug") == normalized:
            return template
    return None


def _safe_ref(raw_value: str, *, fallback: str, used_refs: set[str]) -> str:
    ref = re.sub(r"[^a-zA-Z0-9_]+", "_", _text(raw_value).lower()).strip("_") or fallback
    if not re.match(r"^[a-zA-Z_]", ref):
        ref = f"{fallback}_{ref}"
    ref = ref[:48].strip("_") or fallback
    candidate = ref
    counter = 2
    while candidate in used_refs:
        candidate = f"{ref}_{counter}"
        counter += 1
    used_refs.add(candidate)
    return candidate


def _match_context_mcp(expected_name: str, assistant_context: dict[str, Any]) -> dict[str, Any] | None:
    expected = _normalise_query(expected_name)
    if not expected:
        return None
    expected_tokens = [token for token in re.split(r"[^a-z0-9]+", expected) if token and token != "mcp"]
    candidates = assistant_context.get("available_mcp_servers")
    if not isinstance(candidates, list):
        return None
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        haystack = _normalise_query(
            " ".join(_text(item.get(field)) for field in ("name", "description", "transport", "url"))
        )
        score = sum(1 for token in expected_tokens if _contains_term(haystack, token))
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], _text(pair[1].get("name"))))
    return scored[0][1] if scored else None


def _match_context_server(assistant_context: dict[str, Any]) -> dict[str, Any] | None:
    candidates = assistant_context.get("available_servers")
    if not isinstance(candidates, list):
        return None
    servers = [item for item in candidates if isinstance(item, dict) and item.get("id") is not None]
    if not servers:
        return None

    query = _normalise_query(
        " ".join(
            _text(assistant_context.get(field))
            for field in ("binding_query", "pipeline_name", "user_message")
        )
    )
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in servers:
        name = _normalise_query(_text(item.get("name")))
        host = _normalise_query(_text(item.get("host")))
        score = 0
        if query and name and _contains_term(query, name):
            score += 6
        if query and host and _contains_term(query, host):
            score += 4
        for token in re.split(r"[^a-z0-9]+", name):
            if len(token) >= 4 and _contains_term(query, token):
                score += 1
        if score:
            scored.append((score, item))

    scored.sort(key=lambda pair: (-pair[0], _text(pair[1].get("name"))))
    if scored:
        return scored[0][1]
    if len(servers) == 1:
        return servers[0]
    return None


def _skill_slug_map(assistant_context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    skills = assistant_context.get("available_skills")
    if not isinstance(skills, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in skills:
        if not isinstance(item, dict):
            continue
        slug = _text(item.get("slug"))
        if slug:
            result[slug.lower()] = item
    return result


def _matching_context_skills(
    *,
    expected_name: str,
    existing_slugs: object,
    assistant_context: dict[str, Any],
) -> list[str]:
    available = _skill_slug_map(assistant_context)
    existing = [slug for slug in existing_slugs or [] if _text(slug)]
    selected = [_text(slug) for slug in existing if _text(slug).lower() in available]

    expected = _normalise_query(expected_name)
    tokens = [token for token in re.split(r"[^a-z0-9]+", expected) if len(token) >= 4 and token != "mcp"]
    if not tokens:
        return selected

    for item in available.values():
        slug = _text(item.get("slug"))
        if not slug or slug in selected:
            continue
        haystack = _normalise_query(
            " ".join(_text(item.get(field)) for field in ("slug", "name", "service", "category"))
        )
        if any(_contains_term(haystack, token) for token in tokens):
            selected.append(slug)
        if len(selected) >= 4:
            break
    return selected


def _bind_template_node_data(
    data: dict[str, Any],
    assistant_context: dict[str, Any],
    *,
    argument_bindings: dict[str, str],
) -> dict[str, Any]:
    next_data = enrich_mcp_node_data_with_pilot_spec(data)
    expected_mcp = _text(next_data.get("mcp_server_name"))
    if _text(next_data.get("mcp_server_id")) == "" and expected_mcp:
        matched_mcp = _match_context_mcp(expected_mcp, assistant_context)
        if matched_mcp and matched_mcp.get("id") is not None:
            next_data["mcp_server_id"] = matched_mcp.get("id")

    if "server_id" in next_data and _text(next_data.get("server_id")) == "":
        matched_server = _match_context_server(assistant_context)
        if matched_server and matched_server.get("id") is not None:
            next_data["server_id"] = matched_server.get("id")

    bound_skills = _matching_context_skills(
        expected_name=expected_mcp,
        existing_slugs=next_data.get("skill_slugs"),
        assistant_context=assistant_context,
    )
    if bound_skills or "skill_slugs" in next_data:
        next_data["skill_slugs"] = bound_skills
    if argument_bindings:
        next_data = _replace_bound_placeholders(next_data, argument_bindings)
    return next_data


def build_template_graph_patch(
    template: dict[str, Any],
    *,
    assistant_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = assistant_context or {}
    argument_bindings = _extract_template_argument_bindings(_text(template.get("slug")), context)
    used_refs: set[str] = set()
    id_to_ref: dict[str, str] = {}
    graph_nodes: list[dict[str, Any]] = []

    for index, node in enumerate(template.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        node_id = _text(node.get("id")) or f"node_{index + 1}"
        ref = _safe_ref(node_id, fallback=f"node_{index + 1}", used_refs=used_refs)
        id_to_ref[node_id] = ref
        data = _bind_template_node_data(
            node.get("data") if isinstance(node.get("data"), dict) else {},
            context,
            argument_bindings=argument_bindings,
        )
        position = node.get("position") if isinstance(node.get("position"), dict) else {}
        graph_nodes.append(
            {
                "ref": ref,
                "type": _text(node.get("type")),
                "label": _template_label(node),
                "data": data,
                "x_offset": position.get("x") if isinstance(position.get("x"), (int, float)) else None,
                "y_offset": position.get("y") if isinstance(position.get("y"), (int, float)) else None,
            }
        )

    graph_edges: list[dict[str, Any]] = []
    for edge in template.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source = id_to_ref.get(_text(edge.get("source")), _text(edge.get("source")))
        target = id_to_ref.get(_text(edge.get("target")), _text(edge.get("target")))
        if not source or not target:
            continue
        graph_edges.append(
            {
                "source": source,
                "target": target,
                "source_handle": _text(edge.get("source_handle") or edge.get("sourceHandle") or "out"),
                "target_handle": _text(edge.get("target_handle") or edge.get("targetHandle")) or None,
                "label": _text(edge.get("label")) or None,
            }
        )

    return {
        "anchor_node_id": None,
        "nodes": graph_nodes,
        "edges": graph_edges,
        "update_nodes": [],
        "remove_node_ids": [],
        "remove_edge_ids": [],
    }


def build_template_resource_plan(
    template: dict[str, Any],
    *,
    assistant_context: dict[str, Any],
) -> dict[str, Any]:
    selected_mcp: list[dict[str, Any]] = []
    selected_servers: list[dict[str, Any]] = []
    selected_skills: list[dict[str, Any]] = []
    missing: list[str] = []
    notes: list[str] = []
    available_skills = _skill_slug_map(assistant_context)
    argument_bindings = _extract_template_argument_bindings(_text(template.get("slug")), assistant_context)
    if argument_bindings:
        notes.append("Bound prompt arguments: " + ", ".join(sorted(argument_bindings)))
    expected_mcp_names = list(
        dict.fromkeys(
            _text((node.get("data") or {}).get("mcp_server_name"))
            for node in template.get("nodes", [])
            if isinstance(node, dict) and isinstance(node.get("data"), dict) and _text(node["data"].get("mcp_server_name"))
        )
    )
    for expected_name in expected_mcp_names:
        matched = _match_context_mcp(expected_name, assistant_context)
        if matched:
            selected_mcp.append(matched)
            notes.append(f"Matched {expected_name} to MCP server #{matched.get('id')}.")
        else:
            missing.append(expected_name)

    needs_server = any(
        isinstance(node, dict)
        and isinstance(node.get("data"), dict)
        and "server_id" in node["data"]
        for node in template.get("nodes", [])
    )
    if needs_server:
        matched_server = _match_context_server(assistant_context)
        if matched_server:
            selected_servers.append(matched_server)
            notes.append(f"Matched target server #{matched_server.get('id')}.")
        else:
            missing.append("Target server for OPS nodes")

    for node in template.get("nodes", []):
        if not isinstance(node, dict) or not isinstance(node.get("data"), dict):
            continue
        data = enrich_mcp_node_data_with_pilot_spec(node["data"])
        expected_name = _text(data.get("mcp_server_name"))
        expected_skill_slugs = [_text(slug) for slug in data.get("skill_slugs") or [] if _text(slug)]
        for slug in expected_skill_slugs:
            if available_skills and slug.lower() in available_skills:
                continue
            missing_label = f"Skill: {slug}"
            if missing_label not in missing:
                missing.append(missing_label)
        for slug in _matching_context_skills(
            expected_name=expected_name,
            existing_slugs=data.get("skill_slugs"),
            assistant_context=assistant_context,
        ):
            skill = available_skills.get(slug.lower())
            if skill and skill not in selected_skills:
                selected_skills.append(skill)
            elif not skill and slug not in missing:
                missing.append(f"Skill: {slug}")

    unresolved_inputs, runtime_inputs = _unresolved_operational_placeholders(template, bindings=argument_bindings)
    for placeholder in unresolved_inputs:
        missing.append(f"Argument: {placeholder}")
    if runtime_inputs:
        notes.append("Runtime arguments expected from webhook or previous nodes: " + ", ".join(runtime_inputs) + ".")

    return {
        "servers": selected_servers,
        "agents": [],
        "mcp_servers": selected_mcp,
        "skills": selected_skills,
        "missing": list(dict.fromkeys(missing)),
        "notes": notes or [f"Review resources for template '{template.get('slug')}' before applying."],
    }
