from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GeminiCliError(RuntimeError):
    pass


@dataclass(frozen=True)
class GeminiResult:
    command: list[str]
    response: str
    raw_output: str
    stderr: str
    returncode: int

    def render(self, *, max_len: int = 3000) -> str:
        text = self.response or self.raw_output or self.stderr
        text = text.strip()
        if len(text) > max_len:
            text = f"{text[: max_len - 1]}..."
        return text or "Gemini CLI finished without output."


class GeminiCli:
    def __init__(
        self,
        *,
        command: str = "gemini",
        cwd: Path,
        timeout_seconds: int = 900,
        output_format: str = "json",
        model: str = "",
        approval_mode: str = "auto_edit",
    ) -> None:
        self.command = self._resolve_command(command)
        self.cwd = cwd.resolve()
        self.timeout_seconds = timeout_seconds
        self.output_format = output_format
        self.model = model
        self.approval_mode = approval_mode

    def version(self) -> str:
        result = self._run([self.command, "--version"], timeout=30)
        return (result.stdout or result.stderr).strip()

    def run_prompt(self, prompt: str, *, allow_edits: bool = False) -> GeminiResult:
        args = [self.command, "--prompt", prompt, "--output-format", self.output_format]
        if self.model:
            args.extend(["--model", self.model])
        if allow_edits:
            args.extend(["--approval-mode", self.approval_mode])

        result = self._run(args, timeout=self.timeout_seconds)
        response = self._extract_response(result.stdout)
        return GeminiResult(
            command=args,
            response=response,
            raw_output=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )

    def _run(self, args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                args,
                cwd=self.cwd,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise GeminiCliError(f"Gemini CLI command not found: {self.command}") from exc
        except subprocess.TimeoutExpired as exc:
            raise GeminiCliError(f"Gemini CLI timed out after {timeout} seconds") from exc
        except subprocess.CalledProcessError as exc:
            output = (exc.stderr or exc.stdout or "").strip()
            raise GeminiCliError(output or f"Gemini CLI failed with exit code {exc.returncode}") from exc

    @staticmethod
    def _resolve_command(command: str) -> str:
        if os.name == "nt" and not Path(command).suffix:
            cmd_path = shutil.which(f"{command}.cmd")
            if cmd_path:
                return cmd_path
        return command

    @staticmethod
    def _extract_response(stdout: str) -> str:
        text = stdout.strip()
        if not text:
            return ""
        json_text = GeminiCli._extract_first_json_object(text)
        try:
            payload = json.loads(json_text or text)
        except json.JSONDecodeError:
            return text
        if isinstance(payload, dict):
            response = payload.get("response")
            if isinstance(response, str):
                return response
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str):
                    return message
        return text

    @staticmethod
    def _extract_first_json_object(text: str) -> str:
        start = text.find("{")
        if start < 0:
            return ""
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return ""
