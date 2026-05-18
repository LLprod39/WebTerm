from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class CodexCliError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodexResult:
    response: str
    stdout: str
    stderr: str
    returncode: int
    thread_id: str = ""

    def render(self, *, max_len: int = 3500) -> str:
        text = (self.response or self.stdout or self.stderr).strip()
        if len(text) > max_len:
            return f"{text[: max_len - 1]}..."
        return text or "Codex finished without a final message."


class CodexCli:
    def __init__(
        self,
        *,
        command: str = "codex",
        cwd: Path,
        timeout_seconds: int = 1800,
        model: str = "",
        sandbox: str = "danger-full-access",
        approval: str = "never",
        search: bool = False,
    ) -> None:
        self.command = self._resolve_command(command)
        self.cwd = cwd.resolve()
        self.timeout_seconds = timeout_seconds
        self.model = model
        self.sandbox = sandbox
        self.approval = approval
        self.search = search

    def version(self) -> str:
        result = self._run([self.command, "--version"], timeout=30)
        return (result.stdout or result.stderr).strip()

    def run_chief_prompt(
        self,
        telegram_message: str,
        *,
        user_id: int,
        chat_id: int,
        session_id: str = "",
    ) -> CodexResult:
        prompt = self._build_prompt(telegram_message, user_id=user_id, chat_id=chat_id)
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".txt", delete=False) as handle:
            output_path = Path(handle.name)
        try:
            args = self._build_exec_args(output_path=output_path, session_id=session_id)
            self._append_common_options(args)
            if session_id:
                args.append(session_id)
            args.append("-")
            result = self._run(args, timeout=self.timeout_seconds, stdin=prompt)
            response = output_path.read_text(encoding="utf-8", errors="replace").strip()
            return CodexResult(
                response=response,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
                thread_id=self._extract_thread_id(result.stdout) or session_id,
            )
        finally:
            with contextlib.suppress(OSError):
                output_path.unlink(missing_ok=True)

    def build_delegation_plan(self, telegram_message: str, *, user_id: int, chat_id: int) -> CodexResult:
        prompt = self._build_plan_prompt(telegram_message, user_id=user_id, chat_id=chat_id)
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".txt", delete=False) as handle:
            output_path = Path(handle.name)
        try:
            args = [
                self.command,
                "exec",
                "--cd",
                str(self.cwd),
                "--sandbox",
                "read-only",
                "--json",
                "--output-last-message",
                str(output_path),
                "-",
            ]
            args.extend(["-c", 'approval_policy="never"'])
            if self.model:
                args.extend(["--model", self.model])
            result = self._run(args, timeout=min(self.timeout_seconds, 600), stdin=prompt)
            response = output_path.read_text(encoding="utf-8", errors="replace").strip()
            return CodexResult(
                response=response,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
                thread_id=self._extract_thread_id(result.stdout),
            )
        finally:
            with contextlib.suppress(OSError):
                output_path.unlink(missing_ok=True)

    def _append_common_options(self, args: list[str]) -> None:
        if self.approval:
            args.extend(["-c", f'approval_policy="{self.approval}"'])
        if self.model:
            args.extend(["--model", self.model])
        if self.search:
            args.append("--search")

    def _build_exec_args(self, *, output_path: Path, session_id: str = "") -> list[str]:
        if session_id:
            return [
                self.command,
                "exec",
                "resume",
                "--json",
                "--output-last-message",
                str(output_path),
            ]
        return [
            self.command,
            "exec",
            "--cd",
            str(self.cwd),
            "--sandbox",
            self.sandbox,
            "--json",
            "--output-last-message",
            str(output_path),
        ]

    def _run(
        self,
        args: list[str],
        *,
        timeout: int,
        stdin: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                args,
                cwd=self.cwd,
                input=stdin,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise CodexCliError(f"Codex CLI command not found: {self.command}") from exc
        except subprocess.TimeoutExpired as exc:
            raise CodexCliError(f"Codex CLI timed out after {timeout} seconds") from exc
        except subprocess.CalledProcessError as exc:
            output = (exc.stderr or exc.stdout or "").strip()
            raise CodexCliError(output or f"Codex CLI failed with exit code {exc.returncode}") from exc

    @staticmethod
    def _resolve_command(command: str) -> str:
        if os.name == "nt" and not Path(command).suffix:
            cmd_path = shutil.which(f"{command}.cmd")
            if cmd_path:
                return cmd_path
        return command

    @staticmethod
    def _extract_thread_id(stdout: str) -> str:
        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            thread_id = payload.get("thread_id")
            if isinstance(thread_id, str) and thread_id:
                return thread_id
        return ""

    @staticmethod
    def _build_prompt(telegram_message: str, *, user_id: int, chat_id: int) -> str:
        return "\n".join(
            [
                "You are the chief Codex project orchestrator for this repository.",
                "The customer is talking to you through Telegram. Answer as the chief coordinator.",
                "This is a persistent chief session. Treat previous messages in this thread as project memory.",
                "Operating model:",
                "1. You are the lead. You think, ask clarifying questions, inspect context, split work, and verify results.",
                "2. Prefer delegating implementation to subordinate agents instead of coding everything yourself.",
                "3. Use Gemini CLI for small local implementation/review tasks when it is enough.",
                "4. Use Jules for long-running repository work when Jules is configured.",
                "5. You may make small glue fixes, safety fixes, verification fixes, and integration edits yourself when that is faster or needed to unblock work.",
                "6. Do not blindly delegate. First decide whether the task is clear enough and which worker fits.",
                "7. Report progress, blockers, verification, and final status in concise Russian suitable for Telegram.",
                "8. If you need user input, ask the user directly in Russian.",
                "Tooling policy:",
                "- Use all MCP servers, plugins, connectors, and skills that are available in your current Codex environment when they materially help.",
                "- Discover and load relevant skills before using specialized workflows.",
                "- If a needed skill/plugin/MCP server is missing but the environment supports installing or enabling it, do that when allowed by the user's approved plan.",
                "- If installation requires permissions you do not have, report the exact blocker and the next action needed from the user.",
                "- When delegating to Jules or Gemini, include the relevant repository instructions, verification expectations, and tool/skill assumptions in the worker prompt.",
                "Do not mention that this is a separate CLI run unless it matters.",
                "",
                f"Telegram user id: {user_id}",
                f"Telegram chat id: {chat_id}",
                "",
                "Customer message:",
                telegram_message.strip(),
            ]
        )

    @staticmethod
    def _build_plan_prompt(telegram_message: str, *, user_id: int, chat_id: int) -> str:
        return "\n".join(
            [
                "You are the chief Codex project orchestrator for this repository.",
                "The customer sent a Telegram message. Do not change files. Do not delegate yet.",
                "Prepare an approval plan in Russian before any work starts.",
                "The plan must clearly say:",
                "1. What you understood.",
                "2. Clarifying questions if required.",
                "3. Whether the task is ready to execute.",
                "4. Which worker you would use: Codex chief, Gemini CLI, Jules, or a combination.",
                "5. Exact prompt/task text that will be sent to each worker.",
                "6. What checks/verification you will run.",
                "7. What git actions, if any, may happen.",
                "8. Which MCP servers/plugins/skills/tools you expect to use or install, and why.",
                "Keep it concise and Telegram-readable.",
                "",
                f"Telegram user id: {user_id}",
                f"Telegram chat id: {chat_id}",
                "",
                "Customer message:",
                telegram_message.strip(),
            ]
        )
