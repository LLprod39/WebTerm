from __future__ import annotations

from typing import Any

ARGUMENT_QUESTIONS = {
    "realm": "Укажи Keycloak realm.",
    "username": "Укажи username/login/email пользователя или service account.",
    "role": "Укажи роль, которую нужно добавить или убрать.",
    "group": "Укажи группу, если задача про group membership.",
    "operation": "Укажи действие: add или remove.",
    "cluster": "Укажи Kubernetes cluster/context.",
    "namespace": "Укажи Kubernetes namespace.",
    "kind": "Укажи тип workload: deployment, statefulset или daemonset.",
    "workload_name": "Укажи имя workload/deployment.",
    "project_id": "Укажи GitLab/GitHub project id или repo path.",
    "pipeline_id": "Укажи pipeline/job id.",
    "branch": "Укажи target branch.",
    "commit_sha": "Укажи commit SHA, если задача связана с конкретным run.",
    "database": "Укажи database name или connection alias.",
    "schema": "Укажи DB schema, если она важна.",
    "service_name": "Укажи имя сервиса/application.",
    "healthcheck_url": "Укажи healthcheck URL.",
    "packages": "Укажи точный список OS packages.",
    "backup_path": "Укажи путь к backup каталогу.",
    "max_age_hours": "Укажи максимальный возраст backup в часах.",
    "alert_id": "Укажи alert id/fingerprint или incident source reference.",
    "alert_source": "Укажи источник алерта: Grafana, Prometheus, Loki, Sentry, PagerDuty или Jira.",
    "alert_severity": "Укажи severity: critical, warning, info или unknown.",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _question_for_missing(item: str) -> tuple[int, str] | None:
    text = _text(item)
    if not text:
        return None

    if text.startswith("Argument: "):
        field = text.removeprefix("Argument: ").strip()
        return 10, ARGUMENT_QUESTIONS.get(field, f"Укажи значение для `{field}`.")

    lowered = text.lower()
    if "target server" in lowered or "server for ops" in lowered:
        return 20, "Укажи target server name/host для OPS-ноды."
    if "mcp" in lowered:
        return 30, f"Подключи или выбери MCP server для `{text}`."
    if text.startswith("Skill: "):
        return None
    return 50, f"Уточни ресурс: {text}."


def questions_from_resource_plan(resource_plan: dict[str, Any] | None, *, limit: int = 3) -> list[str]:
    plan = resource_plan if isinstance(resource_plan, dict) else {}
    missing = plan.get("missing")
    if not isinstance(missing, list):
        return []

    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for item in missing:
        question = _question_for_missing(_text(item))
        if question is None:
            continue
        score, text = question
        if text in seen:
            continue
        seen.add(text)
        scored.append((score, text))

    scored.sort(key=lambda pair: (pair[0], pair[1]))
    return [text for _score, text in scored[: max(0, limit)]]


def augment_response_with_interview_questions(response: dict[str, Any]) -> dict[str, Any]:
    questions = response.get("questions")
    existing = [str(item).strip() for item in questions if str(item).strip()] if isinstance(questions, list) else []
    derived = questions_from_resource_plan(response.get("resource_plan"), limit=3)
    merged = list(dict.fromkeys([*existing, *derived]))[:3]
    response["questions"] = merged

    if merged:
        actions = response.get("suggested_next_actions")
        action_items = [str(item).strip() for item in actions if str(item).strip()] if isinstance(actions, list) else []
        prompt = "Ответьте на вопросы в Composer обычным текстом, затем нажмите Revise draft."
        response["suggested_next_actions"] = list(dict.fromkeys([prompt, *action_items]))[:8]
    return response


def build_revision_interview_message(
    *,
    original_goal: str,
    user_message: str,
    previous_questions: list[str] | None,
) -> str:
    answer = _text(user_message)
    goal = _text(original_goal)
    questions = [str(item).strip() for item in previous_questions or [] if str(item).strip()]
    if not questions or not goal:
        return answer

    question_block = "\n".join(f"- {question}" for question in questions[:3])
    return (
        "Исходная задача автоматизации:\n"
        f"{goal}\n\n"
        "Открытые вопросы, на которые отвечает оператор:\n"
        f"{question_block}\n\n"
        "Ответ/уточнение оператора:\n"
        f"{answer}\n\n"
        "Используй ответ, чтобы заполнить missing arguments/resources, сохрани safety shape, approval, verification и report."
    )


def merge_revision_goal(
    *,
    original_goal: str,
    user_message: str,
    previous_questions: list[str] | None,
) -> str:
    goal = _text(original_goal)
    answer = _text(user_message)
    questions = [str(item).strip() for item in previous_questions or [] if str(item).strip()]
    if not questions or not goal:
        return answer or goal
    if not answer:
        return goal
    if "Ответы оператора:" in goal and answer in goal:
        return goal
    return f"{goal}\n\nОтветы оператора: {answer}"[:4000]
