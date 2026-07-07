from __future__ import annotations

from kubernetes_ops.services.release_backend_workstream import (
    build_kubernetes_release_backend_workstream,
    build_kubernetes_release_backend_workstream_blocker_groups,
    can_enable_kubernetes_release_sidebar,
)


def test_backend_workstream_reports_backend_implementation_gaps():
    payload = build_kubernetes_release_backend_workstream(
        completion_audit={
            "core_backend_complete": False,
            "runtime_readiness_complete": False,
            "core_backend_proofs": [
                {"id": "definition_of_done", "status": "ready", "complete": True},
                {"id": "normal_user_surface", "status": "missing", "complete": False},
            ],
            "runtime_missing_required_checks": ["sync_worker", "access_model"],
            "production_scope_readiness_checks": [],
            "production_evidence_checks": [],
        },
        blocker_groups=[],
        production_evidence_checklist={
            "status": "not_required",
            "gap_summary": {
                "next_gap_id": "select_production_environment",
                "blocking_gap_count": 1,
                "next_command_ids": [],
            },
        },
        can_enable_sidebar=False,
    )

    assert payload["status"] == "backend_incomplete"
    assert payload["backend_complete"] is False
    assert payload["core_backend_complete"] is False
    assert payload["runtime_readiness_complete"] is False
    assert payload["core_backend_proof_count"] == 2
    assert payload["core_backend_proof_ready_count"] == 1
    assert payload["core_backend_percent"] == 50
    assert payload["remaining_backend_gap_count"] == 3
    assert payload["safe_to_continue_frontend"] is False
    assert payload["next_backend_step"] == {"id": "close_backend_gaps", "type": "backend", "gap_count": 3}
    assert payload["external_production_blocker_summary"]["primary_category"] == "production_scope"
    assert {item["id"] for item in payload["remaining_backend_gaps"]} == {
        "normal_user_surface",
        "sync_worker",
        "access_model",
    }


def test_backend_workstream_splits_production_blockers_after_backend_is_complete():
    payload = build_kubernetes_release_backend_workstream(
        completion_audit={
            "core_backend_complete": True,
            "runtime_readiness_complete": True,
            "core_backend_proofs": [
                {"id": "definition_of_done", "status": "ready", "complete": True},
                {"id": "normal_user_surface", "status": "ready", "complete": True},
            ],
            "runtime_missing_required_checks": [],
            "production_scope_readiness_checks": ["sidebar_release_scope"],
            "production_evidence_checks": [
                {"id": "target_environment", "complete": False, "detail": "local"},
                {"id": "required_references", "complete": False, "detail": "2"},
                {"id": "release_artifact", "complete": False, "detail": "missing"},
            ],
        },
        blocker_groups=[
            {"id": "runtime_readiness", "status": "blocked"},
            {"id": "production_scope", "status": "blocked"},
            {"id": "release_artifact", "status": "missing"},
        ],
        production_evidence_checklist={
            "status": "missing_external_bundle",
            "gap_summary": {
                "next_gap_id": "set_external_bundle_refs",
                "blocking_gap_count": 3,
                "next_command_ids": ["external_evidence_bundle"],
            },
        },
        can_enable_sidebar=False,
    )

    assert payload["status"] == "backend_ready_production_blocked"
    assert payload["backend_complete"] is True
    assert payload["remaining_backend_gap_count"] == 0
    assert payload["remaining_backend_gaps"] == []
    assert payload["safe_to_continue_frontend"] is True
    assert payload["next_backend_step"] == {
        "id": "set_external_bundle_refs",
        "type": "production_evidence",
        "gap_count": 3,
        "command_ids": ["external_evidence_bundle"],
    }

    blockers = {(item["id"], item["type"]) for item in payload["external_production_blockers"]}
    assert ("sidebar_release_scope", "production_scope_readiness") in blockers
    assert ("target_environment", "production_evidence") in blockers
    assert ("set_external_bundle_refs", "production_evidence_checklist") in blockers
    assert ("production_scope", "blocker_group") in blockers
    assert ("release_artifact", "blocker_group") in blockers
    assert ("runtime_readiness", "blocker_group") not in blockers
    summary = payload["external_production_blocker_summary"]
    assert summary["count"] == payload["external_production_blocker_count"]
    assert summary["primary_category"] == "production_scope"
    assert summary["plain_status"] == "Select production release scope and remove local/demo evidence first."
    categories = {item["id"]: item for item in summary["categories"]}
    assert categories["production_scope"]["count"] == 2
    assert "target_environment" in categories["production_scope"]["blocker_ids"]
    assert categories["production_refs"]["count"] == 2
    assert {"required_references", "set_external_bundle_refs"} <= set(categories["production_refs"]["blocker_ids"])
    assert categories["release_artifact"]["count"] == 2
    assert categories["release_artifact"]["blocker_ids"].count("release_artifact") == 2


def test_backend_workstream_reports_sidebar_ready_when_all_gates_are_complete():
    payload = build_kubernetes_release_backend_workstream(
        completion_audit={
            "core_backend_complete": True,
            "runtime_readiness_complete": True,
            "core_backend_proofs": [
                {"id": "definition_of_done", "status": "ready", "complete": True},
                {"id": "normal_user_surface", "status": "ready", "complete": True},
            ],
            "runtime_missing_required_checks": [],
            "production_scope_readiness_checks": [],
            "production_evidence_checks": [
                {"id": "target_environment", "complete": True, "detail": "production"},
                {"id": "required_references", "complete": True, "detail": "0"},
                {"id": "release_artifact", "complete": True, "detail": "ready"},
            ],
        },
        blocker_groups=[],
        production_evidence_checklist={
            "status": "ready",
            "gap_summary": {
                "next_gap_id": "ready",
                "blocking_gap_count": 0,
                "next_command_ids": ["release_evidence", "release_handoff"],
            },
        },
        can_enable_sidebar=True,
    )

    assert payload["status"] == "ready_for_sidebar"
    assert payload["backend_complete"] is True
    assert payload["core_backend_percent"] == 100
    assert payload["remaining_backend_gap_count"] == 0
    assert payload["external_production_blocker_count"] == 0
    assert payload["external_production_blocker_summary"] == {
        "count": 0,
        "category_count": 0,
        "primary_category": "none",
        "plain_status": "No external production blockers.",
        "categories": [],
    }
    assert payload["safe_to_continue_frontend"] is True
    assert payload["next_backend_step"] == {"id": "none", "type": "complete", "gap_count": 0}


def test_sidebar_enablement_gate_requires_completion_audit_complete():
    assert can_enable_kubernetes_release_sidebar(
        production_ready=True,
        ready_for_sidebar=True,
        artifact_ready=True,
        release_scope_ready=True,
        completion_audit={
            "production_evidence_complete": True,
            "sidebar_enablement_complete": False,
        },
    ) is False

    assert can_enable_kubernetes_release_sidebar(
        production_ready=True,
        ready_for_sidebar=True,
        artifact_ready=True,
        release_scope_ready=True,
        completion_audit={
            "production_evidence_complete": True,
            "sidebar_enablement_complete": True,
        },
    ) is True


def test_backend_workstream_blocker_groups_do_not_mark_blocked_release_artifact_ready():
    groups = build_kubernetes_release_backend_workstream_blocker_groups(
        {
            "production_ready": False,
            "blockers": ["release_scope:local"],
            "release_scope": {
                "status": "local",
                "target_environment": "local",
                "local_indicator_count": 2,
            },
            "artifact_safety": {"status": "ready", "success": True},
        }
    )

    statuses = {item["id"]: item["status"] for item in groups}

    assert statuses["production_scope"] == "local"
    assert statuses["release_artifact"] == "not_production_ready"
    assert statuses["release_evidence"] == "blocked"


def test_backend_workstream_blocker_groups_do_not_treat_backend_only_gaps_as_external_release_evidence():
    groups = build_kubernetes_release_backend_workstream_blocker_groups(
        {
            "production_ready": False,
            "blockers": ["normal_user_surface:skipped", "definition_of_done:missing"],
            "release_scope": {
                "status": "ready",
                "target_environment": "production",
                "local_indicator_count": 0,
                "missing_required_references": [],
            },
            "artifact_safety": {"status": "ready", "success": True},
        }
    )

    by_id = {item["id"]: item for item in groups}

    assert by_id["release_artifact"]["status"] == "not_production_ready"
    assert "production_scope" not in by_id
    assert "release_evidence" not in by_id


def test_backend_workstream_blocker_groups_count_only_external_release_evidence_blockers():
    groups = build_kubernetes_release_backend_workstream_blocker_groups(
        {
            "production_ready": False,
            "blockers": [
                "normal_user_surface:skipped",
                "release_scope:local",
                "external_evidence_bundle:missing",
                "readiness:sidebar_release_scope=missing",
            ],
            "release_scope": {
                "status": "local",
                "target_environment": "local",
                "local_indicator_count": 1,
            },
            "artifact_safety": {"status": "ready", "success": True},
        }
    )

    by_id = {item["id"]: item for item in groups}

    assert by_id["release_evidence"]["status"] == "blocked"
    assert by_id["release_evidence"]["count"] == 3
