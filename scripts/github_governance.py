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
import sys
from datetime import UTC, datetime
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
from github_governance_io import (  # noqa: E402
    GovernanceError,
    append_break_glass,
    branch_head,
    close_break_glass,
    collect_green_unique_shas_from_github,
    gh_json,
    git_head_sha,
    push_capable_collaborators,
    successful_check_names,
)


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
                errors.append(f"{branch}: protection missing required checks: {', '.join(missing_required)}")
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
        started_at=datetime.now(UTC),
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
        ledger_path = ROOT / config.get("stabilityClock", {}).get("ledgerPath", "config/ci-stability-ledger.json")
        ledger = (
            load_json(ledger_path)
            if ledger_path.exists()
            else {
                "policyVersion": config.get("policyVersion", "F-11"),
                "uniqueGreenShas": [],
                "entries": [],
            }
        )
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
    ledger = (
        load_json(ledger_path)
        if ledger_path.exists()
        else {
            "policyVersion": config.get("policyVersion", "F-11"),
            "uniqueGreenShas": [],
            "entries": [],
        }
    )
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
            recorded_at=item.get("createdAt") or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
        ledger = (
            load_json(ledger_path)
            if ledger_path.exists()
            else {
                "policyVersion": config.get("policyVersion", "F-11"),
                "uniqueGreenShas": [],
                "entries": [],
            }
        )
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
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
        ledger = (
            load_json(ledger_path)
            if ledger_path.exists()
            else {
                "uniqueGreenShas": [],
                "entries": [],
            }
        )
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
