from __future__ import annotations

from typing import Any


RELEASE_EVIDENCE_SCHEMA_VERSION = "kubernetes_ops.release_evidence.v2"


def build_kubernetes_release_contract() -> dict[str, Any]:
    return {
        "schema_version": RELEASE_EVIDENCE_SCHEMA_VERSION,
        "generated_by": "python manage.py verify_kubernetes_ops_release",
        "required_preflight_commands": [
            {
                "id": "django_check",
                "command": "python manage.py check",
                "purpose": "Django configuration and system checks pass before release evidence is trusted.",
            },
            {
                "id": "architecture_guard",
                "command": "python scripts/check_architecture_sizes.py --strict-new",
                "purpose": "Repository architecture guard stays green for new Kubernetes Ops code.",
            },
            {
                "id": "migrations_dry_run",
                "command": "python manage.py makemigrations kubernetes_ops --check --dry-run",
                "purpose": "Kubernetes Ops models have no uncommitted migration drift.",
            },
            {
                "id": "kubernetes_backend_tests",
                "command": "python -m pytest tests/test_kubernetes_ops_*.py",
                "timeout_seconds": 1200,
                "env": {"POSTGRES_STATEMENT_TIMEOUT_MS": "0"},
                "purpose": "Kubernetes Ops backend, safety, release and readiness tests pass together.",
            },
            {
                "id": "readonly_rbac_validate",
                "command": "python manage.py render_kubernetes_ops_readonly_rbac --validate-only",
                "purpose": "Generated read-only RBAC contract stays deny-by-default for write/exec paths.",
            },
            {
                "id": "sync_prune_safety",
                "command": "python manage.py verify_kubernetes_ops_sync_prune_safety",
                "purpose": "Local inventory pruning only deletes stale rows after a successful provider sync.",
            },
            {
                "id": "readonly_rbac_live",
                "command": "python scripts/verify_kubernetes_ops_readonly_rbac_live.py --apply",
                "purpose": "Live kubectl auth can-i proof confirms read allow and write/exec deny matrix.",
            },
            {
                "id": "local_platform_evidence",
                "command": "python scripts/verify_kubernetes_ops_local_platform.py --output artifacts/kubernetes_ops_local_platform_evidence.json",
                "purpose": "Local kind platform evidence proves Rancher, Fleet and Devtron namespaces/services/workloads are installed and ready for WebTerm provider integration tests.",
            },
            {
                "id": "live_provider_smoke",
                "command": "python manage.py verify_kubernetes_ops_live_provider_smoke --output artifacts/kubernetes_ops_live_provider_smoke.json",
                "purpose": "Live WebTerm provider evidence proves enabled Rancher/Fleet/Devtron providers answer probes and read-only dry-run sync returns clusters, Fleet bundles and Devtron apps.",
            },
            {
                "id": "interactive_transport_evidence",
                "command": "python manage.py verify_kubernetes_ops_interactive_transport_evidence --output artifacts/kubernetes_ops_interactive_transport_evidence.json",
                "purpose": "Interactive exec, port-forward, cluster terminal and node-debug production prerequisites are captured without opening a live stream.",
            },
            {
                "id": "interactive_live_smoke",
                "command": "python manage.py verify_kubernetes_ops_interactive_live_smoke --output artifacts/kubernetes_ops_interactive_live_smoke.json",
                "purpose": "Interactive exec, port-forward, cluster terminal and node-debug provider openers are smoke-tested with simulated streams, while production live-stream proof stays an external evidence reference.",
            },
            {
                "id": "interactive_production_controls",
                "command": "python manage.py verify_kubernetes_ops_interactive_production_controls --output artifacts/kubernetes_ops_interactive_production_controls.json",
                "purpose": "Restricted credential, recording, provider-contract and port-forward network-policy production controls are captured without opening live streams.",
            },
            {
                "id": "production_action_evidence",
                "command": "python manage.py verify_kubernetes_ops_production_action_evidence --output artifacts/kubernetes_ops_production_action_evidence.json",
                "purpose": "Production rollback drill and native verification evidence refs are captured without mutating the cluster.",
            },
            {
                "id": "external_evidence_bundle",
                "command": "python manage.py verify_kubernetes_ops_external_evidence_bundle --output artifacts/kubernetes_ops_external_evidence_bundle.json",
                "purpose": "Production promotion evidence refs and prerequisite artifacts are captured in one fail-closed external evidence bundle.",
            },
            {
                "id": "release_evidence",
                "command": "python manage.py verify_kubernetes_ops_release --username <staff-user> --output artifacts/kubernetes_ops_release_evidence.json",
                "purpose": "Collect bounded promotion artifact for provider, sync, MCP, action-control, Admin Mode safety and release-scope evidence.",
            },
            {
                "id": "preflight_evidence",
                "command": "python manage.py verify_kubernetes_ops_preflight --output artifacts/kubernetes_ops_preflight_evidence.json",
                "purpose": "Write bounded evidence that required release preflight commands passed before promotion.",
            },
            {
                "id": "release_handoff",
                "command": "python manage.py render_kubernetes_ops_release_handoff --output artifacts/kubernetes_ops_release_handoff.md",
                "purpose": "Render the operator-facing production handoff checklist from release evidence without approving production by itself.",
            },
        ],
    }
