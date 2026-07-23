from __future__ import annotations

from kubernetes_ops.services.release_handoff_plan import build_kubernetes_handoff_execution_plan


def _handoff(required_commands: list[dict[str, str]]) -> dict:
    return {
        "can_enable_sidebar": False,
        "release_scope": {
            "status": "local",
            "target_environment": "local",
            "approval_ref_present": False,
            "missing_required_references": [],
            "local_indicator_count": 0,
        },
        "evidence": {
            "artifact_status": "ready",
            "production_ready": False,
            "ready_for_sidebar": False,
        },
        "completion_audit": {
            "production_evidence_complete": False,
            "sidebar_enablement_complete": False,
        },
        "required_commands": required_commands,
        "production_env_flags": [],
    }


def test_handoff_execution_plan_deduplicates_preflight_alias_commands():
    plan = build_kubernetes_handoff_execution_plan(
        _handoff(
            [
                {
                    "id": "preflight_evidence",
                    "command": "python manage.py verify_kubernetes_ops_preflight --output artifacts/kubernetes_ops_preflight_evidence.json",
                },
                {
                    "id": "preflight",
                    "command": "docker compose exec -T backend python manage.py verify_kubernetes_ops_preflight --output artifacts/kubernetes_ops_preflight_evidence.json",
                },
                {
                    "id": "release_evidence",
                    "command": "python manage.py verify_kubernetes_ops_release --output artifacts/kubernetes_ops_release_evidence.json",
                },
                {
                    "id": "release_handoff",
                    "command": "python manage.py render_kubernetes_ops_release_handoff --output artifacts/kubernetes_ops_release_handoff.md",
                },
            ]
        )
    )

    release_phase = next(phase for phase in plan["phases"] if phase["id"] == "generate_release_artifacts")
    command_ids = [command["id"] for command in release_phase["commands"]]

    assert command_ids == ["preflight_evidence", "release_evidence", "release_handoff"]
    assert release_phase["command_count"] == 3
    assert plan["command_count"] == 3


def test_handoff_execution_plan_keeps_settings_preflight_command_when_contract_alias_is_absent():
    plan = build_kubernetes_handoff_execution_plan(
        _handoff(
            [
                {
                    "id": "preflight",
                    "command": "docker compose exec -T backend python manage.py verify_kubernetes_ops_preflight --output artifacts/kubernetes_ops_preflight_evidence.json",
                },
                {
                    "id": "release_evidence",
                    "command": "docker compose exec -T backend python manage.py verify_kubernetes_ops_release --output artifacts/kubernetes_ops_release_evidence.json",
                },
                {
                    "id": "release_handoff",
                    "command": "docker compose exec -T backend python manage.py render_kubernetes_ops_release_handoff --output artifacts/kubernetes_ops_release_handoff.md",
                },
            ]
        )
    )

    release_phase = next(phase for phase in plan["phases"] if phase["id"] == "generate_release_artifacts")
    command_ids = [command["id"] for command in release_phase["commands"]]

    assert command_ids == ["preflight", "release_evidence", "release_handoff"]
    assert release_phase["command_count"] == 3
    assert plan["command_count"] == 3


def test_handoff_execution_plan_blocks_when_requested_ready_but_completion_is_incomplete():
    handoff = _handoff([])
    handoff["can_enable_sidebar"] = True
    handoff["release_scope"].update(
        {
            "status": "ready",
            "target_environment": "production",
            "approval_ref_present": True,
            "missing_required_references": [],
            "local_indicator_count": 0,
        }
    )
    handoff["evidence"].update({"production_ready": True, "ready_for_sidebar": True})

    plan = build_kubernetes_handoff_execution_plan(handoff)

    assert plan["status"] == "blocked"
    assert plan["can_enable_sidebar"] is False
    blocked_ids = {item["id"] for item in plan["blocked_until"]}
    assert {"production_evidence_complete", "sidebar_enablement_complete"} <= blocked_ids
