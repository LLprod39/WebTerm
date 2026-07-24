"""Unit tests for F-11 governance policy helpers (no GitHub network)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.github_governance import (
    append_break_glass,
    close_break_glass,
    protection_payload,
)


def test_protection_payload_enforces_admins_and_required_checks() -> None:
    checks = ["Runtime Contract", "Playwright Smoke", "Python dependency audit"]
    payload = protection_payload(checks, enforce_admins=True)
    assert payload["enforce_admins"] is True
    assert payload["required_status_checks"]["strict"] is True
    assert payload["required_status_checks"]["contexts"] == checks
    assert payload["allow_force_pushes"] is False
    assert payload["allow_deletions"] is False
    assert payload["required_pull_request_reviews"]["require_code_owner_reviews"] is True
    assert payload["required_pull_request_reviews"]["required_approving_review_count"] == 1


def test_break_glass_log_open_and_close(tmp_path: Path) -> None:
    log_path = tmp_path / "break-glass-log.json"
    log_path.write_text(
        json.dumps({"policyVersion": "F-11", "incidents": []}),
        encoding="utf-8",
    )
    opened = append_break_glass(
        log_path,
        reason="production incident",
        approver="oncall",
        expiry="2026-07-24T18:00:00Z",
        incident_url="https://example.test/inc/1",
        opened_by="operator",
    )
    assert opened["status"] == "open"
    assert opened["id"] == "bg-0001"

    closed = close_break_glass(
        log_path,
        incident_id="bg-0001",
        restored_evidence_url="https://example.test/pr/1",
    )
    assert closed["status"] == "restored"
    assert closed["restoredEvidenceUrl"] == "https://example.test/pr/1"
    data = json.loads(log_path.read_text(encoding="utf-8"))
    assert data["incidents"][0]["restoredAt"] is not None


def test_f11_governance_config_lists_product_and_security_checks() -> None:
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "config/github-governance.json").read_text(encoding="utf-8"))
    assert config["policyVersion"] == "F-11"
    assert config["breakGlass"]["enforceAdmins"] is True
    assert config["breakGlass"]["allowPermanentAdminBypass"] is False
    assert config["stabilityClock"]["minCalendarDays"] == 0
    assert config["stabilityClock"]["minUniqueGreenShas"] == 1
    assert config["stabilityClock"]["countRerunsOfSameSha"] is False
    assert config["clock"]["status"] == "not_started"

    required = set(config["branches"]["main"]["requiredChecks"])
    for name in (
        "Backend Unit and Coverage",
        "Frontend Unit and Coverage",
        "Architecture No Regression",
        "God-file & Import Boundary Checks",
        "Playwright Smoke",
        "Python dependency audit",
        "npm dependency audit",
        "SBOM, checksums, provenance",
        "Secrets-never and security unit tests",
    ):
        assert name in required
    assert config["branches"]["test"]["requiredChecks"] == config["branches"]["main"]["requiredChecks"]
