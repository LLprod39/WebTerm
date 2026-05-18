from __future__ import annotations

from collections.abc import Iterable

TELEGRAM_LIMIT = 4096
SAFE_CHUNK = 3700


def split_message(text: str, *, limit: int = SAFE_CHUNK) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > limit and current:
            chunks.append("".join(current).rstrip())
            current = []
            current_len = 0
        if len(line) > limit:
            chunks.extend(line[i : i + limit] for i in range(0, len(line), limit))
            continue
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append("".join(current).rstrip())
    return chunks


def compact(value: object, *, max_len: int = 900) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1]}..."


def bullet_lines(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def format_source(source: dict) -> str:
    repo = source.get("githubRepo") or {}
    default_branch = (repo.get("defaultBranch") or {}).get("displayName", "")
    private_suffix = " private" if repo.get("isPrivate") else ""
    repo_label = f"{repo.get('owner', '?')}/{repo.get('repo', '?')}"
    branch_suffix = f" default={default_branch}" if default_branch else ""
    return f"{source.get('name', source.get('id', '?'))} ({repo_label}{private_suffix}{branch_suffix})"


def format_session(session: dict) -> str:
    title = session.get("title") or session.get("prompt") or "Untitled"
    state = session.get("state") or "UNKNOWN"
    session_id = session.get("id") or session.get("name", "").split("/")[-1]
    url = session.get("url") or ""
    output_urls: list[str] = []
    for output in session.get("outputs") or []:
        pull_request = output.get("pullRequest") or {}
        if pull_request.get("url"):
            output_urls.append(pull_request["url"])
    lines = [f"{session_id}: {state}", compact(title, max_len=180)]
    if url:
        lines.append(url)
    if output_urls:
        lines.append("Outputs: " + ", ".join(output_urls))
    return "\n".join(lines)


def format_task(task: dict) -> str:
    lines = [
        f"Task #{task['task_id']}: {task['status']} - {task['title']}",
        f"Priority: {task['priority']}",
    ]
    if task.get("branch"):
        lines.append(f"Branch: {task['branch']}")
    if task.get("source"):
        lines.append(f"Jules source: {task['source']}")
    description = compact(task.get("description"), max_len=1200)
    if description:
        lines.append("")
        lines.append(description)
    return "\n".join(lines)


def format_task_event(event: dict) -> str:
    return f"{event['created_at']} [{event['kind']}] {event['message']}"


def format_agent_run(run: dict) -> str:
    summary = compact(run.get("summary"), max_len=240)
    suffix = f" - {summary}" if summary else ""
    return f"Run #{run['run_id']} {run['agent_kind']} {run['status']}{suffix}"


def format_activity(activity: dict) -> str:
    prefix = activity.get("description") or "Jules activity"
    created = activity.get("createTime") or ""

    if plan_generated := activity.get("planGenerated"):
        plan = plan_generated.get("plan") or {}
        steps = plan.get("steps") or []
        lines = [f"{prefix} {created}".strip(), "Plan:"]
        for step in steps:
            index = step.get("index")
            title = step.get("title") or "Step"
            description = compact(step.get("description"), max_len=260)
            step_no = index + 1 if isinstance(index, int) else "?"
            lines.append(f"{step_no}. {title}")
            if description:
                lines.append(f"   {description}")
        return "\n".join(lines)

    if agent_messaged := activity.get("agentMessaged"):
        return f"{prefix} {created}\n{agent_messaged.get('agentMessage', '')}".strip()

    if progress_updated := activity.get("progressUpdated"):
        title = progress_updated.get("title") or prefix
        description = compact(progress_updated.get("description"), max_len=500)
        return f"{title} {created}\n{description}".strip()

    if session_failed := activity.get("sessionFailed"):
        return f"Jules session failed {created}\n{session_failed.get('reason', '')}".strip()

    if activity.get("sessionCompleted") is not None:
        return f"Jules session completed {created}".strip()

    artifact_lines: list[str] = []
    for artifact in activity.get("artifacts") or []:
        if change_set := artifact.get("changeSet"):
            patch = change_set.get("gitPatch") or {}
            if patch.get("suggestedCommitMessage"):
                artifact_lines.append(f"Suggested commit: {patch['suggestedCommitMessage']}")
            if patch.get("unidiffPatch"):
                artifact_lines.append(compact(patch["unidiffPatch"], max_len=1000))
        if bash_output := artifact.get("bashOutput"):
            command = bash_output.get("command", "")
            exit_code = bash_output.get("exitCode")
            output = compact(bash_output.get("output"), max_len=1000)
            artifact_lines.append(f"$ {command}\nexit={exit_code}\n{output}")

    if artifact_lines:
        return f"{prefix} {created}\n" + "\n".join(artifact_lines)

    return f"{prefix} {created}".strip()
