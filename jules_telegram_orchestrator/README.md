# AI Chief Orchestrator

Telegram bot for coordinating a software project through a chief-agent workflow.

The chief worker is Codex CLI through local `codex exec`. Subordinate workers are Google Jules through the Jules REST API and Gemini CLI through local headless execution.

The bot:

- talks to the customer in Telegram;
- forwards normal Telegram messages to the chief Codex coordinator and sends the Codex answer back to Telegram;
- keeps a project task backlog;
- can create safe working branches with a configured prefix;
- delegates long-running tasks to Jules;
- delegates simple local tasks and reviews to Gemini CLI;
- polls Jules activity updates;
- forwards plans, questions, progress, failures, and PR links back to Telegram;
- lets you approve plans and send feedback from Telegram;
- keeps an autonomy policy in env config so commit/push/PR behavior can be tightened or relaxed.

It does not expose arbitrary shell execution through Telegram. Git operations are explicit code paths.

## What Jules Requires

Before using this bot:

1. Sign in at https://jules.google.com.
2. Connect GitHub repositories in the Jules web app.
3. Generate a Jules API key at https://jules.google.com/settings.
4. Create a Telegram bot with BotFather and get its token.

## What Gemini CLI Requires

Gemini CLI must be installed and authenticated on the machine where this bot runs.

Official docs used for this implementation:

- Authentication: https://google-gemini.github.io/gemini-cli/docs/get-started/authentication.html
- Headless mode: https://google-gemini.github.io/gemini-cli/docs/cli/headless.html
- Context files: https://google-gemini.github.io/gemini-cli/docs/cli/gemini-md.html

For Google AI Pro or Ultra subscriptions, Gemini's docs recommend `Login with Google` and using the Google account associated with the subscription. Run this once in a normal terminal:

```bash
gemini
```

Then choose `Login with Google` and complete the browser login. The credentials are cached locally for later headless runs.

This repository also has a root `GEMINI.md` that imports `AGENTS.md`, so Gemini CLI receives the same project instructions.

## What Codex CLI Requires

Codex CLI must be installed and authenticated on the machine where this bot runs. The bot uses:

```bash
codex exec --cd C:\WebTrerm --sandbox danger-full-access --ask-for-approval never -
```

That means regular Telegram messages are processed by a non-interactive Codex chief run. The bot stores the resulting Codex `thread_id` in SQLite and resumes that same chief thread for later Telegram messages. The final Codex message is sent back to Telegram.

Jules REST API docs used for this implementation:

- `GET /v1alpha/sources`
- `POST /v1alpha/sessions`
- `GET /v1alpha/sessions/{sessionId}`
- `GET /v1alpha/sessions/{sessionId}/activities`
- `POST /v1alpha/sessions/{sessionId}:approvePlan`
- `POST /v1alpha/sessions/{sessionId}:sendMessage`

## Setup

```bash
cd jules_telegram_orchestrator
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=123456:telegram-token
TELEGRAM_ALLOWED_USER_IDS=123456789
JULES_API_KEY=your-jules-api-key
JULES_DEFAULT_SOURCE=sources/github-owner-repo
JULES_DEFAULT_BRANCH=main
JULES_REQUIRE_PLAN_APPROVAL=true
JULES_AUTO_CREATE_PR=false
GEMINI_CLI_ENABLED=true
GEMINI_CLI_COMMAND=gemini
GEMINI_CLI_TIMEOUT_SECONDS=900
GEMINI_CLI_OUTPUT_FORMAT=json
GEMINI_CLI_APPROVAL_MODE=auto_edit
CODEX_CHIEF_ENABLED=true
CODEX_CLI_COMMAND=codex
CODEX_CLI_TIMEOUT_SECONDS=1800
CODEX_CLI_SANDBOX=danger-full-access
CODEX_CLI_APPROVAL=never
CODEX_CLI_SEARCH=false
DEFAULT_ORCHESTRATOR=codex
PROJECT_ROOT=C:\WebTrerm
GIT_BRANCH_PREFIX=codex/
GIT_REMOTE=origin
GIT_AUTO_CREATE_BRANCH=true
GIT_AUTO_COMMIT=false
GIT_AUTO_PUSH=false
GIT_AUTO_PR=false
```

Run:

```bash
python -m jules_tg_orchestrator
```

## Telegram Commands

The bot also shows a persistent Telegram keyboard:

- `Статус` - chief overview, current Codex thread, git branch, recent tasks.
- `Задачи` - recent project tasks.
- `Git` - git status.
- `Codex` - Codex CLI status and stored chief thread id.
- `Gemini` - Gemini CLI status/auth check.
- `Jules` - Jules sources when configured.
- `Policy` - autonomy policy.
- `Оркестратор` - switch between Codex and Gemini CLI as the chief message handler.
- `Новый чат` - reset the stored chief thread.

- `/start` - help and current config summary.
- `/policy` - show autonomy policy.
- `/codex_check` - verify Codex CLI.
- `/codex_reset` - forget the stored Codex chief thread and create a new one on the next message.
- `/git_status` - show project git status.
- `/task <description>` - create a project task.
- `/tasks` - list project tasks.
- `/task_status <task_id>` - show project task details and recent events.
- `/delegate_task <task_id>` - delegate a project task to Jules.
- `/gemini_check` - verify Gemini CLI version and auth.
- `/gemini_task <task_id>` - delegate a task to Gemini CLI in the local workspace.
- `/gemini_review <task_id>` - ask Gemini CLI to review current local diff.
- `/commit_task <task_id> [message]` - commit current local changes for a task.
- `/push` - push the current branch to the configured remote.
- `/pr_task <task_id>` - create a PR for the current branch with GitHub CLI.
- `/sources` - list repositories connected to Jules.
- `/sessions` - list known sessions tracked by the bot.
- `/delegate <source> <branch> <task>` - create a Jules session.
- `/delegate <task>` - use default source and branch from `.env`.
- `/status <session_id>` - show session state.
- `/approve <session_id>` - approve a Jules plan.
- `/say <session_id> <message>` - send feedback or an answer to Jules.
- `/watch <session_id>` - start polling an existing Jules session.
- `/unwatch <session_id>` - stop polling a session.

Examples:

```text
/policy
/git_status
/task Add tests for Settings AI Memory policy updates
/delegate_task 1
/gemini_check
/gemini_task 1
/gemini_review 1
/commit_task 1 Add tests for memory policy updates
/push
/pr_task 1
/sources
/delegate sources/github-acme-web main Fix flaky Settings AI Memory tests and add coverage
/delegate Add pytest coverage for server memory policy updates
/status 31415926535897932384
/approve 31415926535897932384
/say 31415926535897932384 Yes, keep the API backwards compatible
```

## Natural Language Flow

You can talk to the bot without commands. Plain Telegram messages are forwarded to the stored chief Codex CLI thread, and the final Codex answer is sent back to Telegram.

For manual project management, `/task`, `/gemini_task`, and `/delegate_task` still exist. This preserves a stable project task id when several agent runs are needed.

## Orchestrator Switching

The bot supports switching between Codex CLI and Gemini CLI as the chief orchestrator for handling plain Telegram messages.

- Tap the **Оркестратор** keyboard button to see and change the active orchestrator.
- When **Codex** is active (default), messages go through the Codex CLI chief session with plan approval if configured.
- When **Gemini CLI** is active, messages go directly to Gemini CLI with full edit permissions.
- The choice persists across bot restarts (stored in SQLite).
- Set `DEFAULT_ORCHESTRATOR=codex` or `DEFAULT_ORCHESTRATOR=gemini` in `.env` to control the initial default.

## Autonomy Model

The intended operating model:

1. Customer writes tasks in Telegram.
2. Telegram bot starts a Codex chief run.
3. Codex answers directly, inspects context, creates a plan, and prefers delegating implementation to a subordinate worker.
4. Jules handles long-running repository work.
5. Gemini CLI handles shorter local tasks or reviews.
6. The chief monitors activities and reports back to Telegram.
7. Completed Jules/Gemini runs move the project task to `REVIEW`; failed runs move it to `BLOCKED`.
8. Commit/push/PR automation is controlled by `GIT_AUTO_COMMIT`, `GIT_AUTO_PUSH`, and `GIT_AUTO_PR`.

The current implementation has backlog, branch creation, Jules delegation, monitoring, and explicit commit/push/PR commands. Fully automatic commit/push/PR on timeout should be enabled only after the verification loop is wired to real checks.

## Safety Notes

- Do not commit `.env`; it contains secrets.
- Use `TELEGRAM_ALLOWED_USER_IDS`; otherwise anyone who can talk to the bot can create Jules tasks with your API key.
- By default `JULES_REQUIRE_PLAN_APPROVAL=true`, so Jules will wait for `/approve` before code changes.
- Set `JULES_AUTO_CREATE_PR=true` only if you want Jules to create PRs automatically.
