#!/usr/bin/env python3
"""Create a tamper-evident bundle from already-produced release artifacts.

This tool records evidence. It intentionally does not run validation commands or
declare a release PASS; that decision belongs to the release checklist/CI policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class EvidenceError(ValueError):
    """Raised when an evidence input is incomplete or cannot be trusted."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        raise EvidenceError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def require_clean_worktree(repo: Path) -> None:
    dirty = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        sample = "\n".join(dirty.splitlines()[:20])
        raise EvidenceError(f"release evidence requires a clean worktree:\n{sample}")


def parse_mapping(spec: str, repo: Path) -> tuple[str, Path]:
    kind, separator, raw_path = spec.partition("=")
    if not separator or not kind.strip() or not raw_path.strip():
        raise EvidenceError(f"expected KIND=PATH, got {spec!r}")
    path = Path(raw_path.strip())
    if not path.is_absolute():
        path = repo / path
    path = path.resolve()
    if not path.is_file():
        raise EvidenceError(f"artifact/config file does not exist: {path}")
    return kind.strip(), path


def load_command_results(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read command results {path}: {exc}") from exc
    commands = payload.get("commands") if isinstance(payload, dict) else None
    if not isinstance(commands, list) or not commands:
        raise EvidenceError("command results must contain a non-empty commands array")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(commands):
        if not isinstance(item, dict):
            raise EvidenceError(f"commands[{index}] must be an object")
        name = item.get("name")
        command = item.get("command")
        exit_code = item.get("exit_code")
        tool_versions = item.get("tool_versions", {})
        if not isinstance(name, str) or not name.strip():
            raise EvidenceError(f"commands[{index}].name is required")
        if not isinstance(command, str) or not command.strip():
            raise EvidenceError(f"commands[{index}].command is required")
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            raise EvidenceError(f"commands[{index}].exit_code must be an integer")
        if not isinstance(tool_versions, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in tool_versions.items()
        ):
            raise EvidenceError(f"commands[{index}].tool_versions must map strings to strings")
        normalized.append(
            {
                "name": name.strip(),
                "command": command.strip(),
                "exit_code": exit_code,
                "tool_versions": dict(sorted(tool_versions.items())),
                "state": "succeeded" if exit_code == 0 else "failed",
            }
        )
    return normalized


def file_record(kind: str, path: Path, repo: Path) -> dict[str, Any]:
    try:
        display_path = path.relative_to(repo).as_posix()
    except ValueError:
        display_path = str(path)
    return {
        "kind": kind,
        "path": display_path,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def build_bundle(
    *,
    repo: Path,
    commands: list[dict[str, Any]],
    artifacts: list[tuple[str, Path]],
    configs: list[tuple[str, Path]],
    ci_run_url: str | None,
    created_at: str | None = None,
) -> dict[str, Any]:
    commit = git(repo, "rev-parse", "HEAD")
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    failures = sum(command["exit_code"] != 0 for command in commands)
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": created_at or datetime.now(UTC).isoformat(),
        "repository": {
            "commit": commit,
            "branch": branch,
            "ci_run_url": ci_run_url,
            "worktree": "clean",
        },
        "commands": commands,
        "artifacts": [file_record(kind, path, repo) for kind, path in artifacts],
        "configuration": [file_record(kind, path, repo) for kind, path in configs],
        "summary": {
            "command_count": len(commands),
            "failed_command_count": failures,
            "command_state": "succeeded" if failures == 0 else "failed",
            "release_decision": "NOT_EVALUATED",
        },
    }


def render_markdown(bundle: dict[str, Any], json_name: str) -> str:
    repository = bundle["repository"]
    summary = bundle["summary"]
    lines = [
        "# WebTerm release evidence",
        "",
        f"- Commit: `{repository['commit']}`",
        f"- Branch: `{repository['branch']}`",
        f"- Created: `{bundle['created_at']}`",
        f"- Command state: **{summary['command_state']}**",
        "- Release decision: **NOT EVALUATED** — this bundle is evidence, not approval.",
        f"- Machine-readable bundle: `{json_name}`",
        "",
        "## Commands",
        "",
        "| Gate | Exit | State | Command |",
        "|---|---:|---|---|",
    ]
    for command in bundle["commands"]:
        safe_command = command["command"].replace("|", "\\|")
        lines.append(f"| {command['name']} | {command['exit_code']} | {command['state']} | `{safe_command}` |")
    lines.extend(["", "## Artifacts", "", "| Kind | Path | SHA-256 |", "|---|---|---|"])
    if bundle["artifacts"]:
        for artifact in bundle["artifacts"]:
            lines.append(f"| {artifact['kind']} | `{artifact['path']}` | `{artifact['sha256']}` |")
    else:
        lines.append("| none | — | — |")
    lines.extend(["", "## Configuration", "", "| Kind | Path | SHA-256 |", "|---|---|---|"])
    for config in bundle["configuration"]:
        lines.append(f"| {config['kind']} | `{config['path']}` | `{config['sha256']}` |")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command-results", required=True, type=Path)
    parser.add_argument("--artifact", action="append", default=[], metavar="KIND=PATH")
    parser.add_argument("--config", action="append", default=[], metavar="KIND=PATH")
    parser.add_argument("--ci-run-url")
    parser.add_argument("--output-dir", type=Path, default=Path(".ci-artifacts/release-evidence"))
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo_root.resolve()
    try:
        require_clean_worktree(repo)
        command_path = args.command_results if args.command_results.is_absolute() else repo / args.command_results
        commands = load_command_results(command_path.resolve())
        artifacts = [parse_mapping(spec, repo) for spec in args.artifact]
        configs = [parse_mapping(spec, repo) for spec in args.config]
        bundle = build_bundle(
            repo=repo,
            commands=commands,
            artifacts=artifacts,
            configs=configs,
            ci_run_url=args.ci_run_url,
        )
        output_dir = args.output_dir if args.output_dir.is_absolute() else repo / args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        stem = f"release-evidence-{bundle['repository']['commit'][:12]}-{stamp}"
        json_path = output_dir / f"{stem}.json"
        markdown_path = output_dir / f"{stem}.md"
        json_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        markdown_path.write_text(render_markdown(bundle, json_path.name), encoding="utf-8")
    except EvidenceError as exc:
        print(f"Evidence collection refused: {exc}")
        return 2
    print(json_path)
    print(markdown_path)
    print("Release decision: NOT_EVALUATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
