from __future__ import annotations

import subprocess
import time
from pathlib import Path

from django.conf import settings

from mars.policy import MarsPolicyError


def run_git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if check and result.returncode != 0:
        raise MarsPolicyError(_git_command_message(result))
    return result


def ensure_git_config(root: Path, key: str, value: str) -> None:
    if _git_config_get(root, key) == value:
        return

    attempts = max(1, int(getattr(settings, "MARS_GIT_CONFIG_LOCK_RETRIES", 6)))
    retry_delay = float(getattr(settings, "MARS_GIT_CONFIG_LOCK_RETRY_DELAY_SECONDS", 0.2))
    last_message = "Git command failed."

    for attempt in range(attempts):
        result = run_git(root, "config", key, value, check=False)
        if result.returncode == 0:
            return

        last_message = _git_command_message(result)
        if not _git_config_lock_error(last_message):
            raise MarsPolicyError(last_message)

        if _git_config_get(root, key) == value:
            return
        if _remove_stale_git_config_lock(root):
            continue
        if attempt < attempts - 1 and retry_delay > 0:
            time.sleep(retry_delay)

    if _git_config_get(root, key) == value:
        return
    raise MarsPolicyError(last_message)


def _git_command_message(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or "Git command failed.").strip()


def _git_config_lock_error(message: str) -> bool:
    lowered = message.lower()
    return "could not lock config file" in lowered and (
        "config.lock" in lowered or ".git/config" in lowered or "file exists" in lowered
    )


def _git_config_get(root: Path, key: str) -> str | None:
    result = run_git(root, "config", "--get", key, check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _remove_stale_git_config_lock(root: Path) -> bool:
    lock_path = root / ".git" / "config.lock"
    try:
        stat = lock_path.stat()
    except FileNotFoundError:
        return False

    stale_seconds = float(getattr(settings, "MARS_GIT_CONFIG_LOCK_STALE_SECONDS", 300))
    if stale_seconds > 0 and time.time() - stat.st_mtime < stale_seconds:
        return False

    try:
        current = lock_path.stat()
    except FileNotFoundError:
        return False
    if current.st_mtime_ns != stat.st_mtime_ns or current.st_size != stat.st_size:
        return False

    try:
        lock_path.unlink()
    except (FileNotFoundError, OSError):
        return False
    return True
