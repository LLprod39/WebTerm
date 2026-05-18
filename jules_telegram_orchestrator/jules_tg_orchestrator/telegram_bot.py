from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import replace
from functools import wraps
from pathlib import Path

from telegram import Bot, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.error import BadRequest, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from jules_tg_orchestrator.codex_cli import CodexCli, CodexCliError
from jules_tg_orchestrator.config import Config
from jules_tg_orchestrator.coordinator import Coordinator, DelegationDraft
from jules_tg_orchestrator.formatting import (
    bullet_lines,
    compact,
    first_change_set_patch,
    first_pull_request_url,
    format_activity,
    format_agent_run,
    format_chief_run,
    format_pending_plan,
    format_session,
    format_source,
    format_task,
    format_task_event,
    split_message,
    summarize_session_outputs,
)
from jules_tg_orchestrator.gemini_cli import GeminiCli, GeminiCliError
from jules_tg_orchestrator.git_ops import GitOps, GitOpsError
from jules_tg_orchestrator.jules_client import JulesApiError, JulesClient
from jules_tg_orchestrator.policy import AutonomyPolicy
from jules_tg_orchestrator.storage import Storage

logger = logging.getLogger(__name__)
CODEX_CHIEF_SESSION_KEY = "codex_chief_session_id"
JULES_SOURCE_KEY_PREFIX = "jules_source_choice:"
JULES_BRANCH_KEY_PREFIX = "jules_branch_choice:"
JULES_AWAITING_BRANCH_PREFIX = "jules_awaiting_branch:"
ORCHESTRATOR_KEY = "active_orchestrator"

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["Статус", "Задачи", "Git"],
        ["Codex", "Gemini", "Jules"],
        ["Policy", "Оркестратор", "Новый чат"],
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


async def send_inline_text(update: Update, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    if not update.effective_chat:
        return
    await update.effective_chat.send_message(text, disable_web_page_preview=True, reply_markup=reply_markup)


async def safe_edit_message_text(
    bot: Bot,
    *,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    try:
        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup)
        return True
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            return True
        logger.info("Telegram message edit failed for %s/%s: %s", chat_id, message_id, exc)
        return False


async def edit_or_send_message_text(
    bot: Bot,
    *,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    fallback_reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = MAIN_KEYBOARD,
) -> None:
    if await safe_edit_message_text(
        bot,
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        reply_markup=reply_markup,
    ):
        return
    for chunk in split_message(text):
        await bot.send_message(chat_id=chat_id, text=chunk, disable_web_page_preview=True, reply_markup=fallback_reply_markup)


async def safe_query_edit_text(
    query: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            return
        logger.info("Telegram callback edit failed: %s", exc)
        if query.message:
            await query.message.reply_text(text, reply_markup=reply_markup or MAIN_KEYBOARD)


async def keep_typing(bot: Bot, chat_id: int, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        with contextlib.suppress(TelegramError):
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4)
        except TimeoutError:
            continue


async def animate_status_message(bot: Bot, chat_id: int, message_id: int, run_id: int, stop_event: asyncio.Event) -> None:
    frames = ["Codex думает.", "Codex думает..", "Codex думает..."]
    index = 0
    while not stop_event.is_set():
        text = f"{frames[index % len(frames)]}\nRun #{run_id}"
        await safe_edit_message_text(bot, chat_id=chat_id, message_id=message_id, text=text)
        index += 1
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=3)
        except TimeoutError:
            continue


async def animate_plan_message(bot: Bot, chat_id: int, message_id: int, stop_event: asyncio.Event) -> None:
    frames = ["Готовлю план.", "Готовлю план..", "Готовлю план..."]
    index = 0
    while not stop_event.is_set():
        await safe_edit_message_text(bot, chat_id=chat_id, message_id=message_id, text=frames[index % len(frames)])
        index += 1
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=3)
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
                f"Active orchestrator: {_get_orchestrator(rt).upper()}",
                f"Codex chief enabled: {rt.config.codex_chief_enabled}",
                f"Gemini CLI enabled: {rt.config.gemini_cli_enabled}",
                f"Plan approval required: {rt.config.jules_require_plan_approval}",
                f"Auto-create PR: {rt.config.jules_auto_create_pr}",
                f"Auto-sync local: {rt.config.jules_auto_sync_local}",
                f"Auto-pull local: {rt.config.jules_auto_pull_local}",
                f"Auto-commit local: {rt.config.jules_auto_commit_local}",
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


def _jules_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Выбрать source", callback_data="jules:list_sources")],
            [InlineKeyboardButton("Выбрать branch", callback_data="jules:list_branches")],
            [InlineKeyboardButton("Ввести branch", callback_data="jules:manual_branch")],
            [InlineKeyboardButton("Сессии Jules", callback_data="jules:sessions")],
            [InlineKeyboardButton("Обновить", callback_data="jules:menu")],
        ]
    )


def _plan_approval_markup(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Одобрить", callback_data=f"plan:approve:{plan_id}"),
                InlineKeyboardButton("Отклонить", callback_data=f"plan:reject:{plan_id}"),
            ],
            [InlineKeyboardButton("Статус", callback_data="chief:status")],
            [InlineKeyboardButton("Все задачи", callback_data="tasks:list")],
        ]
    )


def _plan_detail_markup(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Назад к задачам", callback_data="tasks:list")],
        ]
    )


def _task_list_markup(tasks_rows: list[dict], plan_rows: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for plan in plan_rows[:8]:
        rows.append(
            [
                InlineKeyboardButton(
                    f"План #{plan['plan_id']} {plan['status']}",
                    callback_data=f"plan:open:{plan['plan_id']}",
                )
            ]
        )
    for task_row in tasks_rows[:12]:
        rows.append(
            [
                InlineKeyboardButton(
                    f"#{task_row['task_id']} {task_row['status']}: {compact(task_row['title'], max_len=34)}",
                    callback_data=f"task:open:{task_row['task_id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton("Обновить список", callback_data="tasks:list")])
    return InlineKeyboardMarkup(rows)


def _task_actions_markup(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Обновить статус", callback_data=f"task:refresh:{task_id}"),
                InlineKeyboardButton("Sync local", callback_data=f"task:sync:{task_id}"),
            ],
            [InlineKeyboardButton("Спросить Codex", callback_data=f"task:ask_codex:{task_id}")],
            [
                InlineKeyboardButton("Передать Jules", callback_data=f"task:jules:{task_id}"),
                InlineKeyboardButton("Передать Gemini", callback_data=f"task:gemini:{task_id}"),
            ],
            [
                InlineKeyboardButton("Gemini review", callback_data=f"task:gemini_review:{task_id}"),
                InlineKeyboardButton("Отменить", callback_data=f"task:cancel:{task_id}"),
            ],
            [InlineKeyboardButton("Назад к задачам", callback_data="tasks:list")],
        ]
    )


def _task_cancel_markup(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Да, отменить задачу", callback_data=f"task:cancel_confirm:{task_id}")],
            [InlineKeyboardButton("Назад к задаче", callback_data=f"task:open:{task_id}")],
        ]
    )



def _orchestrator_markup(current: str) -> InlineKeyboardMarkup:
    codex_label = "Codex" + (" (активен)" if current == "codex" else "")
    gemini_label = "Gemini CLI" + (" (активен)" if current == "gemini" else "")
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(codex_label, callback_data="orch:codex")],
            [InlineKeyboardButton(gemini_label, callback_data="orch:gemini")],
        ]
    )


def _get_orchestrator(rt: BotRuntime) -> str:
    stored = rt.storage.get_state(ORCHESTRATOR_KEY)
    if stored in ("codex", "gemini"):
        return stored
    return rt.config.default_orchestrator


def _set_orchestrator(rt: BotRuntime, value: str) -> None:
    if value in ("codex", "gemini"):
        rt.storage.set_state(ORCHESTRATOR_KEY, value)


def _overview_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Задачи и планы", callback_data="tasks:list"),
                InlineKeyboardButton("Jules", callback_data="jules:menu"),
            ],
            [InlineKeyboardButton("Обновить статус", callback_data="chief:status")],
        ]
    )


def _source_repo_label(source: dict) -> str:
    repo = source.get("githubRepo") or {}
    owner = repo.get("owner", "?")
    name = repo.get("repo", "?")
    branch = JulesClient.source_default_branch(source)
    return f"{owner}/{name}" + (f" default={branch}" if branch else "")


async def _send_jules_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    _require_jules(rt)
    text = "\n".join(
        [
            "Jules",
            f"Default source: {rt.config.jules_default_source or 'not set'}",
            f"Default branch: {rt.config.jules_default_branch}",
        ]
    )
    await send_inline_text(update, text, _jules_menu_markup())


async def _send_jules_source_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    _require_jules(rt)
    items = await rt.jules.list_sources()
    rows: list[list[InlineKeyboardButton]] = []
    rt.storage.delete_state(JULES_SOURCE_KEY_PREFIX + "count")
    for index, source in enumerate(items[:40], start=1):
        state_key = f"{JULES_SOURCE_KEY_PREFIX}{index}"
        branch = rt.config.jules_default_branch or JulesClient.source_default_branch(source)
        rt.storage.set_state(state_key, f"{source.get('name', '')}|{branch}")
        rows.append([InlineKeyboardButton(_source_repo_label(source), callback_data=f"jules:select:{index}")])
    rt.storage.set_state(JULES_SOURCE_KEY_PREFIX + "count", str(len(rows)))
    rows.append([InlineKeyboardButton("Назад", callback_data="jules:menu")])
    await send_inline_text(update, "Выбери Jules source для дефолта:", InlineKeyboardMarkup(rows))


def _branch_choice_rows(rt: BotRuntime) -> list[list[InlineKeyboardButton]]:
    candidates: list[str] = []
    for branch in [rt.config.jules_default_branch, rt.git.status().branch, "test", "main", "master"]:
        if branch and branch != "(detached)" and branch not in candidates:
            candidates.append(branch)
    with contextlib.suppress(Exception):
        for branch in rt.git.list_branches():
            if branch not in candidates:
                candidates.append(branch)

    rows: list[list[InlineKeyboardButton]] = []
    for index, branch in enumerate(candidates[:30], start=1):
        rt.storage.set_state(f"{JULES_BRANCH_KEY_PREFIX}{index}", branch)
        label = f"{branch} (сейчас)" if branch == rt.config.jules_default_branch else branch
        rows.append([InlineKeyboardButton(label, callback_data=f"jules:branch:{index}")])
    rows.append([InlineKeyboardButton("Ввести вручную", callback_data="jules:manual_branch")])
    rows.append([InlineKeyboardButton("Назад", callback_data="jules:menu")])
    return rows


async def _send_jules_branch_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rt = runtime(context)
    if not update.effective_chat:
        return
    await update.effective_chat.send_message(
        "Выбери default branch для Jules:",
        reply_markup=InlineKeyboardMarkup(_branch_choice_rows(rt)),
    )


def _task_title(description: str) -> str:
    title = " ".join(description.split())
    if len(title) <= 80:
        return title or "Project task"
    return title[:79].rstrip() + "..."


def _update_env_value(key: str, value: str) -> None:
    path = Path("C:/WebTrerm/jules_telegram_orchestrator/.env")
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    if re.search(rf"(?m)^{re.escape(key)}=", content):
        content = re.sub(rf"(?m)^{re.escape(key)}=.*$", f"{key}={value}", content)
    else:
        content = content.rstrip() + f"\n{key}={value}\n"
    path.write_text(content, encoding="utf-8")


def _apply_jules_default(rt: BotRuntime, *, source: str, branch: str) -> None:
    rt.config = replace(rt.config, jules_default_source=source, jules_default_branch=branch)
    rt.coordinator = Coordinator(default_source=source, default_branch=branch)
    _update_env_value("JULES_DEFAULT_SOURCE", source)
    _update_env_value("JULES_DEFAULT_BRANCH", branch)


def _apply_jules_branch(rt: BotRuntime, branch: str) -> None:
    branch = branch.strip()
    if not branch:
        return
    rt.config = replace(rt.config, jules_default_branch=branch)
    rt.coordinator = Coordinator(default_source=rt.config.jules_default_source, default_branch=branch)
    _update_env_value("JULES_DEFAULT_BRANCH", branch)


def _render_overview(rt: BotRuntime) -> str:
    git_status = rt.git.status()
    session_id = rt.storage.get_state(CODEX_CHIEF_SESSION_KEY, default="not created yet")
    active_runs = rt.storage.list_active_chief_runs()
    recent_runs = rt.storage.list_chief_runs(limit=3)
    pending_plans = [plan for plan in rt.storage.list_pending_plans(limit=5) if plan["status"] == "PENDING"]
    task_rows = rt.storage.list_tasks(limit=5)
    tasks_text = "\n".join(f"#{row['task_id']} {row['status']} - {row['title']}" for row in task_rows)
    if not tasks_text:
        tasks_text = "No tasks yet"
    if active_runs:
        codex_runs_text = "\n".join(format_chief_run(run) for run in active_runs)
    elif recent_runs:
        codex_runs_text = "\n".join(format_chief_run(run) for run in recent_runs)
    else:
        codex_runs_text = "No Codex runs yet"
    plans_text = "\n".join(format_pending_plan(plan) for plan in pending_plans) if pending_plans else "No pending plans"
    return "\n".join(
        [
            "AI Chief Orchestrator",
            f"Codex session: {session_id}",
            f"Project: {rt.config.project_root}",
            f"Branch: {git_status.branch}",
            f"Dirty: {git_status.is_dirty}",
            "",
            "Codex runs:",
            codex_runs_text,
            "",
            "Pending plans:",
            plans_text,
            "",
            "Recent tasks:",
            tasks_text,
        ]
    )


def _render_work_items(rt: BotRuntime) -> tuple[str, InlineKeyboardMarkup]:
    plan_rows = rt.storage.list_pending_plans(limit=8)
    task_rows = rt.storage.list_tasks(limit=12)
    pending_plan_rows = [plan for plan in plan_rows if plan["status"] == "PENDING"]
    non_pending_plan_rows = [plan for plan in plan_rows if plan["status"] != "PENDING"]
    lines = ["Рабочие элементы"]
    if pending_plan_rows:
        lines.extend(["", "Ожидают решения:"])
        lines.extend(format_pending_plan(plan) for plan in pending_plan_rows)
    if task_rows:
        lines.extend(["", "Задачи:"])
        lines.extend(f"#{row['task_id']} {row['status']} - {row['title']}" for row in task_rows[:8])
    if not pending_plan_rows and not task_rows:
        lines.extend(["", "Пока нет задач и планов."])
    if non_pending_plan_rows and not pending_plan_rows:
        lines.extend(["", "Последние планы:"])
        lines.extend(format_pending_plan(plan) for plan in non_pending_plan_rows[:3])
    return "\n".join(lines), _task_list_markup(task_rows, pending_plan_rows or plan_rows[:4])


def _render_plan_detail(plan: dict) -> str:
    return "\n".join(
        [
            f"План #{plan['plan_id']}: {plan['status']}",
            f"Создан: {plan['created_at']}",
            "",
            "Исходное сообщение:",
            compact(plan.get("message"), max_len=900),
            "",
            "План работы:",
            compact(plan.get("plan_text"), max_len=2400),
        ]
    )


def _render_task_detail(rt: BotRuntime, task_row: dict) -> str:
    task_id = int(task_row["task_id"])
    events = rt.storage.list_task_events(task_id, limit=8)
    runs = rt.storage.list_task_agent_runs(task_id, limit=6)
    sessions_rows = rt.storage.list_task_sessions(task_id, limit=6)
    run_text = "\n".join(format_agent_run(run) for run in runs) if runs else "Нет agent runs"
    session_lines = []
    for row in sessions_rows:
        suffix = f" - {row['url']}" if row.get("url") else ""
        session_lines.append(f"{row['session_id']}: {row['state']}{suffix}")
    session_text = "\n".join(session_lines) if session_lines else "Нет Jules sessions"
    event_text = "\n".join(format_task_event(event) for event in events) if events else "Нет событий"
    return "\n".join(
        [
            format_task(task_row),
            "",
            "Jules:",
            session_text,
            "",
            "Agent runs:",
            run_text,
            "",
            "Последние события:",
            event_text,
        ]
    )


def _jules_task_status(session_states: list[str]) -> str:
    states = {state.upper() for state in session_states if state}
    if not states:
        return ""
    if "FAILED" in states:
        return "BLOCKED"
    if "AWAITING_USER_FEEDBACK" in states:
        return "NEEDS_INPUT"
    if "AWAITING_PLAN_APPROVAL" in states:
        return "PLAN_REVIEW"
    if states & {"IN_PROGRESS", "PLANNING", "QUEUED", "PAUSED"}:
        return "JULES_RUNNING"
    if states <= {"COMPLETED", "DELETED"}:
        return "REVIEW"
    return ""


async def _auto_approve_jules_plan_if_needed(
    rt: BotRuntime,
    *,
    session_id: str,
    state: str,
    task_id: int | None = None,
) -> str:
    if state != "AWAITING_PLAN_APPROVAL" or rt.config.jules_require_plan_approval:
        return state
    await rt.jules.approve_plan(session_id)
    if task_id:
        rt.storage.add_task_event(
            task_id,
            kind="jules_plan_auto_approved",
            message=f"Auto-approved Jules plan for session {session_id}",
            payload={"session_id": session_id},
        )
    return "IN_PROGRESS"


def _task_codex_inquiry_prompt(rt: BotRuntime, task_row: dict) -> str:
    task_id = int(task_row["task_id"])
    events = rt.storage.list_task_events(task_id, limit=12)
    runs = rt.storage.list_task_agent_runs(task_id, limit=10)
    sessions_rows = rt.storage.list_task_sessions(task_id, limit=10)
    return "\n".join(
        [
            f"Пользователь просит проверить и объяснить статус задачи #{task_id}.",
            "Это read-only запрос статуса: не меняй файлы, не делегируй новую работу, не коммить, не пушь, не отменяй и не одобряй планы без отдельного подтверждения.",
            "Если локального контекста недостаточно, можешь проверить доступные CLI/API/MCP источники, но итог верни коротко по-русски для Telegram.",
            f"Bot database path: {rt.config.database_path}",
            "",
            "Задача:",
            format_task(task_row),
            "",
            "Связанные Jules sessions:",
            "\n".join(f"{row['session_id']}: {row['state']} {row.get('url') or ''}".strip() for row in sessions_rows)
            or "Нет Jules sessions",
            "",
            "Agent runs:",
            "\n".join(format_agent_run(run) for run in runs) or "Нет agent runs",
            "",
            "Последние события:",
            "\n".join(format_task_event(event) for event in events) or "Нет событий",
        ]
    )


def _parse_task_reference(text: str) -> int | None:
    match = re.search(r"(?:задач[аиуей]?|task)\s*#?\s*(\d+)", text.casefold())
    if not match:
        return None
    return int(match.group(1))


def _looks_like_codex_task_question(text: str) -> bool:
    lowered = text.casefold()
    return "codex" in lowered or "кодекс" in lowered or "спрос" in lowered


def _plan_targets_jules(plan: dict) -> bool:
    text = f"{plan.get('message', '')}\n{plan.get('plan_text', '')}".casefold()
    return "jules" in text or "джул" in text


def _extract_worker_prompt(plan_text: str, *, worker: str = "Jules") -> str:
    pattern = rf"(?:prompt|задач[аи]|текст)[^\n]*{re.escape(worker)}[^\n]*:\s*```(?:text)?\s*(.*?)```"
    match = re.search(pattern, plan_text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    fenced = re.findall(r"```(?:text)?\s*(.*?)```", plan_text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced[0].strip()
    return plan_text.strip()


@restricted
async def overview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        await update.effective_chat.send_message(
            _render_overview(runtime(context)),
            disable_web_page_preview=True,
            reply_markup=_overview_markup(),
        )


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
    if not update.effective_chat:
        return
    text, markup = _render_work_items(rt)
    await update.effective_chat.send_message(text, disable_web_page_preview=True, reply_markup=markup)


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
    if update.effective_chat:
        await update.effective_chat.send_message(
            _render_task_detail(rt, task_row),
            disable_web_page_preview=True,
            reply_markup=_task_actions_markup(task_row["task_id"]),
        )


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
            "Use any MCP/tools/skills available to Gemini CLI if they are configured and relevant.",
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
            "Use any MCP/tools/skills available to Gemini CLI if they are configured and relevant.",
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
        task_row = rt.storage.get_task(task_id)
        if task_row and task_row["status"] == "CANCELLED":
            rt.storage.update_agent_run(run_id, status="CANCELLED", summary="Task was cancelled before Gemini finished")
            rt.storage.add_task_event(task_id, kind="gemini_cancelled", message=f"Gemini run #{run_id} finished after cancellation")
            return
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


async def _start_gemini_task_run(
    application: Application,
    *,
    chat_id: int,
    task_id: int,
    review: bool = False,
) -> str:
    rt: BotRuntime = application.bot_data["runtime"]
    _require_gemini(rt)
    task_row = rt.storage.get_task(task_id)
    if not task_row:
        return f"Task #{task_id} not found."
    if task_row["status"] == "CANCELLED":
        return f"Task #{task_id} is cancelled."
    agent_kind = "gemini_cli_review" if review else "gemini_cli"
    run_id = rt.storage.create_agent_run(task_id=task_row["task_id"], agent_kind=agent_kind)
    if review:
        rt.storage.add_task_event(task_row["task_id"], kind="gemini_review_started", message=f"Started Gemini review #{run_id}")
        prompt = _build_gemini_review_prompt(task_row, rt.git.diff_for_review())
    else:
        rt.storage.update_task(task_row["task_id"], status="GEMINI_RUNNING")
        rt.storage.add_task_event(task_row["task_id"], kind="gemini_started", message=f"Started Gemini run #{run_id}")
        prompt = _build_gemini_task_prompt(task_row)
    application.create_task(
        _execute_gemini_run(
            application,
            chat_id=chat_id,
            task_id=task_row["task_id"],
            run_id=run_id,
            prompt=prompt,
            allow_edits=not review,
        )
    )
    action = "Gemini review" if review else "Gemini CLI run"
    return f"Started {action} #{run_id} for task #{task_row['task_id']}."


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
    message = await _start_gemini_task_run(
        context.application,
        chat_id=update.effective_chat.id,
        task_id=int(context.args[0]),
    )
    await send_text(update, message)


@restricted
async def gemini_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await send_text(update, "Usage: /gemini_review <task_id>")
        return
    if not update.effective_chat:
        return
    message = await _start_gemini_task_run(
        context.application,
        chat_id=update.effective_chat.id,
        task_id=int(context.args[0]),
        review=True,
    )
    await send_text(update, message)


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
    message = await _create_jules_session_for_chat(rt, draft, chat_id=update.effective_chat.id, task_id=task_id)
    await send_text(update, message)


async def _create_jules_session_for_chat(
    rt: BotRuntime,
    draft: DelegationDraft,
    *,
    chat_id: int,
    task_id: int | None = None,
) -> str:
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
        chat_id=chat_id,
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
    rt.storage.clear_draft(chat_id)
    return "Delegated to Jules:\n" + format_session(session)


async def _approve_jules_plan(
    application: Application,
    *,
    plan: dict,
) -> str:
    rt: BotRuntime = application.bot_data["runtime"]
    prompt = _extract_worker_prompt(plan["plan_text"])
    title = _task_title(plan["message"])
    task_id = rt.storage.create_task(
        chat_id=plan["chat_id"],
        title=title,
        description=prompt,
        project_root=str(rt.config.project_root),
        source=rt.config.jules_default_source,
        branch=rt.config.jules_default_branch,
        status="READY",
    )
    rt.storage.add_task_event(
        task_id,
        kind="created_from_plan",
        message=f"Created from approved plan #{plan['plan_id']}",
        payload={"plan_id": plan["plan_id"]},
    )
    draft = rt.coordinator.build_draft(
        prompt,
        source=rt.config.jules_default_source,
        branch=rt.config.jules_default_branch,
        title=title,
    )
    decision = rt.coordinator.evaluate(draft)
    if not decision.ready:
        rt.storage.update_pending_plan(plan["plan_id"], status="APPROVED", task_id=task_id)
        return f"План #{plan['plan_id']} одобрен, создана задача #{task_id}, но Jules пока не запущен:\n{decision.question}"
    message = await _create_jules_session_for_chat(
        rt,
        decision.draft or draft,
        chat_id=plan["chat_id"],
        task_id=task_id,
    )
    rt.storage.update_pending_plan(plan["plan_id"], status="APPROVED", task_id=task_id)
    return f"План #{plan['plan_id']} одобрен. Создана задача #{task_id} и Jules session.\n\n{message}"


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


async def _refresh_task_status(rt: BotRuntime, task_id: int) -> str:
    task_row = rt.storage.get_task(task_id)
    if not task_row:
        return f"Task #{task_id} not found."
    sessions_rows = rt.storage.list_task_sessions(task_id)
    refreshed_states: list[str] = []
    if sessions_rows:
        _require_jules(rt)
    for row in sessions_rows:
        session = await rt.jules.get_session(row["session_id"])
        session_id = session.get("id") or row["session_id"]
        state = session.get("state") or row["state"]
        state = await _auto_approve_jules_plan_if_needed(rt, session_id=session_id, state=state, task_id=task_id)
        refreshed_states.append(state)
        rt.storage.update_session_state(session_id, state=state, url=session.get("url") or "")
        activities = await rt.jules.list_activities(session_id)
        for activity in sorted(activities, key=lambda item: item.get("createTime", "")):
            activity_id = activity.get("id") or activity.get("name", "").split("/")[-1]
            if not activity_id or not rt.storage.mark_activity_seen(session_id, activity_id):
                continue
            rt.storage.add_task_event(
                task_id,
                kind="jules_activity",
                message=compact(format_activity(activity), max_len=900),
                payload={"session_id": session_id, "activity_id": activity_id},
            )
    next_status = _jules_task_status(refreshed_states)
    if next_status and task_row["status"] != "CANCELLED":
        rt.storage.update_task(task_id, status=next_status)
    rt.storage.add_task_event(task_id, kind="status_refreshed", message="Task status refreshed from linked agents")
    return f"Task #{task_id} status refreshed."


async def _cancel_task(rt: BotRuntime, task_id: int) -> str:
    task_row = rt.storage.get_task(task_id)
    if not task_row:
        return f"Task #{task_id} not found."
    rt.storage.update_task(task_id, status="CANCELLED")
    rt.storage.cancel_running_agent_runs(task_id)
    sessions_rows = rt.storage.list_task_sessions(task_id)
    deleted_sessions: list[str] = []
    failed_sessions: list[str] = []
    for row in sessions_rows:
        session_id = row["session_id"]
        if row["state"] in {"COMPLETED", "FAILED", "DELETED"}:
            continue
        if not rt.config.jules_api_key:
            failed_sessions.append(f"{session_id}: no JULES_API_KEY")
            continue
        try:
            await rt.jules.delete_session(session_id)
            rt.storage.update_session_state(session_id, state="DELETED")
            deleted_sessions.append(session_id)
        except Exception as exc:
            logger.exception("Could not delete Jules session %s during cancellation", session_id)
            failed_sessions.append(f"{session_id}: {exc}")
    rt.storage.unwatch_task_sessions(task_id)
    rt.storage.add_task_event(
        task_id,
        kind="cancelled",
        message="Task cancelled by user",
        payload={"deleted_jules_sessions": deleted_sessions, "failed_jules_sessions": failed_sessions},
    )
    lines = [f"Task #{task_id} cancelled."]
    if deleted_sessions:
        lines.append("Deleted Jules sessions: " + ", ".join(deleted_sessions))
    if failed_sessions:
        lines.append("Could not delete Jules sessions: " + "; ".join(failed_sessions))
    return "\n".join(lines)


async def _sync_completed_jules_session(
    application: Application,
    *,
    row: dict,
    session: dict,
    force: bool = False,
) -> str:
    rt: BotRuntime = application.bot_data["runtime"]
    session_id = row["session_id"]
    task_id = row.get("task_id")
    sync_key = f"jules_local_sync:{session_id}"
    if force:
        rt.storage.delete_state(sync_key)
    elif rt.storage.get_state(sync_key):
        return ""
    if (session.get("state") or row["state"]) != "COMPLETED":
        return ""
    if not rt.config.jules_auto_sync_local:
        return ""

    output_summary = summarize_session_outputs(session)
    try:
        pr_url = first_pull_request_url(session)
        if pr_url and rt.config.jules_auto_pull_local:
            branch = rt.git.checkout_pull_request(pr_url)
            result = f"Checked out Jules PR locally on branch `{branch}`."
        else:
            patch, commit_message = first_change_set_patch(session)
            if not patch:
                result = "Jules completed, but API did not return PR or patch outputs for local sync."
            else:
                result = rt.git.apply_patch_and_commit(
                    patch,
                    message=commit_message,
                    commit=rt.config.jules_auto_commit_local,
                )
        rt.storage.set_state(sync_key, "DONE")
        if task_id:
            rt.storage.add_task_event(
                task_id,
                kind="local_sync_completed",
                message=result,
                payload={"session_id": session_id},
            )
        lines = ["Локальный sync Jules выполнен.", result]
        if output_summary:
            lines.extend(["", output_summary])
        return "\n".join(lines)
    except GitOpsError as exc:
        message = str(exc)
        rt.storage.set_state(sync_key, f"BLOCKED: {message}")
        if task_id:
            rt.storage.add_task_event(
                task_id,
                kind="local_sync_blocked",
                message=message,
                payload={"session_id": session_id},
            )
        lines = [
            "Локальный sync Jules не выполнен.",
            message,
            "",
            "Результат Jules остался в cloud/session. Локально ничего не применялось.",
        ]
        if output_summary:
            lines.extend(["", output_summary])
        return "\n".join(lines)


async def _sync_task_jules_sessions(
    application: Application,
    *,
    task_id: int,
    force: bool = False,
) -> str:
    rt: BotRuntime = application.bot_data["runtime"]
    sessions_rows = rt.storage.list_task_sessions(task_id, limit=10)
    if not sessions_rows:
        return f"У задачи #{task_id} нет Jules sessions."
    messages: list[str] = []
    for row in sessions_rows:
        session = await rt.jules.get_session(row["session_id"])
        state = session.get("state") or row["state"]
        rt.storage.update_session_state(row["session_id"], state=state, url=session.get("url") or row["url"])
        if state != "COMPLETED":
            messages.append(f"{row['session_id']}: пока {state}, sync будет после COMPLETED.")
            continue
        message = await _sync_completed_jules_session(application, row=row, session=session, force=force)
        messages.append(message or f"{row['session_id']}: local sync уже обработан.")
    return "\n\n".join(messages)


async def _start_codex_task_inquiry(
    application: Application,
    *,
    chat_id: int,
    user_id: int,
    task_id: int,
) -> str:
    rt: BotRuntime = application.bot_data["runtime"]
    task_row = rt.storage.get_task(task_id)
    if not task_row:
        return f"Task #{task_id} not found."
    if rt.storage.list_task_sessions(task_id):
        try:
            await _refresh_task_status(rt, task_id)
            task_row = rt.storage.get_task(task_id) or task_row
        except Exception as exc:
            logger.info("Could not refresh task %s before Codex inquiry: %s", task_id, exc)
            rt.storage.add_task_event(task_id, kind="status_refresh_failed", message=str(exc))
    status_message = await application.bot.send_message(chat_id=chat_id, text=f"Codex смотрит задачу #{task_id}...")
    prompt = _task_codex_inquiry_prompt(rt, task_row)
    run_id = rt.storage.create_chief_run(
        chat_id=chat_id,
        user_id=user_id,
        message=prompt,
        status_message_id=status_message.message_id,
        thread_id=rt.storage.get_state(CODEX_CHIEF_SESSION_KEY),
    )
    rt.storage.add_task_event(task_id, kind="codex_inquiry_started", message=f"Started Codex run #{run_id}")
    application.create_task(
        _execute_codex_chief(
            application,
            chat_id=chat_id,
            user_id=user_id,
            message=prompt,
            run_id=run_id,
            status_message_id=status_message.message_id,
        )
    )
    return f"Запустил Codex run #{run_id} по задаче #{task_id}."


async def animate_gemini_status_message(bot: Bot, chat_id: int, message_id: int, stop_event: asyncio.Event) -> None:
    frames = ["Gemini думает.", "Gemini думает..", "Gemini думает..."]
    index = 0
    while not stop_event.is_set():
        await safe_edit_message_text(bot, chat_id=chat_id, message_id=message_id, text=frames[index % len(frames)])
        index += 1
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=3)
        except TimeoutError:
            continue


def _build_gemini_chief_prompt(telegram_message: str) -> str:
    parts = [
        "You are the chief Gemini project orchestrator for this repository.",
        "The customer is talking to you through Telegram. Answer as the chief coordinator.",
        "Operating model:",
        "1. You are the lead. You think, inspect context, and verify results.",
        "2. You may make edits, fixes, and implementation directly.",
        "3. Report progress and final status in concise Russian suitable for Telegram.",
        "4. If you need user input, ask the user directly in Russian.",
        "Tooling policy:",
        "- Use all tools, context files, and skills available in your Gemini CLI environment.",
        "- Follow AGENTS.md and GEMINI.md instructions if present in the repository.",
        "",
        "Customer message:",
        telegram_message,
    ]
    return "\n".join(parts)


async def _execute_gemini_chief(
    application: Application,
    *,
    chat_id: int,
    user_id: int,
    message: str,
    run_id: int,
    status_message_id: int,
) -> None:
    rt: BotRuntime = application.bot_data["runtime"]
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(application.bot, chat_id, stop_typing))
    status_task = asyncio.create_task(
        animate_gemini_status_message(application.bot, chat_id, status_message_id, stop_typing)
    )
    try:
        prompt = _build_gemini_chief_prompt(message)
        result = await asyncio.to_thread(rt.gemini.run_prompt, prompt, allow_edits=True)
        rt.storage.update_chief_run(
            run_id,
            status="COMPLETED",
            response=result.render(max_len=8000),
            thread_id="",
        )
        await edit_or_send_message_text(
            application.bot,
            chat_id=chat_id,
            message_id=status_message_id,
            text=f"Gemini готов. Run #{run_id}",
        )
        await send_to_chat(application.bot, chat_id, result.render())
    except GeminiCliError as exc:
        logger.exception("Gemini chief run failed")
        rt.storage.update_chief_run(run_id, status="FAILED", error=str(exc))
        await edit_or_send_message_text(
            application.bot,
            chat_id=chat_id,
            message_id=status_message_id,
            text=f"Gemini ошибка. Run #{run_id}",
        )
        await send_to_chat(application.bot, chat_id, f"Gemini chief error: {exc}")
    except Exception as exc:
        logger.exception("Gemini chief run failed")
        rt.storage.update_chief_run(run_id, status="FAILED", error=str(exc))
        await edit_or_send_message_text(
            application.bot,
            chat_id=chat_id,
            message_id=status_message_id,
            text=f"Gemini ошибка. Run #{run_id}",
        )
        await send_to_chat(application.bot, chat_id, f"Gemini chief error: {exc}")
    finally:
        stop_typing.set()
        with contextlib.suppress(asyncio.CancelledError):
            await typing_task
        with contextlib.suppress(asyncio.CancelledError):
            await status_task


async def _execute_codex_chief(
    application: Application,
    *,
    chat_id: int,
    user_id: int,
    message: str,
    run_id: int,
    status_message_id: int,
) -> None:
    rt: BotRuntime = application.bot_data["runtime"]
    session_id = rt.storage.get_state(CODEX_CHIEF_SESSION_KEY)
    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(application.bot, chat_id, stop_typing))
    status_task = asyncio.create_task(
        animate_status_message(application.bot, chat_id, status_message_id, run_id, stop_typing)
    )
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
        rt.storage.update_chief_run(
            run_id,
            status="COMPLETED",
            response=result.render(max_len=8000),
            thread_id=result.thread_id,
        )
        await edit_or_send_message_text(
            application.bot,
            chat_id=chat_id,
            message_id=status_message_id,
            text=f"Codex готов.\nRun #{run_id}",
        )
        await send_to_chat(application.bot, chat_id, result.render())
    except CodexCliError as exc:
        if session_id and "not found" in str(exc).lower():
            rt.storage.delete_state(CODEX_CHIEF_SESSION_KEY)
            rt.storage.update_chief_run(run_id, status="RETRYING", error=str(exc))
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
                rt.storage.update_chief_run(
                    run_id,
                    status="COMPLETED",
                    response=result.render(max_len=8000),
                    thread_id=result.thread_id,
                )
                await edit_or_send_message_text(
                    application.bot,
                    chat_id=chat_id,
                    message_id=status_message_id,
                    text=f"Codex готов.\nRun #{run_id}",
                )
                await send_to_chat(application.bot, chat_id, result.render())
                return
            except Exception as retry_exc:
                logger.exception("Codex chief retry failed")
                rt.storage.update_chief_run(run_id, status="FAILED", error=str(retry_exc))
                await edit_or_send_message_text(
                    application.bot,
                    chat_id=chat_id,
                    message_id=status_message_id,
                    text=f"Codex ошибка.\nRun #{run_id}",
                )
                await send_to_chat(application.bot, chat_id, f"Codex chief error:\n{retry_exc}")
                return
        logger.exception("Codex chief run failed")
        rt.storage.update_chief_run(run_id, status="FAILED", error=str(exc))
        await edit_or_send_message_text(
            application.bot,
            chat_id=chat_id,
            message_id=status_message_id,
            text=f"Codex ошибка.\nRun #{run_id}",
        )
        await send_to_chat(application.bot, chat_id, f"Codex chief error:\n{exc}")
    except Exception as exc:
        logger.exception("Codex chief run failed")
        rt.storage.update_chief_run(run_id, status="FAILED", error=str(exc))
        await edit_or_send_message_text(
            application.bot,
            chat_id=chat_id,
            message_id=status_message_id,
            text=f"Codex ошибка.\nRun #{run_id}",
        )
        await send_to_chat(application.bot, chat_id, f"Codex chief error:\n{exc}")
    finally:
        stop_typing.set()
        with contextlib.suppress(asyncio.CancelledError):
            await typing_task
        with contextlib.suppress(asyncio.CancelledError):
            await status_task


async def _prepare_codex_plan(
    application: Application,
    *,
    chat_id: int,
    user_id: int,
    message: str,
    status_message_id: int,
) -> None:
    rt: BotRuntime = application.bot_data["runtime"]
    stop_event = asyncio.Event()
    typing_task = asyncio.create_task(keep_typing(application.bot, chat_id, stop_event))
    plan_task = asyncio.create_task(animate_plan_message(application.bot, chat_id, status_message_id, stop_event))
    try:
        result = await asyncio.to_thread(rt.codex.build_delegation_plan, message, user_id=user_id, chat_id=chat_id)
        plan_text = result.render(max_len=3200)
        plan_id = rt.storage.create_pending_plan(chat_id=chat_id, user_id=user_id, message=message, plan_text=plan_text)
        await edit_or_send_message_text(
            application.bot,
            chat_id=chat_id,
            message_id=status_message_id,
            text=f"План #{plan_id}\n\n{plan_text}",
            reply_markup=_plan_approval_markup(plan_id),
            fallback_reply_markup=_plan_approval_markup(plan_id),
        )
    except Exception as exc:
        logger.exception("Codex plan preparation failed")
        await edit_or_send_message_text(
            application.bot,
            chat_id=chat_id,
            message_id=status_message_id,
            text=f"Не смог подготовить план:\n{exc}",
        )
    finally:
        stop_event.set()
        with contextlib.suppress(asyncio.CancelledError):
            await typing_task
        with contextlib.suppress(asyncio.CancelledError):
            await plan_task


@restricted
async def natural_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    rt = runtime(context)
    text = update.message.text or ""
    awaiting_branch_key = f"{JULES_AWAITING_BRANCH_PREFIX}{update.effective_chat.id}"
    if rt.storage.get_state(awaiting_branch_key):
        branch = text.strip()
        if not branch or any(char.isspace() for char in branch):
            await send_text(update, "Ветка должна быть одной строкой без пробелов. Например: test")
            return
        _apply_jules_branch(rt, branch)
        rt.storage.delete_state(awaiting_branch_key)
        await update.effective_chat.send_message(
            "\n".join(
                [
                    "Jules branch обновлен.",
                    f"Default source: {rt.config.jules_default_source or 'not set'}",
                    f"Default branch: {rt.config.jules_default_branch}",
                ]
            ),
            reply_markup=_jules_menu_markup(),
        )
        return
    button = text.strip().casefold()
    if button == "статус":
        await overview(update, context)
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
        await _send_jules_menu(update, context)
        return
    if button == "policy":
        await policy(update, context)
        return
    if button == "новый чат":
        await codex_reset(update, context)
        return
    if button == "оркестратор":
        current = _get_orchestrator(rt)
        await send_inline_text(
            update,
            f"Текущий оркестратор: {current.upper()}\nВыбери главного агента для обработки сообщений:",
            _orchestrator_markup(current),
        )
        return
    if task_id := _parse_task_reference(text):
        task_row = rt.storage.get_task(task_id)
        if not task_row:
            await send_text(update, f"Task #{task_id} not found.")
            return
        if _looks_like_codex_task_question(text):
            user_id = update.effective_user.id if update.effective_user else 0
            message = await _start_codex_task_inquiry(
                context.application,
                chat_id=update.effective_chat.id,
                user_id=user_id,
                task_id=task_id,
            )
            await send_text(update, message)
            return
        with contextlib.suppress(Exception):
            await _refresh_task_status(rt, task_id)
            task_row = rt.storage.get_task(task_id) or task_row
        await update.effective_chat.send_message(
            _render_task_detail(rt, task_row),
            disable_web_page_preview=True,
            reply_markup=_task_actions_markup(task_id),
        )
        return
    active_orch = _get_orchestrator(rt)
    user_id = update.effective_user.id if update.effective_user else 0

    if active_orch == "gemini":
        if not rt.config.gemini_cli_enabled:
            await send_text(update, "Gemini CLI отключен. Включи GEMINI_CLI_ENABLED=true или переключи оркестратор.")
            return
        status_message = await update.effective_chat.send_message("Gemini думает...")
        run_id = rt.storage.create_chief_run(
            chat_id=update.effective_chat.id,
            user_id=user_id,
            message=text,
            status_message_id=status_message.message_id,
            thread_id="",
        )
        context.application.create_task(
            _execute_gemini_chief(
                context.application,
                chat_id=update.effective_chat.id,
                user_id=user_id,
                message=text,
                run_id=run_id,
                status_message_id=status_message.message_id,
            )
        )
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        return

    if not rt.config.codex_chief_enabled:
        await send_text(update, "Codex chief adapter is disabled. Enable CODEX_CHIEF_ENABLED=true.")
        return
    if rt.config.codex_require_plan_approval:
        status_message = await update.effective_chat.send_message("Готовлю план.")
        context.application.create_task(
            _prepare_codex_plan(
                context.application,
                chat_id=update.effective_chat.id,
                user_id=user_id,
                message=text,
                status_message_id=status_message.message_id,
            )
        )
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        return

    status_message = await update.effective_chat.send_message("Codex думает.\nRun создается...")
    run_id = rt.storage.create_chief_run(
        chat_id=update.effective_chat.id,
        user_id=user_id,
        message=text,
        status_message_id=status_message.message_id,
        thread_id=rt.storage.get_state(CODEX_CHIEF_SESSION_KEY),
    )
    await safe_edit_message_text(
        context.bot,
        chat_id=update.effective_chat.id,
        message_id=status_message.message_id,
        text=f"Codex думает.\nRun #{run_id}",
    )
    context.application.create_task(
        _execute_codex_chief(
            context.application,
            chat_id=update.effective_chat.id,
            user_id=user_id,
            message=text,
            run_id=run_id,
            status_message_id=status_message.message_id,
        )
    )
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
@restricted
async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    rt = runtime(context)
    data = query.data or ""
    if data.startswith("orch:"):
        choice = data.split(":", 1)[1]
        _set_orchestrator(rt, choice)
        label = "Codex CLI" if choice == "codex" else "Gemini CLI"
        await safe_query_edit_text(
            query,
            f"Оркестратор переключен на {label}.\nВсе новые сообщения будут обрабатываться через {label}.",
            reply_markup=_orchestrator_markup(choice),
        )
        return
    if data == "chief:status":
        await safe_query_edit_text(query, _render_overview(rt), reply_markup=_overview_markup())
        return
    if data == "tasks:list":
        text, markup = _render_work_items(rt)
        await safe_query_edit_text(query, text, reply_markup=markup)
        return
    if data.startswith("plan:open:"):
        plan_id = int(data.rsplit(":", 1)[-1])
        plan = rt.storage.get_pending_plan(plan_id)
        if not plan:
            await safe_query_edit_text(query, "План не найден.")
            return
        markup = _plan_approval_markup(plan_id) if plan["status"] == "PENDING" else _plan_detail_markup(plan_id)
        await safe_query_edit_text(query, _render_plan_detail(plan), reply_markup=markup)
        return
    if data.startswith("plan:approve:"):
        plan_id = int(data.rsplit(":", 1)[-1])
        plan = rt.storage.get_pending_plan(plan_id)
        if not plan:
            await safe_query_edit_text(query, "План не найден.")
            return
        if plan["status"] != "PENDING":
            await safe_query_edit_text(query, f"План #{plan_id} уже в статусе {plan['status']}.")
            return
        if _plan_targets_jules(plan):
            await safe_query_edit_text(query, f"План #{plan_id} одобрен. Создаю задачу и Jules session...")
            try:
                message = await _approve_jules_plan(context.application, plan=plan)
            except Exception as exc:
                logger.exception("Jules plan approval failed")
                rt.storage.update_pending_plan(plan_id, status="FAILED")
                await safe_query_edit_text(query, f"Не смог создать Jules session по плану #{plan_id}:\n{exc}")
                return
            text, markup = _render_work_items(rt)
            await safe_query_edit_text(query, message + "\n\n" + text, reply_markup=markup)
            return
        status_message = await query.message.reply_text(f"Codex думает.\nRun создается по плану #{plan_id}")
        run_id = rt.storage.create_chief_run(
            chat_id=plan["chat_id"],
            user_id=plan["user_id"],
            message=(
                "План был одобрен пользователем. Выполни работу по этому плану.\n\n"
                f"Исходное сообщение:\n{plan['message']}\n\n"
                f"Одобренный план:\n{plan['plan_text']}"
            ),
            status_message_id=status_message.message_id,
            thread_id=rt.storage.get_state(CODEX_CHIEF_SESSION_KEY),
        )
        rt.storage.update_pending_plan(plan_id, status="APPROVED", chief_run_id=run_id)
        await safe_query_edit_text(query, f"План #{plan_id} одобрен. Запущен Codex run #{run_id}.")
        context.application.create_task(
            _execute_codex_chief(
                context.application,
                chat_id=plan["chat_id"],
                user_id=plan["user_id"],
                message=(
                    "План был одобрен пользователем. Выполни работу по этому плану.\n\n"
                    f"Исходное сообщение:\n{plan['message']}\n\n"
                    f"Одобренный план:\n{plan['plan_text']}"
                ),
                run_id=run_id,
                status_message_id=status_message.message_id,
            )
        )
        return
    if data.startswith("plan:reject:"):
        plan_id = int(data.rsplit(":", 1)[-1])
        rt.storage.update_pending_plan(plan_id, status="REJECTED")
        await safe_query_edit_text(query, f"План #{plan_id} отклонен.")
        return
    if data.startswith("task:open:"):
        task_id = int(data.rsplit(":", 1)[-1])
        task_row = rt.storage.get_task(task_id)
        if not task_row:
            await safe_query_edit_text(query, f"Task #{task_id} not found.", reply_markup=_task_list_markup([], []))
            return
        await safe_query_edit_text(query, _render_task_detail(rt, task_row), reply_markup=_task_actions_markup(task_id))
        return
    if data.startswith("task:refresh:"):
        task_id = int(data.rsplit(":", 1)[-1])
        await safe_query_edit_text(query, f"Обновляю статус задачи #{task_id}...")
        try:
            message = await _refresh_task_status(rt, task_id)
        except Exception as exc:
            logger.exception("Task %s refresh failed", task_id)
            message = f"Не смог обновить статус задачи #{task_id}:\n{exc}"
        task_row = rt.storage.get_task(task_id)
        if not task_row:
            await safe_query_edit_text(query, message)
            return
        await safe_query_edit_text(
            query,
            message + "\n\n" + _render_task_detail(rt, task_row),
            reply_markup=_task_actions_markup(task_id),
        )
        return
    if data.startswith("task:sync:"):
        task_id = int(data.rsplit(":", 1)[-1])
        await safe_query_edit_text(query, f"Пробую local sync для задачи #{task_id}...")
        try:
            message = await _sync_task_jules_sessions(context.application, task_id=task_id, force=True)
        except Exception as exc:
            logger.exception("Task %s local sync failed", task_id)
            message = f"Local sync задачи #{task_id} не выполнен:\n{exc}"
        task_row = rt.storage.get_task(task_id)
        if task_row:
            message += "\n\n" + _render_task_detail(rt, task_row)
        await safe_query_edit_text(query, message, reply_markup=_task_actions_markup(task_id))
        return
    if data.startswith("task:ask_codex:"):
        task_id = int(data.rsplit(":", 1)[-1])
        if not query.message:
            return
        user_id = query.from_user.id if query.from_user else 0
        message = await _start_codex_task_inquiry(
            context.application,
            chat_id=query.message.chat_id,
            user_id=user_id,
            task_id=task_id,
        )
        await safe_query_edit_text(query, message, reply_markup=_task_actions_markup(task_id))
        return
    if data.startswith("task:jules:"):
        task_id = int(data.rsplit(":", 1)[-1])
        if not query.message:
            return
        task_row = rt.storage.get_task(task_id)
        if not task_row:
            await safe_query_edit_text(query, f"Task #{task_id} not found.")
            return
        await safe_query_edit_text(query, f"Создаю Jules session для задачи #{task_id}...")
        draft = rt.coordinator.build_draft(
            task_row["description"],
            source=task_row["source"],
            branch=task_row["branch"] or rt.config.jules_default_branch,
            title=task_row["title"],
        )
        decision = rt.coordinator.evaluate(draft)
        if not decision.ready:
            await safe_query_edit_text(query, decision.question, reply_markup=_task_actions_markup(task_id))
            return
        message = await _create_jules_session_for_chat(
            rt,
            decision.draft or draft,
            chat_id=query.message.chat_id,
            task_id=task_id,
        )
        task_row = rt.storage.get_task(task_id) or task_row
        await safe_query_edit_text(query, message + "\n\n" + _render_task_detail(rt, task_row), reply_markup=_task_actions_markup(task_id))
        return
    if data.startswith("task:gemini_review:"):
        task_id = int(data.rsplit(":", 1)[-1])
        if not query.message:
            return
        message = await _start_gemini_task_run(
            context.application,
            chat_id=query.message.chat_id,
            task_id=task_id,
            review=True,
        )
        await safe_query_edit_text(query, message, reply_markup=_task_actions_markup(task_id))
        return
    if data.startswith("task:gemini:"):
        task_id = int(data.rsplit(":", 1)[-1])
        if not query.message:
            return
        message = await _start_gemini_task_run(
            context.application,
            chat_id=query.message.chat_id,
            task_id=task_id,
        )
        await safe_query_edit_text(query, message, reply_markup=_task_actions_markup(task_id))
        return
    if data.startswith("task:cancel_confirm:"):
        task_id = int(data.rsplit(":", 1)[-1])
        message = await _cancel_task(rt, task_id)
        task_row = rt.storage.get_task(task_id)
        if task_row:
            message += "\n\n" + _render_task_detail(rt, task_row)
        await safe_query_edit_text(query, message, reply_markup=_task_actions_markup(task_id))
        return
    if data.startswith("task:cancel:"):
        task_id = int(data.rsplit(":", 1)[-1])
        await safe_query_edit_text(
            query,
            f"Отменить задачу #{task_id}?\n\nЭто остановит локальное отслеживание, пометит задачу CANCELLED и удалит активные Jules sessions через API, если они привязаны.",
            reply_markup=_task_cancel_markup(task_id),
        )
        return
    if data == "jules:menu":
        text = "\n".join(
            [
                "Jules",
                f"Default source: {rt.config.jules_default_source or 'not set'}",
                f"Default branch: {rt.config.jules_default_branch}",
            ]
        )
        await safe_query_edit_text(query, text, reply_markup=_jules_menu_markup())
        return
    if data == "jules:list_sources":
        items = await rt.jules.list_sources()
        rows: list[list[InlineKeyboardButton]] = []
        for index, source in enumerate(items[:40], start=1):
            branch = rt.config.jules_default_branch or JulesClient.source_default_branch(source)
            rt.storage.set_state(f"{JULES_SOURCE_KEY_PREFIX}{index}", f"{source.get('name', '')}|{branch}")
            rows.append([InlineKeyboardButton(_source_repo_label(source), callback_data=f"jules:select:{index}")])
        rows.append([InlineKeyboardButton("Назад", callback_data="jules:menu")])
        await safe_query_edit_text(query, "Выбери Jules source для дефолта:", reply_markup=InlineKeyboardMarkup(rows))
        return
    if data == "jules:list_branches":
        await safe_query_edit_text(
            query,
            "Выбери default branch для Jules:",
            reply_markup=InlineKeyboardMarkup(_branch_choice_rows(rt)),
        )
        return
    if data == "jules:manual_branch":
        if not query.message:
            return
        rt.storage.set_state(f"{JULES_AWAITING_BRANCH_PREFIX}{query.message.chat_id}", "1")
        await safe_query_edit_text(
            query,
            "Напиши следующим сообщением имя ветки для Jules.\nНапример: test",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="jules:menu")]]),
        )
        return
    if data.startswith("jules:branch:"):
        index = data.rsplit(":", 1)[-1]
        branch = rt.storage.get_state(f"{JULES_BRANCH_KEY_PREFIX}{index}")
        if not branch:
            await safe_query_edit_text(query, "Выбор устарел. Открой выбор ветки заново.", reply_markup=_jules_menu_markup())
            return
        _apply_jules_branch(rt, branch)
        await safe_query_edit_text(
            query,
            "\n".join(
                [
                    "Jules branch обновлен.",
                    f"Default source: {rt.config.jules_default_source or 'not set'}",
                    f"Default branch: {rt.config.jules_default_branch}",
                ]
            ),
            reply_markup=_jules_menu_markup(),
        )
        return
    if data.startswith("jules:select:"):
        index = data.rsplit(":", 1)[-1]
        stored = rt.storage.get_state(f"{JULES_SOURCE_KEY_PREFIX}{index}")
        if not stored or "|" not in stored:
            await safe_query_edit_text(query, "Выбор устарел. Открой Jules заново.", reply_markup=_jules_menu_markup())
            return
        source, branch = stored.split("|", 1)
        _apply_jules_default(rt, source=source, branch=branch or "test")
        await safe_query_edit_text(
            query,
            f"Jules default обновлен.\nSource: {source}\nBranch: {branch or 'test'}",
            reply_markup=_jules_menu_markup(),
        )
        return
    if data == "jules:sessions":
        rows = rt.storage.list_sessions(limit=10)
        if not rows:
            await safe_query_edit_text(query, "Нет отслеживаемых Jules sessions.", reply_markup=_jules_menu_markup())
            return
        lines = ["Jules sessions:"]
        for row in rows:
            state = row["state"]
            url = row["url"]
            latest_activity = ""
            with contextlib.suppress(Exception):
                session = await rt.jules.get_session(row["session_id"])
                state = session.get("state") or state
                url = session.get("url") or url
                state = await _auto_approve_jules_plan_if_needed(
                    rt,
                    session_id=row["session_id"],
                    state=state,
                    task_id=row.get("task_id"),
                )
                rt.storage.update_session_state(row["session_id"], state=state, url=url)
                activities = await rt.jules.list_activities(row["session_id"], page_size=5)
                if activities:
                    latest_activity = compact(format_activity(activities[-1]), max_len=350)
                if row.get("task_id"):
                    task_row = rt.storage.get_task(row["task_id"])
                    next_status = _jules_task_status([state])
                    if next_status and task_row and task_row["status"] != "CANCELLED":
                        rt.storage.update_task(row["task_id"], status=next_status)
            task_suffix = f" task #{row['task_id']}" if row.get("task_id") else ""
            lines.append(f"{row['session_id']}: {state}{task_suffix} - {row['title']}")
            if url:
                lines.append(url)
            if latest_activity:
                lines.append("Latest: " + latest_activity)
        await safe_query_edit_text(query, "\n".join(lines), reply_markup=_jules_menu_markup())


async def poll_jules(application: Application) -> None:
    rt: BotRuntime = application.bot_data["runtime"]
    if not rt.config.jules_api_key:
        return
    rows = rt.storage.list_watched_sessions()
    rows.extend(rt.storage.list_completed_sessions_needing_sync(sync_key_prefix="jules_local_sync:"))
    seen_sessions: set[str] = set()
    for row in rows:
        session_id = row["session_id"]
        if session_id in seen_sessions:
            continue
        seen_sessions.add(session_id)
        try:
            session = await rt.jules.get_session(session_id)
            state = session.get("state") or row["state"]
            state = await _auto_approve_jules_plan_if_needed(
                rt,
                session_id=session_id,
                state=state,
                task_id=row.get("task_id"),
            )
            rt.storage.update_session_state(session_id, state=state, url=session.get("url") or "")
            if row.get("task_id"):
                next_status = _jules_task_status([state])
                task_row = rt.storage.get_task(row["task_id"])
                if next_status and task_row and task_row["status"] != "CANCELLED":
                    rt.storage.update_task(row["task_id"], status=next_status)

            activities = await rt.jules.list_activities(session_id)
            for activity in sorted(activities, key=lambda item: item.get("createTime", "")):
                activity_id = activity.get("id") or activity.get("name", "").split("/")[-1]
                if not activity_id or not rt.storage.mark_activity_seen(session_id, activity_id):
                    continue
                if row.get("task_id"):
                    rt.storage.add_task_event(
                        row["task_id"],
                        kind="jules_activity",
                        message=compact(format_activity(activity), max_len=900),
                        payload={"session_id": session_id, "activity_id": activity_id},
                    )
                await send_to_chat(application.bot, row["chat_id"], f"Jules {session_id}:\n{format_activity(activity)}")

            if state in {"COMPLETED", "FAILED"}:
                sync_message = await _sync_completed_jules_session(application, row=row, session=session)
                final_lines = ["Final status:", format_session(session)]
                output_summary = summarize_session_outputs(session)
                if output_summary:
                    final_lines.extend(["", output_summary])
                if sync_message:
                    final_lines.extend(["", sync_message])
                await send_to_chat(application.bot, row["chat_id"], "\n".join(final_lines))
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
    app.add_handler(CallbackQueryHandler(callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, natural_message))
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    config = Config.from_env()
    app = build_application(config)
    logger.info("Starting Jules Telegram Orchestrator")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
