from __future__ import annotations

import re
from typing import Any

from studio.services.pipeline_template_text import _contains_term, _normalise_query, _text

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
