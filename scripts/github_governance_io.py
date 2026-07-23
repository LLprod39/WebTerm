#!/usr/bin/env python3
"""GitHub/git I/O and break-glass log helpers for the F-11 governance policy.

Kept separate from ``github_governance.py`` so the policy orchestration stays
under the architecture god-file limit. Pure ledger math lives in
``ci_stability_clock.py``; this module owns the side-effecting I/O.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from ci_stability_clock import load_json, write_json  # noqa: E402


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


def git_head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        raise GovernanceError(result.stderr.strip() or "git rev-parse HEAD failed")
    return result.stdout.strip()


def append_break_glass(
    log_path: Path,
    *,
    reason: str,
    approver: str,
    expiry: str,
    incident_url: str,
    opened_by: str,
) -> dict[str, Any]:
    payload = load_json(log_path) if log_path.exists() else {
        "policyVersion": "F-11",
        "incidents": [],
    }
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    entry = {
        "id": f"bg-{len(payload.get('incidents', [])) + 1:04d}",
        "openedAt": now,
        "openedBy": opened_by,
        "reason": reason,
        "approver": approver,
        "expiry": expiry,
        "incidentUrl": incident_url,
        "restoredAt": None,
        "restoredEvidenceUrl": None,
        "status": "open",
    }
    incidents = list(payload.get("incidents", []))
    incidents.append(entry)
    payload["incidents"] = incidents
    write_json(log_path, payload)
    return entry


def close_break_glass(
    log_path: Path,
    *,
    incident_id: str,
    restored_evidence_url: str,
) -> dict[str, Any]:
    payload = load_json(log_path)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    found = None
    for item in payload.get("incidents", []):
        if item.get("id") == incident_id:
            item["restoredAt"] = now
            item["restoredEvidenceUrl"] = restored_evidence_url
            item["status"] = "restored"
            found = item
            break
    if found is None:
        raise GovernanceError(f"break-glass incident not found: {incident_id}")
    write_json(log_path, payload)
    return found


def list_workflow_runs(
    repository: str,
    *,
    branch: str,
    event: str | None = None,
    per_page: int = 50,
) -> list[dict[str, Any]]:
    query = f"repos/{repository}/actions/runs?branch={branch}&per_page={per_page}&status=completed"
    if event:
        query += f"&event={event}"
    response = gh_json(query)
    return list(response.get("workflow_runs") or [])


def collect_green_unique_shas_from_github(
    repository: str,
    *,
    branches: list[str],
    product_workflows: set[str],
    required_checks: set[str],
    since: str | None,
) -> list[dict[str, Any]]:
    """Find SHAs where every required check succeeded (latest completed run per check name)."""
    since_dt = None
    if since:
        text = since.replace("Z", "+00:00")
        since_dt = datetime.fromisoformat(text)
        if since_dt.tzinfo is None:
            since_dt = since_dt.replace(tzinfo=timezone.utc)

    candidates: dict[str, dict[str, Any]] = {}
    for branch in branches:
        for event in ("pull_request", "push", "schedule", "workflow_dispatch"):
            try:
                runs = list_workflow_runs(repository, branch=branch, event=event, per_page=50)
            except GovernanceError:
                continue
            for run in runs:
                if run.get("name") not in product_workflows:
                    continue
                if run.get("conclusion") != "success":
                    continue
                created = run.get("created_at") or run.get("updated_at")
                if since_dt and created:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if created_dt < since_dt:
                        continue
                sha = (run.get("head_sha") or "").lower()
                if not sha:
                    continue
                bucket = candidates.setdefault(
                    sha,
                    {
                        "sha": sha,
                        "branch": branch,
                        "event": event,
                        "workflows": set(),
                        "runIds": [],
                        "createdAt": created,
                    },
                )
                bucket["workflows"].add(run["name"])
                bucket["runIds"].append(run.get("id"))

    green: list[dict[str, Any]] = []
    for sha, meta in candidates.items():
        successful = successful_check_names(repository, sha)
        missing = sorted(required_checks - successful)
        if missing:
            continue
        green.append(
            {
                "sha": sha,
                "branch": meta["branch"],
                "event": meta["event"],
                "workflows": sorted(meta["workflows"]),
                "runIds": [rid for rid in meta["runIds"] if rid is not None],
                "createdAt": meta["createdAt"],
            }
        )
    green.sort(key=lambda item: item.get("createdAt") or "")
    return green
