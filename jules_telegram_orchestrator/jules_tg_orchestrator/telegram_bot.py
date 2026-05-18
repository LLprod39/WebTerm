from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from functools import wraps

from telegram import Bot, ReplyKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from jules_tg_orchestrator.codex_cli import CodexCli, CodexCliError
from jules_tg_orchestrator.config import Config
from jules_tg_orchestrator.coordinator import Coordinator, DelegationDraft
from jules_tg_orchestrator.formatting import (
    bullet_lines,
    compact,
    format_activity,
    format_agent_run,
    format_session,
    format_source,
    format_task,
    format_task_event,
    split_message,
)
from jules_tg_orchestrator.gemini_cli import GeminiCli, GeminiCliError
from jules_tg_orchestrator.git_ops import GitOps, GitOpsError
from jules_tg_orchestrator.jules_client import JulesApiError, JulesClient
from jules_tg_orchestrator.policy import AutonomyPolicy
from jules_tg_orchestrator.storage import Storage

logger = logging.getLogger(__name__)
CODEX_CHIEF_SESSION_KEY = "codex_chief_session_id"

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["Статус", "Задачи", "Git"],
        ["Codex", "Gemini", "Jules"],
        ["Policy", "Новый чат Codex"],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


class BotRuntime:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.storage = Storage(config.database_path)
        self.jules = JulesClient(api_key=config.jules_api_key, base_url=config.jules_base_url)
        self.codex = CodexCli(
            command=config.codex_cli_command,
            cwd=config.project_root,
            timeout_seconds=config.codex_cli_timeout_seconds,
            model=config.codex_cli_model,
            sandbox=config.codex_cli_sandbox,
            approval=config.codex_cli_approval,
            search=config.codex_cli_search,
        )
        self.gemini = GeminiCli(
            command=config.gemini_cli_command,
            cwd=config.project_root,
            timeout_seconds=config.gemini_cli_timeout_seconds,
            output_format=config.gemini_cli_output_format,
            model=config.gemini_cli_model,
            approval_mode=config.gemini_cli_approval_mode,
        )
        self.git = GitOps(config.project_root, branch_prefix=config.git_branch_prefix, remote=config.git_remote)
        self.policy = AutonomyPolicy.from_config(config)
        self.coordinator = Coordinator(
            default_source=config.jules_default_source,
            default_branch=config.jules_default_branch,
        )
        self.poll_task: asyncio.Task[None] | None = None

    async def close(self) -> None:
        if self.poll_task:
            self.poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.poll_task
        await self.jules.close()
        self.storage.close()


def runtime(context: ContextTypes.DEFAULT_TYPE) -> BotRuntime:
    return context.application.bot_data["runtime"]


async def send_text(update: Update, text: str) -> None:
    if not update.effective_chat:
        return
    for chunk in split_message(text):
        await update.effective_chat.send_message(chunk, disable_web_page_preview=True, reply_markup=MAIN_KEYBOARD)


async def send_to_chat(bot: Bot, chat_id: int, text: str) -> None:
    for chunk in split_message(text):
        await bot.send_message(chat_id=chat_id, text=chunk, disable_web_page_preview=True, reply_markup=MAIN_KEYBOARD)


async def keep_typing(bot: Bot, chat_id: int, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4)
        except TimeoutError:
            continue


Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]


def restricted(handler: Handler) -> Handler:
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        rt = runtime(context)
        user = update.effective_user
        if rt.config.telegram_allowed_user_ids and (not user or user.id not in rt.config.telegram_allowed_user_ids):
            if update.effective_chat:
                await update.effective_chat.send_message("Access denied.")
            return
        try:
            await handler(update, context)
        except JulesApiError as exc:
            await send_text(update, f"Jules API error:\n{exc}")
        except GitOpsError as exc:
            await send_text(update, f"Git error:\n{exc}")
        except GeminiCliError as exc:
            await send_text(update, f"Gemini CLI error:\n{exc}")
        except CodexCliError as exc:
            await send_text(update, f"Codex CLI error:\n{exc}")
        except Exception:
            logger.exception("Telegram handler failed")
            await send_text(update, "Internal bot error. Check logs for details.")

    return wrapper


@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    allowed = "configured" if rt.config.telegram_allowed_user_ids else "not configured"
    default_source = rt.config.jules_default_source or "not set"
    await send_text(
        update,
        "\n".join(
            [
                "Jules Telegram Orchestrator is running.",
                "",
                "Use the keyboard buttons below for common actions.",
                "",
                "Commands:",
                "/overview - show chief status",
                "/policy - show autonomy policy",
                "/codex_check - verify Codex CLI",
                "/codex_reset - forget stored Codex chief session",
                "/git_status - show project git status",
                "/task <description> - create project task",
                "/tasks - list project tasks",
                "/task_status <task_id> - show project task details",
                "/delegate_task <task_id> - delegate project task to Jules",
                "/gemini_check - verify Gemini CLI auth",
                "/gemini_task <task_id> - delegate task to Gemini CLI",
                "/gemini_review <task_id> - ask Gemini to review current diff",
                "/commit_task <task_id> [message] - commit current changes",
                "/push - push current branch",
                "/pr_task <task_id> - create PR for current branch",
                "/sources - list Jules repositories",
                "/delegate <source> <branch> <task> - create Jules session",
                "/delegate <task> - use default source and branch",
                "/confirm_delegate - create session from the current draft",
                "/sessions - list tracked sessions",
                "/status <session_id> - show session state",
                "/approve <session_id> - approve plan",
                "/say <session_id> <message> - send feedback to Jules",
                "/watch <session_id> - track an existing Jules session",
                "/unwatch <session_id> - stop tracking",
                "",
                f"Allowed users: {allowed}",
                f"Default source: {default_source}",
                f"Default branch: {rt.config.jules_default_branch}",
                f"Project root: {rt.config.project_root}",
                f"Codex chief enabled: {rt.config.codex_chief_enabled}",
                f"Gemini CLI enabled: {rt.config.gemini_cli_enabled}",
                f"Plan approval required: {rt.config.jules_require_plan_approval}",
                f"Auto-create PR: {rt.config.jules_auto_create_pr}",
            ]
        ),
    )


@restricted
async def policy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_text(update, runtime(context).policy.render())


@restricted
async def codex_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    if not rt.config.codex_chief_enabled:
        raise CodexCliError("Codex chief adapter is disabled by CODEX_CHIEF_ENABLED=false")
    version = await asyncio.to_thread(rt.codex.version)
    session_id = rt.storage.get_state(CODEX_CHIEF_SESSION_KEY, default="not created yet")
    await send_text(update, f"Codex CLI is available.\nVersion: {version}\nChief session: {session_id}")


@restricted
async def codex_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime(context).storage.delete_state(CODEX_CHIEF_SESSION_KEY)
    await send_text(update, "Сбросил сохраненную Codex chief session. Следующее сообщение создаст новый chief-thread.")


@restricted
async def git_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_text(update, runtime(context).git.status().render())


@restricted
async def sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    _require_jules(rt)
    items = await rt.jules.list_sources()
    if not items:
        await send_text(update, "No Jules sources found. Connect GitHub repositories in the Jules web app first.")
        return
    await send_text(update, "Jules sources:\n" + bullet_lines(format_source(item) for item in items))


def _task_title(description: str) -> str:
    title = " ".join(description.split())
    if len(title) <= 80:
        return title or "Project task"
    return title[:79].rstrip() + "..."


def _render_overview(rt: BotRuntime) -> str:
    git_status = rt.git.status()
    session_id = rt.storage.get_state(CODEX_CHIEF_SESSION_KEY, default="not created yet")
    task_rows = rt.storage.list_tasks(limit=5)
    tasks_text = "\n".join(f"#{row['task_id']} {row['status']} - {row['title']}" for row in task_rows)
    if not tasks_text:
        tasks_text = "No tasks yet"
    return "\n".join(
        [
            "AI Chief Orchestrator",
            f"Codex session: {session_id}",
            f"Project: {rt.config.project_root}",
            f"Branch: {git_status.branch}",
            f"Dirty: {git_status.is_dirty}",
            "",
            "Recent tasks:",
            tasks_text,
        ]
    )


@restricted
async def overview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_text(update, _render_overview(runtime(context)))


@restricted
async def task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        return
    description = " ".join(context.args).strip()
    if not description:
        await send_text(update, "Usage: /task <what should be done>")
        return

    rt = runtime(context)
    task_id = rt.storage.create_task(
        chat_id=update.effective_chat.id,
        title=_task_title(description),
        description=description,
        project_root=str(rt.config.project_root),
        source=rt.config.jules_default_source,
        branch=rt.config.jules_default_branch,
        status="READY",
    )

    branch_message = ""
    if rt.config.git_auto_create_branch:
        status = rt.git.status()
        if status.is_dirty:
            rt.storage.add_task_event(
                task_id,
                kind="branch_skipped",
                message="Auto branch creation skipped because working tree is dirty",
            )
            branch_message = "\nBranch not created automatically because git working tree is dirty."
        else:
            branch = rt.git.create_branch_for_task(task_id, description)
            rt.storage.update_task(task_id, branch=branch)
            rt.storage.add_task_event(task_id, kind="branch_created", message=f"Created branch {branch}")
            branch_message = f"\nCreated branch: {branch}"

    created = rt.storage.get_task(task_id)
    await send_text(update, f"Created project task.{branch_message}\n\n{format_task(created)}")


@restricted
async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    rows = rt.storage.list_tasks()
    if not rows:
        await send_text(update, "No project tasks yet.")
        return
    lines = [f"#{row['task_id']} {row['status']} - {row['title']}" for row in rows]
    await send_text(update, "\n".join(lines))


@restricted
async def task_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_text(update, "Usage: /task_status <task_id>")
        return
    rt = runtime(context)
    task_row = rt.storage.get_task(int(context.args[0]))
    if not task_row:
        await send_text(update, f"Task #{context.args[0]} not found.")
        return
    events = rt.storage.list_task_events(task_row["task_id"])
    runs = rt.storage.list_task_agent_runs(task_row["task_id"])
    event_text = "\n".join(format_task_event(event) for event in events) if events else "No events"
    run_text = "\n".join(format_agent_run(run) for run in runs) if runs else "No agent runs"
    await send_text(update, f"{format_task(task_row)}\n\nAgent runs:\n{run_text}\n\nRecent events:\n{event_text}")


def _require_gemini(rt: BotRuntime) -> None:
    if not rt.config.gemini_cli_enabled:
        raise GeminiCliError("Gemini CLI adapter is disabled by GEMINI_CLI_ENABLED=false")


def _require_jules(rt: BotRuntime) -> None:
    if not rt.config.jules_api_key:
        raise JulesApiError("JULES_API_KEY is not configured. Add it to .env before using Jules commands.")


def _build_gemini_task_prompt(task_row: dict) -> str:
    return "\n".join(
        [
            "You are a subordinate coding agent working for the AI Chief Orchestrator.",
            "Use the local repository as your workspace.",
            "Follow AGENTS.md and existing project conventions.",
            "Keep changes tightly scoped to the task.",
            "Do not commit, push, create branches, or open pull requests.",
            "Run relevant checks if practical. If a check cannot run, explain the blocker.",
            "At the end, report changed files, checks run, and remaining risks.",
            "",
            f"Task #{task_row['task_id']}: {task_row['title']}",
            task_row["description"],
        ]
    )


def _build_gemini_review_prompt(task_row: dict, diff_text: str) -> str:
    return "\n".join(
        [
            "You are reviewing local changes for the AI Chief Orchestrator.",
            "Do not edit files. Review only.",
            "Focus on concrete bugs, regressions, missing tests, and unsafe behavior.",
            "Return findings ordered by severity. If there are no issues, say so clearly.",
            "",
            f"Task #{task_row['task_id']}: {task_row['title']}",
            task_row["description"],
            "",
            diff_text,
        ]
    )


async def _execute_gemini_run(
    application: Application,
    *,
    chat_id: int,
    task_id: int,
    run_id: int,
    prompt: str,
    allow_edits: bool,
) -> None:
    rt: BotRuntime = application.bot_data["runtime"]
    try:
        result = await asyncio.to_thread(rt.gemini.run_prompt, prompt, allow_edits=allow_edits)
        summary = compact(result.render(max_len=700), max_len=700)
        rt.storage.update_agent_run(run_id, status="COMPLETED", summary=summary, output=result.raw_output)
        rt.storage.update_task(task_id, status="REVIEW")
        rt.storage.add_task_event(task_id, kind="gemini_completed", message=f"Gemini run #{run_id} completed")
        await send_to_chat(application.bot, chat_id, f"Gemini run #{run_id} completed for task #{task_id}:\n{result.render()}")
    except Exception as exc:
        logger.exception("Gemini run %s failed", run_id)
        message = str(exc)
        rt.storage.update_agent_run(run_id, status="FAILED", summary=message, output=message)
        rt.storage.update_task(task_id, status="BLOCKED")
        rt.storage.add_task_event(task_id, kind="gemini_failed", message=f"Gemini run #{run_id} failed: {message}")
        await send_to_chat(application.bot, chat_id, f"Gemini run #{run_id} failed for task #{task_id}:\n{message}")


@restricted
async def gemini_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    _require_gemini(rt)
    version = await asyncio.to_thread(rt.gemini.version)
    result = await asyncio.to_thread(rt.gemini.run_prompt, "Respond with exactly: OK", allow_edits=False)
    await send_text(update, f"Gemini CLI is available.\nVersion: {version}\nAuth check: {result.render(max_len=500)}")


@restricted
async def gemini_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_text(update, "Usage: /gemini_task <task_id>")
        return
    if not update.effective_chat:
        return
    rt = runtime(context)
    _require_gemini(rt)
    task_row = rt.storage.get_task(int(context.args[0]))
    if not task_row:
        await send_text(update, f"Task #{context.args[0]} not found.")
        return
    run_id = rt.storage.create_agent_run(task_id=task_row["task_id"], agent_kind="gemini_cli")
    rt.storage.update_task(task_row["task_id"], status="GEMINI_RUNNING")
    rt.storage.add_task_event(task_row["task_id"], kind="gemini_started", message=f"Started Gemini run #{run_id}")
    prompt = _build_gemini_task_prompt(task_row)
    context.application.create_task(
        _execute_gemini_run(
            context.application,
            chat_id=update.effective_chat.id,
            task_id=task_row["task_id"],
            run_id=run_id,
            prompt=prompt,
            allow_edits=True,
        )
    )
    await send_text(update, f"Started Gemini CLI run #{run_id} for task #{task_row['task_id']}.")


@restricted
async def gemini_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_text(update, "Usage: /gemini_review <task_id>")
        return
    if not update.effective_chat:
        return
    rt = runtime(context)
    _require_gemini(rt)
    task_row = rt.storage.get_task(int(context.args[0]))
    if not task_row:
        await send_text(update, f"Task #{context.args[0]} not found.")
        return
    run_id = rt.storage.create_agent_run(task_id=task_row["task_id"], agent_kind="gemini_cli_review")
    rt.storage.add_task_event(task_row["task_id"], kind="gemini_review_started", message=f"Started Gemini review #{run_id}")
    prompt = _build_gemini_review_prompt(task_row, rt.git.diff_for_review())
    context.application.create_task(
        _execute_gemini_run(
            context.application,
            chat_id=update.effective_chat.id,
            task_id=task_row["task_id"],
            run_id=run_id,
            prompt=prompt,
            allow_edits=False,
        )
    )
    await send_text(update, f"Started Gemini CLI review #{run_id} for task #{task_row['task_id']}.")


@restricted
async def commit_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_text(update, "Usage: /commit_task <task_id> [message]")
        return
    rt = runtime(context)
    task_row = rt.storage.get_task(int(context.args[0]))
    if not task_row:
        await send_text(update, f"Task #{context.args[0]} not found.")
        return
    message = " ".join(context.args[1:]).strip() or f"Task #{task_row['task_id']}: {task_row['title']}"
    commit_sha = rt.git.commit_all(message)
    rt.storage.update_task(task_row["task_id"], status="COMMITTED")
    rt.storage.add_task_event(task_row["task_id"], kind="committed", message=f"Created commit {commit_sha}")
    await send_text(update, f"Committed current changes for task #{task_row['task_id']}: {commit_sha}")


@restricted
async def push(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    branch = runtime(context).git.push_current_branch()
    await send_text(update, f"Pushed branch {branch}.")


@restricted
async def pr_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_text(update, "Usage: /pr_task <task_id>")
        return
    rt = runtime(context)
    task_row = rt.storage.get_task(int(context.args[0]))
    if not task_row:
        await send_text(update, f"Task #{context.args[0]} not found.")
        return
    body = "\n".join(
        [
            f"Task #{task_row['task_id']}",
            "",
            task_row["description"],
            "",
            "Created by AI Chief Orchestrator.",
        ]
    )
    pr_url = rt.git.create_pull_request(
        title=task_row["title"],
        body=body,
        base_branch=rt.config.jules_default_branch,
    )
    rt.storage.update_task(task_row["task_id"], status="PR")
    rt.storage.add_task_event(task_row["task_id"], kind="pr_created", message=pr_url)
    await send_text(update, f"Created PR for task #{task_row['task_id']}:\n{pr_url}")


def _parse_delegate_args(args: list[str], rt: BotRuntime) -> DelegationDraft:
    text = " ".join(args).strip()
    if not text:
        return DelegationDraft(prompt="", source=rt.config.jules_default_source, branch=rt.config.jules_default_branch)

    # Full form: /delegate <source> <branch> <task...>
    if len(args) >= 3 and (args[0].startswith("sources/") or "/" in args[0] or args[0].startswith("github-")):
        return rt.coordinator.build_draft(" ".join(args[2:]), source=args[0], branch=args[1])

    updates = rt.coordinator.parse_key_values(text)
    if updates:
        return rt.coordinator.build_draft(
            updates.get("task") or updates.get("prompt") or "",
            source=updates.get("source") or updates.get("repo") or "",
            branch=updates.get("branch") or "",
            title=updates.get("title") or "",
        )

    return rt.coordinator.build_draft(text)


async def _create_jules_session(
    update: Update,
    rt: BotRuntime,
    draft: DelegationDraft,
    *,
    task_id: int | None = None,
) -> None:
    if not update.effective_chat:
        return
    _require_jules(rt)
    source = await rt.jules.resolve_source(draft.source)
    prompt = rt.coordinator.build_jules_prompt(draft)
    session = await rt.jules.create_session(
        prompt=prompt,
        title=draft.title,
        source=source,
        branch=draft.branch,
        require_plan_approval=rt.config.jules_require_plan_approval,
        auto_create_pr=rt.config.jules_auto_create_pr,
    )
    session_id = session.get("id") or session.get("name", "").split("/")[-1]
    rt.storage.upsert_session(
        session_id=session_id,
        chat_id=update.effective_chat.id,
        title=session.get("title") or draft.title,
        source=source,
        branch=draft.branch,
        state=session.get("state") or "UNKNOWN",
        url=session.get("url") or "",
        task_id=task_id,
    )
    if task_id is not None:
        rt.storage.update_task(task_id, status="DELEGATED", source=source, branch=draft.branch)
        rt.storage.add_task_event(
            task_id,
            kind="delegated",
            message=f"Delegated to Jules session {session_id}",
            payload={"session_id": session_id},
        )
    rt.storage.clear_draft(update.effective_chat.id)
    await send_text(update, "Delegated to Jules:\n" + format_session(session))


@restricted
async def delegate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    draft = _parse_delegate_args(context.args, rt)
    decision = rt.coordinator.evaluate(draft)
    if not decision.ready:
        if update.effective_chat and decision.draft:
            rt.storage.save_draft(update.effective_chat.id, decision.draft)
        await send_text(update, decision.question)
        return
    await _create_jules_session(update, rt, decision.draft or draft)


@restricted
async def delegate_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_text(update, "Usage: /delegate_task <task_id>")
        return
    rt = runtime(context)
    task_row = rt.storage.get_task(int(context.args[0]))
    if not task_row:
        await send_text(update, f"Task #{context.args[0]} not found.")
        return
    draft = rt.coordinator.build_draft(
        task_row["description"],
        source=task_row["source"],
        branch=task_row["branch"] or rt.config.jules_default_branch,
        title=task_row["title"],
    )
    decision = rt.coordinator.evaluate(draft)
    if not decision.ready:
        await send_text(update, decision.question)
        return
    await _create_jules_session(update, rt, decision.draft or draft, task_id=task_row["task_id"])


@restricted
async def confirm_delegate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    if not update.effective_chat:
        return
    draft = rt.storage.get_draft(update.effective_chat.id)
    if not draft:
        await send_text(update, "No pending delegation draft.")
        return
    decision = rt.coordinator.evaluate(draft)
    if not decision.ready:
        await send_text(update, decision.question)
        return
    await _create_jules_session(update, rt, decision.draft or draft)


@restricted
async def sessions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    rows = rt.storage.list_sessions()
    if not rows:
        await send_text(update, "No sessions tracked by this bot yet.")
        return
    lines = []
    for row in rows:
        lines.append(f"{row['session_id']}: {row['state']} - {row['title']}")
        if row["url"]:
            lines.append(row["url"])
    await send_text(update, "\n".join(lines))


@restricted
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_text(update, "Usage: /status <session_id>")
        return
    rt = runtime(context)
    _require_jules(rt)
    session = await rt.jules.get_session(context.args[0])
    session_id = session.get("id") or context.args[0].removeprefix("sessions/")
    if row := rt.storage.get_session(session_id):
        rt.storage.update_session_state(
            session_id, state=session.get("state") or row["state"], url=session.get("url") or ""
        )
    await send_text(update, format_session(session))


@restricted
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_text(update, "Usage: /approve <session_id>")
        return
    rt = runtime(context)
    _require_jules(rt)
    await rt.jules.approve_plan(context.args[0])
    await send_text(update, f"Approved latest Jules plan for session {context.args[0]}.")


@restricted
async def say(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await send_text(update, "Usage: /say <session_id> <message>")
        return
    rt = runtime(context)
    _require_jules(rt)
    session_id = context.args[0]
    message = " ".join(context.args[1:]).strip()
    await rt.jules.send_message(session_id, message)
    await send_text(update, f"Sent message to Jules session {session_id}.")


@restricted
async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_text(update, "Usage: /watch <session_id>")
        return
    if not update.effective_chat:
        return
    rt = runtime(context)
    _require_jules(rt)
    session = await rt.jules.get_session(context.args[0])
    session_id = session.get("id") or context.args[0].removeprefix("sessions/")
    source_context = session.get("sourceContext") or {}
    github_context = source_context.get("githubRepoContext") or {}
    rt.storage.upsert_session(
        session_id=session_id,
        chat_id=update.effective_chat.id,
        title=session.get("title") or "Watched Jules session",
        source=source_context.get("source") or "",
        branch=github_context.get("startingBranch") or "",
        state=session.get("state") or "UNKNOWN",
        url=session.get("url") or "",
        is_watched=True,
    )
    await send_text(update, "Now watching:\n" + format_session(session))


@restricted
async def unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_text(update, "Usage: /unwatch <session_id>")
        return
    rt = runtime(context)
    session_id = context.args[0].removeprefix("sessions/")
    rt.storage.set_watched(session_id, False)
    await send_text(update, f"Stopped watching Jules session {session_id}.")


async def _execute_codex_chief(
    application: Application,
    *,
    chat_id: int,
    user_id: int,
    message: str,
) -> None:
    rt: BotRuntime = application.bot_data["runtime"]
    session_id = rt.storage.get_state(CODEX_CHIEF_SESSION_KEY)
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(application.bot, chat_id, stop_typing))
    try:
        result = await asyncio.to_thread(
            rt.codex.run_chief_prompt,
            message,
            user_id=user_id,
            chat_id=chat_id,
            session_id=session_id,
        )
        if result.thread_id:
            rt.storage.set_state(CODEX_CHIEF_SESSION_KEY, result.thread_id)
        await send_to_chat(application.bot, chat_id, result.render())
    except CodexCliError as exc:
        if session_id and "not found" in str(exc).lower():
            rt.storage.delete_state(CODEX_CHIEF_SESSION_KEY)
            try:
                result = await asyncio.to_thread(
                    rt.codex.run_chief_prompt,
                    message,
                    user_id=user_id,
                    chat_id=chat_id,
                    session_id="",
                )
                if result.thread_id:
                    rt.storage.set_state(CODEX_CHIEF_SESSION_KEY, result.thread_id)
                await send_to_chat(application.bot, chat_id, result.render())
                return
            except Exception as retry_exc:
                logger.exception("Codex chief retry failed")
                await send_to_chat(application.bot, chat_id, f"Codex chief error:\n{retry_exc}")
                return
        logger.exception("Codex chief run failed")
        await send_to_chat(application.bot, chat_id, f"Codex chief error:\n{exc}")
    except Exception as exc:
        logger.exception("Codex chief run failed")
        await send_to_chat(application.bot, chat_id, f"Codex chief error:\n{exc}")
    finally:
        stop_typing.set()
        with contextlib.suppress(asyncio.CancelledError):
            await typing_task


@restricted
async def natural_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    rt = runtime(context)
    text = update.message.text or ""
    button = text.strip().casefold()
    if button == "статус":
        await send_text(update, _render_overview(rt))
        return
    if button == "задачи":
        await tasks(update, context)
        return
    if button == "git":
        await git_status(update, context)
        return
    if button == "codex":
        await codex_check(update, context)
        return
    if button == "gemini":
        await gemini_check(update, context)
        return
    if button == "jules":
        if not rt.config.jules_api_key:
            await send_text(update, "Jules пока не настроен: добавь JULES_API_KEY в .env.")
            return
        await sources(update, context)
        return
    if button == "policy":
        await policy(update, context)
        return
    if button == "новый чат codex":
        await codex_reset(update, context)
        return
    if not rt.config.codex_chief_enabled:
        await send_text(update, "Codex chief adapter is disabled. Enable CODEX_CHIEF_ENABLED=true.")
        return
    user_id = update.effective_user.id if update.effective_user else 0
    context.application.create_task(
        _execute_codex_chief(
            context.application,
            chat_id=update.effective_chat.id,
            user_id=user_id,
            message=text,
        )
    )
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)


async def poll_jules(application: Application) -> None:
    rt: BotRuntime = application.bot_data["runtime"]
    if not rt.config.jules_api_key:
        return
    for row in rt.storage.list_watched_sessions():
        session_id = row["session_id"]
        try:
            session = await rt.jules.get_session(session_id)
            state = session.get("state") or row["state"]
            rt.storage.update_session_state(session_id, state=state, url=session.get("url") or "")
            if row.get("task_id"):
                if state == "COMPLETED":
                    rt.storage.update_task(row["task_id"], status="REVIEW")
                elif state == "FAILED":
                    rt.storage.update_task(row["task_id"], status="BLOCKED")

            activities = await rt.jules.list_activities(session_id)
            for activity in sorted(activities, key=lambda item: item.get("createTime", "")):
                activity_id = activity.get("id") or activity.get("name", "").split("/")[-1]
                if not activity_id or not rt.storage.mark_activity_seen(session_id, activity_id):
                    continue
                if row.get("task_id"):
                    rt.storage.add_task_event(
                        row["task_id"],
                        kind="jules_activity",
                        message=activity.get("description") or activity_id,
                        payload={"session_id": session_id, "activity_id": activity_id},
                    )
                await send_to_chat(application.bot, row["chat_id"], f"Jules {session_id}:\n{format_activity(activity)}")

            if state in {"COMPLETED", "FAILED"}:
                await send_to_chat(application.bot, row["chat_id"], "Final status:\n" + format_session(session))
        except Exception:
            logger.exception("Failed to poll Jules session %s", session_id)


async def poll_loop(application: Application) -> None:
    rt: BotRuntime = application.bot_data["runtime"]
    while True:
        await poll_jules(application)
        await asyncio.sleep(rt.config.poll_interval_seconds)


async def post_init(application: Application) -> None:
    rt: BotRuntime = application.bot_data["runtime"]
    rt.poll_task = asyncio.create_task(poll_loop(application))


async def post_shutdown(application: Application) -> None:
    await application.bot_data["runtime"].close()


def build_application(config: Config) -> Application:
    app = (
        Application.builder().token(config.telegram_bot_token).post_init(post_init).post_shutdown(post_shutdown).build()
    )
    app.bot_data["runtime"] = BotRuntime(config)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("overview", overview))
    app.add_handler(CommandHandler("policy", policy))
    app.add_handler(CommandHandler("codex_check", codex_check))
    app.add_handler(CommandHandler("codex_reset", codex_reset))
    app.add_handler(CommandHandler("git_status", git_status))
    app.add_handler(CommandHandler("task", task))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("task_status", task_status))
    app.add_handler(CommandHandler("delegate_task", delegate_task))
    app.add_handler(CommandHandler("gemini_check", gemini_check))
    app.add_handler(CommandHandler("gemini_task", gemini_task))
    app.add_handler(CommandHandler("gemini_review", gemini_review))
    app.add_handler(CommandHandler("commit_task", commit_task))
    app.add_handler(CommandHandler("push", push))
    app.add_handler(CommandHandler("pr_task", pr_task))
    app.add_handler(CommandHandler("sources", sources))
    app.add_handler(CommandHandler("delegate", delegate))
    app.add_handler(CommandHandler("confirm_delegate", confirm_delegate))
    app.add_handler(CommandHandler("sessions", sessions))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("say", say))
    app.add_handler(CommandHandler("watch", watch))
    app.add_handler(CommandHandler("unwatch", unwatch))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, natural_message))
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = Config.from_env()
    app = build_application(config)
    logger.info("Starting Jules Telegram Orchestrator")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
