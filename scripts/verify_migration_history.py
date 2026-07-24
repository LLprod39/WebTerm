from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

MIGRATION_NAME = re.compile(r"^\d{4}_[A-Za-z0-9_]+\.py$")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def _commit(repo: Path, ref: str) -> str:
    return _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")


def _is_migration(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return "/migrations/" in f"/{normalized}" and MIGRATION_NAME.fullmatch(Path(normalized).name) is not None


def verify_history(*, repo: Path, from_ref: str, to_ref: str) -> dict[str, Any]:
    from_commit = _commit(repo, from_ref)
    to_commit = _commit(repo, to_ref)
    diff = _git(repo, "diff", "--name-status", "--find-renames", f"{from_commit}..{to_commit}", "--")
    added: list[str] = []
    violations: list[dict[str, str]] = []
    for raw_line in diff.splitlines():
        columns = raw_line.split("\t")
        if len(columns) < 2:
            continue
        status = columns[0]
        paths = columns[1:]
        migration_paths = [path for path in paths if _is_migration(path)]
        if not migration_paths:
            continue
        if status == "A" and len(migration_paths) == 1:
            added.append(migration_paths[0])
            continue
        violations.append({"status": status, "paths": " -> ".join(migration_paths)})

    return {
        "schema_version": 1,
        "from_ref": from_ref,
        "from_commit": from_commit,
        "to_ref": to_ref,
        "to_commit": to_commit,
        "added_migrations": sorted(added),
        "historical_mutations": violations,
        "status": "pass" if not violations else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reject edits to migration files that already exist in a fixture")
    parser.add_argument("--from-ref", required=True)
    parser.add_argument("--to-ref", default="HEAD")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        report = verify_history(repo=args.repo.resolve(), from_ref=args.from_ref, to_ref=args.to_ref)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
