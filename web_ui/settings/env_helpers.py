from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_int(name: str, default: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return int(raw.strip())


def env_float(name: str, default: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return float(raw.strip())


def append_unique(values: list[str], *items: str) -> list[str]:
    for item in items:
        value = (item or "").strip()
        if value and value not in values:
            values.append(value)
    return values


def origin_from_url(value: str) -> str:
    raw = (value or "").strip().rstrip("/")
    if not raw or "://" not in raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def hostname_from_value(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    return (parsed.hostname or "").strip()


def parse_cursor_cli_extra_env(*, cursor_cli_http1: bool) -> dict[str, str]:
    raw = os.getenv("CURSOR_CLI_EXTRA_ENV", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            return dict(data) if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    if cursor_cli_http1:
        return {"CURSOR_DISABLE_HTTP2": "1"}
    return {}


def parse_path_list_env(name: str, default: list[Path]) -> list[Path]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    paths: list[Path] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        paths.append(Path(value).expanduser())
    return paths or default


def cli_command(env_var: str, default_name: str) -> str:
    configured = os.getenv(env_var)
    if configured:
        return configured
    discovered = shutil.which(default_name)
    if discovered:
        return discovered
    if default_name == "codex":
        wsl_users_root = Path("/mnt/c/Users")
        if wsl_users_root.exists():
            for user_dir in wsl_users_root.iterdir():
                candidate = user_dir / "AppData/Local/Programs/OpenAI/Codex/bin/codex.exe"
                try:
                    if candidate.exists():
                        return str(candidate)
                except OSError:
                    continue
    return default_name
