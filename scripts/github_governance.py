#!/usr/bin/env python3
"""Audit or safely apply the repository's F-11 branch-protection policy.

Also:
- starts the F-11 stability clock after a successful --apply
- records unique green SHAs (reruns of the same SHA do not count)
- appends logged break-glass incidents
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from ci_stability_clock import (  # noqa: E402
    evaluate_clock,
    load_json,
    record_unique_green_sha,
    start_clock_payload,
    write_json,
)


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


def protection_payload(required_checks: list[str], *, enforce_admins: bool = True) -> dict[str, Any]:
    """PR-only protection with admin enforcement (no permanent check bypass)."""
    return {
        "required_status_checks": {"strict": True, "contexts": required_checks},
        "enforce_admins": enforce_admins,
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


def audit_branches(config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    repository = config["repository"]
    collaborators = push_capable_collaborators(repository)
    minimum = config["minimumPushCapableCollaborators"]
    errors: list[str] = []
    if len(collaborators) < minimum:
        errors.append(
            f"review deadlock risk: {len(collaborators)} push-capable collaborator(s), "
            f"{minimum} required before protection"
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
            enforce_admins = bool(
                (protection.get("enforce_admins") or {}).get("enabled")
                if isinstance(protection.get("enforce_admins"), dict)
                else protection.get("enforce_admins")
            )
            if not enforce_admins:
                errors.append(f"{branch}: enforce_admins is false (admin can merge without checks)")
            contexts = (
                ((protection.get("required_status_checks") or {}).get("contexts"))
                or ((protection.get("required_status_checks") or {}).get("checks"))
                or []
            )
            if contexts and isinstance(contexts[0], dict):
                current_required = {item.get("context") for item in contexts}
            else:
                current_required = set(contexts)
            missing_required = sorted(set(required) - current_required)
            if protected and missing_required:
                errors.append(
                    f"{branch}: protection missing required checks: {', '.join(missing_required)}"
                )
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

    report = {
        "repository": repository,
        "policyVersion": config.get("policyVersion"),
        "collaborators": collaborators,
        "branches": branch_states,
        "clock": config.get("clock"),
    }
    return report, errors


def apply_protection(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    report, errors = audit_branches(config)
    if errors:
        print("Governance apply refused:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(2)

    enforce_admins = bool(config.get("breakGlass", {}).get("enforceAdmins", True))
    repository = config["repository"]
    for branch, branch_config in config["branches"].items():
        gh_json(
            "--method",
            "PUT",
            f"repos/{repository}/branches/{branch}/protection",
            "--input",
            "-",
            input_payload=protection_payload(
                branch_config["requiredChecks"],
                enforce_admins=enforce_admins,
            ),
        )
        print(f"Protected {repository}:{branch}")

    started = start_clock_payload(
        started_at=datetime.now(timezone.utc),
        started_commit=git_head_sha(),
        started_by="github_governance.py --apply",
        applied_branches=sorted(config["branches"].keys()),
    )
    # Refuse to restart an already-started clock (no acceleration / backdate).
    existing = config.get("clock") or {}
    if existing.get("status") == "started" and existing.get("startedAt"):
        print("Clock already started; leaving original startedAt/startedCommit unchanged.")
        started = existing
    else:
        config["clock"] = started
        write_json(config_path, config)
        ledger_path = ROOT / config.get("stabilityClock", {}).get(
            "ledgerPath", "config/ci-stability-ledger.json"
        )
        ledger = load_json(ledger_path) if ledger_path.exists() else {
            "policyVersion": config.get("policyVersion", "F-11"),
            "uniqueGreenShas": [],
            "entries": [],
        }
        ledger["clockStartedAt"] = started["startedAt"]
        ledger["clockStartedCommit"] = started["startedCommit"]
        write_json(ledger_path, ledger)
        print(json.dumps({"clockStarted": started}, indent=2))

    return report


def sync_unique_shas(config: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    repository = config["repository"]
    clock = config.get("clock") or {}
    if clock.get("status") != "started":
        return {"status": "clock_not_started", "recorded": [], "uniqueGreenShaCount": 0}

    stability = config.get("stabilityClock") or {}
    ledger_path = ROOT / stability.get("ledgerPath", "config/ci-stability-ledger.json")
    ledger = load_json(ledger_path) if ledger_path.exists() else {
        "policyVersion": config.get("policyVersion", "F-11"),
        "uniqueGreenShas": [],
        "entries": [],
    }
    # Required checks union across protected branches.
    required: set[str] = set()
    for branch_config in config["branches"].values():
        required.update(branch_config["requiredChecks"])

    green = collect_green_unique_shas_from_github(
        repository,
        branches=list(stability.get("mergeCandidateBranches") or config["branches"].keys()),
        product_workflows=set(stability.get("productWorkflows") or []),
        required_checks=required,
        since=clock.get("startedAt"),
    )
    recorded: list[dict[str, Any]] = []
    for item in green:
        ledger, result = record_unique_green_sha(
            ledger,
            sha=item["sha"],
            recorded_at=item.get("createdAt")
            or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            event=item.get("event") or "sync",
            branch=item.get("branch"),
            run_ids=item.get("runIds") or [],
            workflows=item.get("workflows") or [],
            source="github_sync",
        )
        recorded.append(result.__dict__)
    if not dry_run:
        write_json(ledger_path, ledger)
    evaluation = evaluate_clock(
        clock=clock,
        ledger=ledger,
        min_calendar_days=int(stability.get("minCalendarDays", 14)),
        min_unique_green_shas=int(stability.get("minUniqueGreenShas", 30)),
    )
    return {
        "status": "ok",
        "recorded": recorded,
        "uniqueGreenShaCount": len(ledger.get("uniqueGreenShas") or []),
        "evaluation": evaluation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/github-governance.json")
    parser.add_argument("--apply", action="store_true", help="Apply only after all safety prerequisites pass")
    parser.add_argument(
        "--clock-status",
        action="store_true",
        help="Print F-11 calendar + unique-SHA gate status",
    )
    parser.add_argument(
        "--sync-unique-shas",
        action="store_true",
        help="Query GitHub for green merge-candidate SHAs and update the ledger",
    )
    parser.add_argument(
        "--record-sha",
        type=str,
        default=None,
        help="Manually record one green SHA (reruns of the same SHA are ignored for the denominator)",
    )
    parser.add_argument("--event", type=str, default="manual")
    parser.add_argument("--branch", type=str, default=None)
    parser.add_argument(
        "--break-glass",
        action="store_true",
        help="Append a logged break-glass incident (does not change GitHub protection by itself)",
    )
    parser.add_argument("--reason", type=str, default=None)
    parser.add_argument("--approver", type=str, default=None)
    parser.add_argument("--expiry", type=str, default=None, help="UTC expiry timestamp or duration note")
    parser.add_argument("--incident-url", type=str, default=None)
    parser.add_argument("--opened-by", type=str, default="operator")
    parser.add_argument("--close-break-glass", type=str, default=None, help="Incident id to mark restored")
    parser.add_argument("--restored-evidence-url", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = load_json(args.config)

    if args.break_glass:
        if not args.reason or not args.approver or not args.expiry or not args.incident_url:
            print("break-glass requires --reason --approver --expiry --incident-url")
            return 2
        log_path = ROOT / config.get("breakGlass", {}).get("logPath", "config/break-glass-log.json")
        entry = append_break_glass(
            log_path,
            reason=args.reason,
            approver=args.approver,
            expiry=args.expiry,
            incident_url=args.incident_url,
            opened_by=args.opened_by,
        )
        print(json.dumps({"breakGlassOpened": entry}, indent=2))
        print("Remember: re-apply protection after the emergency with --apply")
        return 0

    if args.close_break_glass:
        if not args.restored_evidence_url:
            print("--close-break-glass requires --restored-evidence-url")
            return 2
        log_path = ROOT / config.get("breakGlass", {}).get("logPath", "config/break-glass-log.json")
        entry = close_break_glass(
            log_path,
            incident_id=args.close_break_glass,
            restored_evidence_url=args.restored_evidence_url,
        )
        print(json.dumps({"breakGlassClosed": entry}, indent=2))
        return 0

    if args.record_sha:
        stability = config.get("stabilityClock") or {}
        ledger_path = ROOT / stability.get("ledgerPath", "config/ci-stability-ledger.json")
        ledger = load_json(ledger_path) if ledger_path.exists() else {
            "policyVersion": config.get("policyVersion", "F-11"),
            "uniqueGreenShas": [],
            "entries": [],
        }
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ledger, result = record_unique_green_sha(
            ledger,
            sha=args.record_sha,
            recorded_at=now,
            event=args.event,
            branch=args.branch,
            source="cli",
        )
        if not args.dry_run:
            write_json(ledger_path, ledger)
        print(json.dumps({"record": result.__dict__}, indent=2))

    if args.sync_unique_shas:
        try:
            result = sync_unique_shas(config, dry_run=args.dry_run)
        except GovernanceError as exc:
            print(f"sync failed: {exc}")
            return 1
        print(json.dumps(result, indent=2))
        return 0

    if args.clock_status or args.record_sha:
        stability = config.get("stabilityClock") or {}
        ledger_path = ROOT / stability.get("ledgerPath", "config/ci-stability-ledger.json")
        ledger = load_json(ledger_path) if ledger_path.exists() else {
            "uniqueGreenShas": [],
            "entries": [],
        }
        evaluation = evaluate_clock(
            clock=config.get("clock") or {},
            ledger=ledger,
            min_calendar_days=int(stability.get("minCalendarDays", 14)),
            min_unique_green_shas=int(stability.get("minUniqueGreenShas", 30)),
        )
        print(json.dumps({"evaluation": evaluation}, indent=2))
        if args.clock_status and not args.apply:
            return 0 if not evaluation["readyToCloseF11"] else 0

    if args.apply:
        try:
            apply_protection(config, args.config)
        except GovernanceError as exc:
            print(f"apply failed: {exc}")
            return 1
        return 0

    if args.record_sha or args.clock_status:
        return 0

    # Default: audit only
    try:
        report, errors = audit_branches(config)
    except GovernanceError as exc:
        print(f"audit failed: {exc}")
        return 1
    print(json.dumps(report, indent=2))
    stability = config.get("stabilityClock") or {}
    ledger_path = ROOT / stability.get("ledgerPath", "config/ci-stability-ledger.json")
    ledger = load_json(ledger_path) if ledger_path.exists() else {"uniqueGreenShas": [], "entries": []}
    evaluation = evaluate_clock(
        clock=config.get("clock") or {},
        ledger=ledger,
        min_calendar_days=int(stability.get("minCalendarDays", 14)),
        min_unique_green_shas=int(stability.get("minUniqueGreenShas", 30)),
    )
    print(json.dumps({"evaluation": evaluation}, indent=2))
    if errors:
        print("Governance audit: NOT READY")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Governance audit: READY TO APPLY (no external state changed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
