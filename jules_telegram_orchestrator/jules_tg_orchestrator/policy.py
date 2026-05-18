from __future__ import annotations

from dataclasses import dataclass

from jules_tg_orchestrator.config import Config


@dataclass(frozen=True)
class AutonomyPolicy:
    project_root: str
    branch_prefix: str
    remote: str
    gemini_cli_enabled: bool
    gemini_cli_command: str
    gemini_cli_timeout_seconds: int
    gemini_cli_approval_mode: str
    codex_chief_enabled: bool
    codex_cli_command: str
    codex_cli_timeout_seconds: int
    codex_cli_sandbox: str
    codex_cli_approval: str
    auto_create_branch: bool
    auto_commit: bool
    auto_push: bool
    auto_pr: bool
    require_jules_plan_approval: bool
    jules_auto_create_pr: bool

    @classmethod
    def from_config(cls, config: Config) -> AutonomyPolicy:
        return cls(
            project_root=str(config.project_root),
            branch_prefix=config.git_branch_prefix,
            remote=config.git_remote,
            gemini_cli_enabled=config.gemini_cli_enabled,
            gemini_cli_command=config.gemini_cli_command,
            gemini_cli_timeout_seconds=config.gemini_cli_timeout_seconds,
            gemini_cli_approval_mode=config.gemini_cli_approval_mode,
            codex_chief_enabled=config.codex_chief_enabled,
            codex_cli_command=config.codex_cli_command,
            codex_cli_timeout_seconds=config.codex_cli_timeout_seconds,
            codex_cli_sandbox=config.codex_cli_sandbox,
            codex_cli_approval=config.codex_cli_approval,
            auto_create_branch=config.git_auto_create_branch,
            auto_commit=config.git_auto_commit,
            auto_push=config.git_auto_push,
            auto_pr=config.git_auto_pr,
            require_jules_plan_approval=config.jules_require_plan_approval,
            jules_auto_create_pr=config.jules_auto_create_pr,
        )

    def render(self) -> str:
        return "\n".join(
            [
                "Chief autonomy policy:",
                f"Project root: {self.project_root}",
                f"Branch prefix: {self.branch_prefix}",
                f"Remote: {self.remote}",
                f"Gemini CLI enabled: {self.gemini_cli_enabled}",
                f"Gemini CLI command: {self.gemini_cli_command}",
                f"Gemini CLI timeout seconds: {self.gemini_cli_timeout_seconds}",
                f"Gemini CLI approval mode: {self.gemini_cli_approval_mode}",
                f"Codex chief enabled: {self.codex_chief_enabled}",
                f"Codex CLI command: {self.codex_cli_command}",
                f"Codex CLI timeout seconds: {self.codex_cli_timeout_seconds}",
                f"Codex CLI sandbox: {self.codex_cli_sandbox}",
                f"Codex CLI approval: {self.codex_cli_approval}",
                f"Auto-create branch: {self.auto_create_branch}",
                f"Auto-commit: {self.auto_commit}",
                f"Auto-push: {self.auto_push}",
                f"Auto-create PR: {self.auto_pr}",
                f"Jules requires plan approval: {self.require_jules_plan_approval}",
                f"Jules auto-create PR: {self.jules_auto_create_pr}",
            ]
        )
