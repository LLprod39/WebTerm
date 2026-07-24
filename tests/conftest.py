from __future__ import annotations

import pytest

pytest_plugins = ("tests.playbook_workspace_support",)

_RELEASE_EVIDENCE_TEST_MODULES = frozenset(
    {
        "test_kubernetes_ops_release_evidence.py",
        "test_kubernetes_ops_release_evidence_redaction.py",
    }
)


@pytest.fixture(autouse=True)
def _ready_interactive_live_smoke_for_release_evidence_tests(monkeypatch, request):
    if request.node.fspath.basename not in _RELEASE_EVIDENCE_TEST_MODULES:
        return
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._interactive_live_smoke_evidence",
        lambda _enabled: {
            "success": True,
            "status": "ready",
            "summary": {
                "simulated_check_count": 4,
                "live_smoke_required": False,
                "production_live_provider_evidence": False,
            },
        },
    )
    monkeypatch.setattr(
        "kubernetes_ops.services.release_evidence._external_evidence_bundle",
        lambda _enabled: {
            "success": True,
            "status": "ready",
            "summary": {
                "missing_required_ref_count": 0,
                "artifact_ready_count": 5,
                "artifact_check_count": 5,
                "local_indicator_count": 0,
            },
        },
    )
