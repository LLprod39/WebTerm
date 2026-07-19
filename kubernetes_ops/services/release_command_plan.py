from __future__ import annotations

from typing import Any

from kubernetes_ops.services.release_preflight import PREFLIGHT_ARTIFACT

COMMANDS: dict[str, dict[str, str]] = {
    "local_demo_fixture": {
        "id": "local_demo_fixture",
        "label": "Start local Kubernetes provider fixture",
        "command": "python .tools/k8s-provider-fixture.py --host 127.0.0.1 --port 18090",
        "scope": "local_demo",
    },
    "local_demo_seed": {
        "id": "local_demo_seed",
        "label": "Seed local Kubernetes Ops demo inventory",
        "command": "python manage.py seed_kubernetes_ops_demo --username admin --admin-write",
        "scope": "local_demo",
    },
    "live_provider_smoke": {
        "id": "live_provider_smoke",
        "label": "Refresh live provider smoke evidence",
        "command": "docker compose exec -T backend python manage.py verify_kubernetes_ops_live_provider_smoke --output artifacts/kubernetes_ops_live_provider_smoke.json",
        "scope": "production_evidence",
    },
    "readonly_rbac_live": {
        "id": "readonly_rbac_live",
        "label": "Refresh live read-only RBAC proof",
        "command": "docker compose exec -T backend python manage.py verify_kubernetes_ops_readonly_rbac_live --output artifacts/kubernetes_ops_readonly_rbac_live_evidence.json",
        "scope": "production_evidence",
    },
    "interactive_transport_evidence": {
        "id": "interactive_transport_evidence",
        "label": "Refresh interactive transport prerequisites",
        "command": "docker compose exec -T backend python manage.py verify_kubernetes_ops_interactive_transport_evidence --output artifacts/kubernetes_ops_interactive_transport_evidence.json",
        "scope": "production_evidence",
    },
    "interactive_live_smoke": {
        "id": "interactive_live_smoke",
        "label": "Refresh interactive live-smoke evidence",
        "command": "docker compose exec -T backend python manage.py verify_kubernetes_ops_interactive_live_smoke --output artifacts/kubernetes_ops_interactive_live_smoke.json --no-fail",
        "scope": "production_evidence",
    },
    "interactive_production_controls": {
        "id": "interactive_production_controls",
        "label": "Refresh interactive production controls",
        "command": "docker compose exec -T backend python manage.py verify_kubernetes_ops_interactive_production_controls --output artifacts/kubernetes_ops_interactive_production_controls.json --no-fail",
        "scope": "production_evidence",
    },
    "production_action_evidence": {
        "id": "production_action_evidence",
        "label": "Refresh rollback/native verification evidence",
        "command": "docker compose exec -T backend python manage.py verify_kubernetes_ops_production_action_evidence --output artifacts/kubernetes_ops_production_action_evidence.json",
        "scope": "production_evidence",
    },
    "external_evidence_bundle": {
        "id": "external_evidence_bundle",
        "label": "Refresh external production evidence bundle",
        "command": "docker compose exec -T backend python manage.py verify_kubernetes_ops_external_evidence_bundle --output artifacts/kubernetes_ops_external_evidence_bundle.json --no-fail",
        "scope": "production_evidence",
    },
    "preflight": {
        "id": "preflight",
        "label": "Refresh required preflight checks",
        "command": f"docker compose exec -T backend python manage.py verify_kubernetes_ops_preflight --output {PREFLIGHT_ARTIFACT}",
        "scope": "release_artifact",
    },
    "release_evidence": {
        "id": "release_evidence",
        "label": "Refresh Kubernetes Ops release evidence",
        "command": "docker compose exec -T backend python manage.py verify_kubernetes_ops_release --output artifacts/kubernetes_ops_release_evidence.json --no-fail",
        "scope": "release_artifact",
    },
    "release_handoff": {
        "id": "release_handoff",
        "label": "Render operator handoff",
        "command": "docker compose exec -T backend python manage.py render_kubernetes_ops_release_handoff --evidence artifacts/kubernetes_ops_release_evidence.json --format markdown --output artifacts/kubernetes_ops_release_handoff.md",
        "scope": "release_artifact",
    },
}

PHASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("local_demo_smoke", "Local demo smoke", ("local_demo_fixture", "local_demo_seed")),
    (
        "production_prerequisites",
        "Production prerequisite evidence",
        (
            "live_provider_smoke",
            "readonly_rbac_live",
            "interactive_transport_evidence",
            "interactive_live_smoke",
            "interactive_production_controls",
            "production_action_evidence",
            "external_evidence_bundle",
        ),
    ),
    ("release_artifacts", "Release artifacts", ("preflight", "release_evidence", "release_handoff")),
)


def build_kubernetes_release_command_plan(
    *,
    production_evidence_checklist: dict[str, Any],
    blocker_groups: list[dict[str, Any]],
    can_enable_sidebar: bool,
) -> dict[str, Any]:
    missing_settings = [
        str(item.get("setting") or "")
        for item in production_evidence_checklist.get("core_references") or []
        if isinstance(item, dict) and item.get("required") and not item.get("present")
    ]
    blocked_groups = [str(item.get("id") or "") for item in blocker_groups if item.get("count")]
    recommended = _recommended_next(
        checklist=production_evidence_checklist,
        blocked_groups=blocked_groups,
        can_enable_sidebar=can_enable_sidebar,
        missing_settings=missing_settings,
    )
    return {
        "status": "ready" if can_enable_sidebar else "attention_required",
        "runs_live_checks": False,
        "note": "Commands are operator instructions only; this API does not execute them.",
        "recommended_next": recommended,
        "blocking_summary": _blocking_summary(
            checklist=production_evidence_checklist,
            blocked_groups=blocked_groups,
            missing_settings=missing_settings,
            recommended=recommended,
            can_enable_sidebar=can_enable_sidebar,
        ),
        "manual_steps": _manual_steps(production_evidence_checklist, missing_settings),
        "phases": [
            {
                "id": phase_id,
                "title": title,
                "commands": [dict(COMMANDS[command_id]) for command_id in command_ids],
            }
            for phase_id, title, command_ids in PHASES
        ],
        "commands": [dict(command) for command in COMMANDS.values()],
    }


def _recommended_next(
    *,
    checklist: dict[str, Any],
    blocked_groups: list[str],
    can_enable_sidebar: bool,
    missing_settings: list[str],
) -> dict[str, Any]:
    if can_enable_sidebar:
        return _command("release_handoff")
    if not checklist.get("production_target"):
        return {
            "type": "manual",
            "id": "select_production_environment",
            "label": "Select production release environment when production evidence is available.",
            "settings": ["KUBERNETES_OPS_RELEASE_ENVIRONMENT"],
        }
    if missing_settings:
        return {
            "type": "manual",
            "id": "set_production_evidence_refs",
            "label": "Set required production evidence refs before rerunning evidence commands.",
            "settings": missing_settings[:12],
        }
    if checklist.get("external_bundle", {}).get("status") != "ready":
        return _command("external_evidence_bundle")
    if "runtime_readiness" in blocked_groups:
        return _command("preflight")
    if "release_artifact" in blocked_groups or "release_evidence" in blocked_groups:
        return _command("release_evidence")
    if "production_scope" in blocked_groups:
        return _command("external_evidence_bundle")
    return _command("release_evidence")


def _blocking_summary(
    *,
    checklist: dict[str, Any],
    blocked_groups: list[str],
    missing_settings: list[str],
    recommended: dict[str, Any],
    can_enable_sidebar: bool,
) -> dict[str, Any]:
    gap = checklist.get("gap_summary") if isinstance(checklist.get("gap_summary"), dict) else {}
    return {
        "can_enable_sidebar": can_enable_sidebar,
        "production_target": bool(checklist.get("production_target")),
        "production_evidence_status": str(checklist.get("status") or ""),
        "production_blocking_gap_count": int(gap.get("blocking_gap_count") or 0),
        "blocked_group_count": len(blocked_groups),
        "blocked_groups": blocked_groups[:8],
        "missing_setting_count": len(missing_settings),
        "missing_settings": missing_settings[:12],
        "next_gap_id": str(gap.get("next_gap_id") or ""),
        "next_command_ids": [str(item) for item in list(gap.get("next_command_ids") or [])[:6]],
        "recommended_next_id": str(recommended.get("id") or ""),
        "recommended_next_type": str(recommended.get("type") or ""),
    }


def _command(command_id: str) -> dict[str, Any]:
    payload = dict(COMMANDS[command_id])
    payload["type"] = "command"
    return payload


def _manual_steps(checklist: dict[str, Any], missing_settings: list[str]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    if not checklist.get("production_target"):
        steps.append(
            {
                "id": "select_production_environment",
                "label": "Set KUBERNETES_OPS_RELEASE_ENVIRONMENT=production only for a real production release.",
                "settings": ["KUBERNETES_OPS_RELEASE_ENVIRONMENT"],
            }
        )
    if missing_settings:
        steps.append(
            {
                "id": "set_production_evidence_refs",
                "label": "Set missing production evidence refs; do not paste secret values into the UI.",
                "settings": missing_settings[:12],
            }
        )
    return steps
