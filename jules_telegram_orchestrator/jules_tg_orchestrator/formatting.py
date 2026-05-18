from __future__ import annotations

import re
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


def format_chief_run(run: dict) -> str:
    message = compact(run.get("message"), max_len=140)
    thread = run.get("thread_id") or "session pending"
    return f"Chief run #{run['run_id']} {run['status']} - {message}\nThread: {thread}"


def format_pending_plan(plan: dict) -> str:
    message = compact(plan.get("message"), max_len=140)
    return f"Plan #{plan['plan_id']} {plan['status']} - {message}"


def format_activity(activity: dict) -> str:
    created = activity.get("createTime") or ""

    if plan_generated := activity.get("planGenerated"):
        plan = plan_generated.get("plan") or {}
        steps = plan.get("steps") or []
        lines = [f"Jules подготовил план {created}".strip()]
        for step in steps[:5]:
            index = step.get("index")
            title = step.get("title") or "Step"
            step_no = index + 1 if isinstance(index, int) else "?"
            lines.append(f"{step_no}. {title}")
        return "\n".join(lines)

    if activity.get("planApproved") is not None:
        return f"План Jules одобрен {created}".strip()

    if agent_messaged := activity.get("agentMessaged"):
        return f"Jules сообщение {created}\n{compact(agent_messaged.get('agentMessage'), max_len=900)}".strip()

    if progress_updated := activity.get("progressUpdated"):
        title = progress_updated.get("title") or "Jules обновил статус"
        description = compact(progress_updated.get("description"), max_len=700)
        artifact_summary = _summarize_artifacts(activity.get("artifacts") or [])
        lines = [f"{title} {created}".strip()]
        if description:
            lines.append(description)
        if artifact_summary:
            lines.append(artifact_summary)
        return "\n".join(lines)

    if session_failed := activity.get("sessionFailed"):
        return f"Jules session failed {created}\n{session_failed.get('reason', '')}".strip()

    if activity.get("sessionCompleted") is not None:
        artifact_summary = _summarize_artifacts(activity.get("artifacts") or [])
        lines = [f"Jules завершил работу {created}".strip()]
        if artifact_summary:
            lines.append(artifact_summary)
        return "\n".join(lines)

    artifact_summary = _summarize_artifacts(activity.get("artifacts") or [])
    if artifact_summary:
        return f"Jules обновил изменения {created}\n{artifact_summary}".strip()

    return f"Jules activity {created}".strip()


def summarize_session_outputs(session: dict) -> str:
    outputs = session.get("outputs") or []
    lines: list[str] = []
    for output in outputs:
        if pull_request := output.get("pullRequest"):
            title = pull_request.get("title") or "Pull request"
            url = pull_request.get("url") or ""
            lines.append(f"PR: {title}" + (f"\n{url}" if url else ""))
        if change_set := output.get("changeSet"):
            summary = _summarize_change_set(change_set)
            if summary:
                lines.append(summary)
    return "\n".join(lines)


def first_change_set_patch(session: dict) -> tuple[str, str]:
    for output in session.get("outputs") or []:
        change_set = output.get("changeSet") or {}
        git_patch = change_set.get("gitPatch") or {}
        patch = git_patch.get("unidiffPatch") or ""
        message = git_patch.get("suggestedCommitMessage") or "Apply Jules changes"
        if patch:
            return patch, message
    return "", ""


def first_pull_request_url(session: dict) -> str:
    for output in session.get("outputs") or []:
        pull_request = output.get("pullRequest") or {}
        url = pull_request.get("url") or ""
        if url:
            return url
    return ""


def _summarize_artifacts(artifacts: list[dict]) -> str:
    lines: list[str] = []
    for artifact in artifacts:
        if change_set := artifact.get("changeSet"):
            summary = _summarize_change_set(change_set)
            if summary:
                lines.append(summary)
        if bash_output := artifact.get("bashOutput"):
            command = bash_output.get("command", "")
            exit_code = bash_output.get("exitCode")
            output = compact(bash_output.get("output"), max_len=450)
            lines.append(f"Команда: {command}\nexit={exit_code}\n{output}")
    return "\n".join(lines)


def _summarize_change_set(change_set: dict) -> str:
    git_patch = change_set.get("gitPatch") or {}
    patch = git_patch.get("unidiffPatch") or ""
    commit_message = git_patch.get("suggestedCommitMessage") or ""
    files = _patch_file_stats(patch)
    lines: list[str] = []
    if files:
        lines.append("Изменения:")
        lines.extend(f"- {path}: +{added}/-{removed}" for path, added, removed in files[:8])
    if commit_message:
        lines.append(f"Commit: {commit_message}")
    return "\n".join(lines)


def _patch_file_stats(patch: str) -> list[tuple[str, int, int]]:
    files: list[tuple[str, int, int]] = []
    current_path = ""
    added = 0
    removed = 0
    for line in patch.splitlines():
        match = re.match(r"diff --git a/(.*?) b/(.*?)$", line)
        if match:
            if current_path:
                files.append((current_path, added, removed))
            current_path = match.group(2)
            added = 0
            removed = 0
            continue
        if not current_path or line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    if current_path:
        files.append((current_path, added, removed))
    return files
