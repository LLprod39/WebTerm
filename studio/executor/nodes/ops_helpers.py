from __future__ import annotations

import json
import re
import shlex
import time
from typing import Any

SERVER_SNAPSHOT_SECTIONS = {
    "overview",
    "services",
    "processes",
    "docker",
    "logs",
    "disk",
    "network",
    "packages",
}
SERVICE_ACTIONS = {"start", "stop", "restart", "reload"}
DOCKER_ACTIONS = {"start", "stop", "restart"}
PROCESS_ACTIONS = {"terminate", "kill_force"}
ALERT_ACTIONS = {"resolve"}
FILE_ACTIONS = {"read", "write"}
PACKAGE_ACTIONS = {"list_updates", "install", "update", "remove"}
DISK_CLEANUP_ACTIONS = {"inspect", "journal_vacuum", "tmp_cleanup"}
BACKUP_RESTORE_CHECK_ACTIONS = {"inspect", "verify_latest"}
PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:@~/-]{0,127}$")


def compact_json(value: Any, *, limit: int = 3500) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n..."


def coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def coerce_bool(value: Any, *, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def coerce_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def normalise_packages(value: Any) -> list[str]:
    source_items = value if isinstance(value, list) else [value]
    raw_items: list[str] = []
    for item in source_items:
        raw_items.extend(part for part in re.split(r"[\s,]+", str(item or "")) if part)
    packages: list[str] = []
    for item in raw_items:
        package = str(item or "").strip()
        if not package:
            continue
        if not PACKAGE_NAME_RE.fullmatch(package):
            raise ValueError(f"Invalid package name: {package}")
        if package not in packages:
            packages.append(package)
    return packages


def package_command(package_manager: str, action: str, packages: list[str]) -> str:
    quoted = " ".join(shlex.quote(package) for package in packages)
    if package_manager == "apt":
        if action == "install":
            return f"DEBIAN_FRONTEND=noninteractive apt-get install -y -- {quoted}"
        if action == "update":
            return f"DEBIAN_FRONTEND=noninteractive apt-get install --only-upgrade -y -- {quoted}"
        if action == "remove":
            return f"DEBIAN_FRONTEND=noninteractive apt-get remove -y -- {quoted}"
    if package_manager in {"dnf", "yum"} and action in {"install", "update", "remove"}:
        return f"{package_manager} -y {action} {quoted}"
    raise ValueError("Unsupported package action")


def disk_cleanup_command(
    action: str,
    *,
    min_age_days: int,
    max_entries: int,
    dry_run: bool,
    vacuum_time_days: int,
    vacuum_size_mb: int | None,
) -> str:
    dry = "1" if dry_run else "0"
    if action == "journal_vacuum":
        vacuum_args = [f"--vacuum-time={vacuum_time_days}d"]
        if vacuum_size_mb:
            vacuum_args.append(f"--vacuum-size={vacuum_size_mb}M")
        command = "journalctl " + " ".join(vacuum_args)
        return (
            "set -u\n"
            "printf '__PLAN__\\n'\n"
            "journalctl --disk-usage 2>&1 || true\n"
            f"printf 'planned_command=%s\\n' {shlex.quote(command)}\n"
            "printf '__ACTION__\\n'\n"
            f"if [ {dry} -eq 1 ]; then printf 'dry_run=true\\n'; else {command} 2>&1; fi\n"
        )
    if action == "tmp_cleanup":
        return (
            "set -u\n"
            "printf '__PLAN__\\n'\n"
            f"find /tmp /var/tmp -xdev -mindepth 1 -mtime +{min_age_days} -print 2>/dev/null | head -n {max_entries}\n"
            "printf '__ACTION__\\n'\n"
            f"if [ {dry} -eq 1 ]; then printf 'dry_run=true\\n'; "
            "else "
            f"find /tmp /var/tmp -xdev -mindepth 1 -mtime +{min_age_days} -print 2>/dev/null | head -n {max_entries} | "
            "while IFS= read -r path; do "
            "case \"$path\" in /tmp/*|/var/tmp/*) rm -rf -- \"$path\" && printf 'removed=%s\\n' \"$path\" ;; *) printf 'skipped=%s\\n' \"$path\" ;; esac; "
            "done; "
            "fi\n"
        )
    raise ValueError("Unsupported disk cleanup action")


def backup_restore_check_command(path: str, *, action: str, max_depth: int, max_files: int) -> str:
    quoted_path = shlex.quote(path)
    return (
        "set -u\n"
        f"BACKUP_DIR={quoted_path}\n"
        f"MAX_DEPTH={max_depth}\n"
        f"MAX_FILES={max_files}\n"
        "printf '__FILES__\\n'\n"
        "if [ ! -d \"$BACKUP_DIR\" ]; then printf 'missing_dir\\t0\\t%s\\n' \"$BACKUP_DIR\"; exit 0; fi\n"
        "find \"$BACKUP_DIR\" -maxdepth \"$MAX_DEPTH\" -type f -printf '%T@\\t%s\\t%p\\n' 2>/dev/null | sort -nr | head -n \"$MAX_FILES\"\n"
        "printf '__VERIFY__\\n'\n"
        f"if [ {1 if action == 'verify_latest' else 0} -eq 0 ]; then printf 'verification=skipped\\n'; exit 0; fi\n"
        "latest=$(find \"$BACKUP_DIR\" -maxdepth \"$MAX_DEPTH\" -type f -printf '%T@\\t%s\\t%p\\n' 2>/dev/null | sort -nr | head -n 1 | cut -f3-)\n"
        "if [ -z \"$latest\" ]; then printf 'verification=no_files\\n'; exit 3; fi\n"
        "printf 'latest=%s\\n' \"$latest\"\n"
        "case \"$latest\" in\n"
        "  *.tar) tar -tf \"$latest\" >/dev/null 2>&1 ;;\n"
        "  *.tar.gz|*.tgz) tar -tzf \"$latest\" >/dev/null 2>&1 ;;\n"
        "  *.gz) gzip -t \"$latest\" >/dev/null 2>&1 ;;\n"
        "  *.zip) if command -v unzip >/dev/null 2>&1; then unzip -t \"$latest\" >/dev/null 2>&1; else printf 'verification=missing_unzip\\n'; exit 4; fi ;;\n"
        "  *) printf 'verification=unsupported_extension\\n'; exit 2 ;;\n"
        "esac\n"
        "status=$?\n"
        "printf 'verification_exit=%s\\n' \"$status\"\n"
        "exit \"$status\"\n"
    )


def parse_backup_file_rows(raw: str, *, max_age_hours: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    files: list[dict[str, Any]] = []
    missing_dir = ""
    now = time.time()
    for line in str(raw or "").splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        if parts[0] == "missing_dir":
            missing_dir = parts[2]
            continue
        try:
            mtime = float(parts[0])
            size = int(float(parts[1]))
        except (TypeError, ValueError):
            continue
        age_hours = max(0.0, (now - mtime) / 3600)
        files.append(
            {
                "path": parts[2],
                "size_bytes": size,
                "size_mb": round(size / (1024 * 1024), 2),
                "mtime_epoch": mtime,
                "age_hours": round(age_hours, 2),
            }
        )
    latest = files[0] if files else None
    summary = {
        "file_count": len(files),
        "latest_path": latest.get("path") if latest else "",
        "latest_age_hours": latest.get("age_hours") if latest else None,
        "latest_size_mb": latest.get("size_mb") if latest else None,
        "fresh": bool(latest and float(latest.get("age_hours") or 0) <= max_age_hours),
        "max_age_hours": max_age_hours,
        "missing_dir": missing_dir,
    }
    return files, summary
