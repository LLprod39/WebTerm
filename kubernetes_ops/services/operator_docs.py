from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings

OPERATOR_RUNBOOK_RELATIVE_PATH = "docs/architecture/KUBERNETES_OPS_OPERATIONS.md"
REQUIRED_RUNBOOK_MARKERS = (
    "# Kubernetes Ops Operations Runbook",
    "## 1. Scope And Operating Mode",
    "## 2. Production Configuration Checklist",
    "## 3. Readiness And Release Gates",
    "## 4. Provider Outage Disaster Recovery",
    "## 5. Sync Worker Recovery",
    "## 6. Token Rotation And Secret Handling",
    "## 7. Audit Retention",
    "## 8. Terminal And Debug Policy",
    "## 9. Rollback And Disablement",
    "## 10. Operator Daily Checklist",
)


def build_kubernetes_operator_docs_report(*, base_dir: Path | str | None = None) -> dict[str, Any]:
    root = Path(base_dir if base_dir is not None else settings.BASE_DIR)
    runbook_path = root / OPERATOR_RUNBOOK_RELATIVE_PATH
    exists = runbook_path.exists() and runbook_path.is_file()
    content = runbook_path.read_text(encoding="utf-8") if exists else ""
    missing_markers = [marker for marker in REQUIRED_RUNBOOK_MARKERS if marker not in content]
    status = "ready" if exists and not missing_markers else "missing"
    return {
        "status": status,
        "runbook_path": OPERATOR_RUNBOOK_RELATIVE_PATH,
        "exists": exists,
        "missing_markers": missing_markers,
        "required_markers": list(REQUIRED_RUNBOOK_MARKERS),
        "topics": [
            "production_configuration",
            "readiness_gates",
            "provider_outage_dr",
            "sync_worker_recovery",
            "secret_rotation",
            "audit_retention",
            "admin_action_post_review",
            "admin_interactive_transport",
            "admin_recording_retention",
            "terminal_policy",
            "rollback_disablement",
            "daily_operations",
        ],
    }


def kubernetes_operator_docs_check() -> dict[str, Any]:
    report = build_kubernetes_operator_docs_report()
    if report["status"] == "ready":
        return {
            "id": "operator_docs",
            "status": "ready",
            "detail": f"Kubernetes Ops operator and DR runbook is present: {OPERATOR_RUNBOOK_RELATIVE_PATH}.",
            "required": False,
        }
    return {
        "id": "operator_docs",
        "status": "missing",
        "detail": "Kubernetes Ops operator runbook is incomplete or missing: "
        + ", ".join(report["missing_markers"] or [OPERATOR_RUNBOOK_RELATIVE_PATH]),
        "required": False,
    }
