#!/usr/bin/env python3
"""Audit or safely apply the repository's early branch-protection policy."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class GovernanceError(RuntimeError):
    pass


def gh_json(*args: str, input_payload: dict[str, Any] | None = None) -> Any:
    command = ["gh", "api", "-H", "Accept: application/vnd.github+json", *args]
    result = subprocess.run(
        command,
        input=json.dumps(input_payload) if input_payload is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        raise GovernanceError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout) if result.stdout.strip() else None


def push_capable_collaborators(repository: str) -> list[str]:
    collaborators = gh_json(f"repos/{repository}/collaborators?per_page=100")
    return sorted(item["login"] for item in collaborators if item.get("permissions", {}).get("push"))


def branch_head(repository: str, branch: str) -> str:
    return gh_json(f"repos/{repository}/branches/{branch}")["commit"]["sha"]


def successful_check_names(repository: str, commit: str) -> set[str]:
    response = gh_json(f"repos/{repository}/commits/{commit}/check-runs?per_page=100")
    return {
        run["name"]
        for run in response.get("check_runs", [])
        if run.get("status") == "completed" and run.get("conclusion") == "success"
    }


def protection_payload(required_checks: list[str]) -> dict[str, Any]:
    return {
        "required_status_checks": {"strict": True, "contexts": required_checks},
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "required_approving_review_count": 1,
            "require_last_push_approval": True,
        },
        "restrictions": None,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": True,
        "lock_branch": False,
        "allow_fork_syncing": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/github-governance.json")
    parser.add_argument("--apply", action="store_true", help="Apply only after all safety prerequisites pass")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    repository = config["repository"]
    collaborators = push_capable_collaborators(repository)
    minimum = config["minimumPushCapableCollaborators"]
    errors: list[str] = []
    if len(collaborators) < minimum:
        errors.append(
            f"review deadlock risk: {len(collaborators)} push-capable collaborator(s), {minimum} required before protection"
        )

    branch_states: dict[str, Any] = {}
    for branch, branch_config in config["branches"].items():
        commit = branch_head(repository, branch)
        successful = successful_check_names(repository, commit)
        required = branch_config["requiredChecks"]
        missing = sorted(set(required) - successful)
        if missing:
            errors.append(f"{branch}@{commit[:12]} has not passed required checks: {', '.join(missing)}")
        try:
            protection = gh_json(f"repos/{repository}/branches/{branch}/protection")
            protected = True
        except GovernanceError as exc:
            if "404" not in str(exc):
                raise
            protection = None
            protected = False
        branch_states[branch] = {
            "commit": commit,
            "protected": protected,
            "successfulChecks": sorted(successful),
            "requiredChecks": required,
            "currentProtection": protection,
        }

    print(json.dumps({"repository": repository, "collaborators": collaborators, "branches": branch_states}, indent=2))
    if not args.apply:
        if errors:
            print("Governance audit: NOT READY")
            for error in errors:
                print(f"- {error}")
            return 1
        print("Governance audit: READY TO APPLY (no external state changed)")
        return 0
    if errors:
        print("Governance apply refused:")
        for error in errors:
            print(f"- {error}")
        return 2
    for branch, branch_config in config["branches"].items():
        gh_json(
            "--method",
            "PUT",
            f"repos/{repository}/branches/{branch}/protection",
            "--input",
            "-",
            input_payload=protection_payload(branch_config["requiredChecks"]),
        )
        print(f"Protected {repository}:{branch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
