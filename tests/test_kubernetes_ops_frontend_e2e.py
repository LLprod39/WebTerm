from __future__ import annotations

import pytest

from kubernetes_ops.services.frontend_e2e import REQUIRED_FRONTEND_E2E_EVIDENCE, kubernetes_frontend_e2e_check


def _write_evidence_tree(root):
    spec_path = root / "frontend/e2e/visual.spec.ts"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text("\n".join(item.spec_token for item in REQUIRED_FRONTEND_E2E_EVIDENCE), encoding="utf-8")
    for item in REQUIRED_FRONTEND_E2E_EVIDENCE:
        snapshot_path = root / item.snapshot_path
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_bytes(b"\x89PNG\r\n" + (b"0" * 2048))


@pytest.mark.django_db
def test_kubernetes_frontend_e2e_check_ready_when_spec_and_snapshots_exist(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    _write_evidence_tree(tmp_path)

    check = kubernetes_frontend_e2e_check()

    assert check["id"] == "frontend_e2e"
    assert check["status"] == "ready"
    assert check["required"] is False


@pytest.mark.django_db
def test_kubernetes_frontend_e2e_check_manual_when_snapshot_missing(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    _write_evidence_tree(tmp_path)
    missing_snapshot = tmp_path / REQUIRED_FRONTEND_E2E_EVIDENCE[0].snapshot_path
    missing_snapshot.unlink()

    check = kubernetes_frontend_e2e_check()

    assert check["status"] == "manual"
    assert REQUIRED_FRONTEND_E2E_EVIDENCE[0].snapshot_path in check["detail"]
