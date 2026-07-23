from __future__ import annotations

from kubernetes_ops.services.release_command_plan import build_kubernetes_release_command_plan
from kubernetes_ops.services.release_preflight import PREFLIGHT_ARTIFACT


def test_release_command_plan_uses_loader_compatible_preflight_artifact_path():
    plan = build_kubernetes_release_command_plan(
        production_evidence_checklist={
            "status": "ready",
            "production_target": True,
            "core_references": [],
            "external_bundle": {"status": "ready"},
            "gap_summary": {
                "next_gap_id": "ready",
                "blocking_gap_count": 0,
                "next_command_ids": ["release_evidence", "release_handoff"],
            },
        },
        blocker_groups=[{"id": "runtime_readiness", "count": 1}],
        can_enable_sidebar=False,
    )

    preflight = next(command for command in plan["commands"] if command["id"] == "preflight")

    assert f"--output {PREFLIGHT_ARTIFACT}" in preflight["command"]
    assert "kubernetes_ops_preflight.json" not in preflight["command"]
    assert "kubernetes_ops_preflight_evidence.json" in preflight["command"]


def test_release_command_plan_exposes_local_demo_smoke_without_changing_production_next_step():
    plan = build_kubernetes_release_command_plan(
        production_evidence_checklist={
            "status": "not_required",
            "production_target": False,
            "core_references": [],
            "external_bundle": {"status": "missing"},
            "gap_summary": {
                "next_gap_id": "select_production_environment",
                "blocking_gap_count": 1,
                "next_command_ids": [],
            },
        },
        blocker_groups=[{"id": "production_scope", "count": 1}],
        can_enable_sidebar=False,
    )

    local_phase = next(phase for phase in plan["phases"] if phase["id"] == "local_demo_smoke")
    local_commands = {command["id"]: command for command in local_phase["commands"]}

    assert plan["recommended_next"]["id"] == "select_production_environment"
    assert local_commands["local_demo_fixture"]["scope"] == "local_demo"
    assert ".tools/k8s-provider-fixture.py" in local_commands["local_demo_fixture"]["command"]
    assert (
        local_commands["local_demo_seed"]["command"]
        == "python manage.py seed_kubernetes_ops_demo --username admin --admin-write"
    )
    assert all(command["scope"] == "local_demo" for command in local_phase["commands"])
