from __future__ import annotations

import json

from django.contrib.auth.models import User

from core_ui.models import UserAppPermission


def _grant_kubernetes(user: User) -> None:
    UserAppPermission.objects.create(user=user, feature="kubernetes", allowed=True)


def _write_release_artifact(tmp_path, payload: dict) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "kubernetes_ops_release_evidence.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_external_bundle(tmp_path, payload: dict) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    (artifact_dir / "kubernetes_ops_external_evidence_bundle.json").write_text(json.dumps(payload), encoding="utf-8")
