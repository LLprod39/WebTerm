from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _as_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(value: str | None, *, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _allowed_user_ids(value: str | None) -> set[int]:
    if not value:
        return set()
    result: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if item:
            result.add(int(item))
    return result


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_allowed_user_ids: set[int]
    jules_api_key: str
    jules_base_url: str
    jules_default_source: str
    jules_default_branch: str
    jules_require_plan_approval: bool
    jules_auto_create_pr: bool
    jules_auto_sync_local: bool
    jules_auto_pull_local: bool
    jules_auto_commit_local: bool
    gemini_cli_enabled: bool
    gemini_cli_command: str
    gemini_cli_model: str
    gemini_cli_timeout_seconds: int
    gemini_cli_output_format: str
    gemini_cli_approval_mode: str
    codex_chief_enabled: bool
    codex_cli_command: str
    codex_cli_model: str
    codex_cli_timeout_seconds: int
    codex_cli_sandbox: str
    codex_cli_approval: str
    codex_cli_search: bool
    codex_require_plan_approval: bool
    default_orchestrator: str
    project_root: Path
    git_branch_prefix: str
    git_remote: str
    git_auto_create_branch: bool
    git_auto_commit: bool
    git_auto_push: bool
    git_auto_pr: bool
    poll_interval_seconds: int
    database_path: Path

    @classmethod
    def from_env(cls) -> Config:
        load_dotenv()
        config = cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_allowed_user_ids=_allowed_user_ids(os.getenv("TELEGRAM_ALLOWED_USER_IDS")),
            jules_api_key=os.getenv("JULES_API_KEY", "").strip(),
            jules_base_url=os.getenv("JULES_BASE_URL", "https://jules.googleapis.com/v1alpha").rstrip("/"),
            jules_default_source=os.getenv("JULES_DEFAULT_SOURCE", "").strip(),
            jules_default_branch=os.getenv("JULES_DEFAULT_BRANCH", "main").strip() or "main",
            jules_require_plan_approval=_as_bool(os.getenv("JULES_REQUIRE_PLAN_APPROVAL"), default=True),
            jules_auto_create_pr=_as_bool(os.getenv("JULES_AUTO_CREATE_PR"), default=False),
            jules_auto_sync_local=_as_bool(os.getenv("JULES_AUTO_SYNC_LOCAL"), default=True),
            jules_auto_pull_local=_as_bool(os.getenv("JULES_AUTO_PULL_LOCAL"), default=True),
            jules_auto_commit_local=_as_bool(os.getenv("JULES_AUTO_COMMIT_LOCAL"), default=True),
            gemini_cli_enabled=_as_bool(os.getenv("GEMINI_CLI_ENABLED"), default=True),
            gemini_cli_command=os.getenv("GEMINI_CLI_COMMAND", "gemini").strip() or "gemini",
            gemini_cli_model=os.getenv("GEMINI_CLI_MODEL", "").strip(),
            gemini_cli_timeout_seconds=_as_int(os.getenv("GEMINI_CLI_TIMEOUT_SECONDS"), default=900),
            gemini_cli_output_format=os.getenv("GEMINI_CLI_OUTPUT_FORMAT", "json").strip() or "json",
            gemini_cli_approval_mode=os.getenv("GEMINI_CLI_APPROVAL_MODE", "auto_edit").strip() or "auto_edit",
            codex_chief_enabled=_as_bool(os.getenv("CODEX_CHIEF_ENABLED"), default=True),
            codex_cli_command=os.getenv("CODEX_CLI_COMMAND", "codex").strip() or "codex",
            codex_cli_model=os.getenv("CODEX_CLI_MODEL", "").strip(),
            codex_cli_timeout_seconds=_as_int(os.getenv("CODEX_CLI_TIMEOUT_SECONDS"), default=1800),
            codex_cli_sandbox=os.getenv("CODEX_CLI_SANDBOX", "danger-full-access").strip() or "danger-full-access",
            codex_cli_approval=os.getenv("CODEX_CLI_APPROVAL", "never").strip() or "never",
            codex_cli_search=_as_bool(os.getenv("CODEX_CLI_SEARCH"), default=False),
            codex_require_plan_approval=_as_bool(os.getenv("CODEX_REQUIRE_PLAN_APPROVAL"), default=True),
            default_orchestrator=os.getenv("DEFAULT_ORCHESTRATOR", "codex").strip().lower() or "codex",
            project_root=Path(os.getenv("PROJECT_ROOT", ".")).resolve(),
            git_branch_prefix=os.getenv("GIT_BRANCH_PREFIX", "codex/").strip() or "codex/",
            git_remote=os.getenv("GIT_REMOTE", "origin").strip() or "origin",
            git_auto_create_branch=_as_bool(os.getenv("GIT_AUTO_CREATE_BRANCH"), default=True),
            git_auto_commit=_as_bool(os.getenv("GIT_AUTO_COMMIT"), default=False),
            git_auto_push=_as_bool(os.getenv("GIT_AUTO_PUSH"), default=False),
            git_auto_pr=_as_bool(os.getenv("GIT_AUTO_PR"), default=False),
            poll_interval_seconds=_as_int(os.getenv("POLL_INTERVAL_SECONDS"), default=45),
            database_path=Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3")),
        )
        config.validate()
        return config

    def validate(self) -> None:
        missing = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if missing:
            names = ", ".join(missing)
            raise RuntimeError(f"Missing required environment variables: {names}")
