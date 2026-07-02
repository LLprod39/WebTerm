from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings


@dataclass(frozen=True)
class FrontendE2EEvidence:
    name: str
    spec_token: str
    snapshot_path: str


REQUIRED_FRONTEND_E2E_EVIDENCE = (
    FrontendE2EEvidence(
        name="settings kubernetes page",
        spec_token='test("settings kubernetes page snapshot"',
        snapshot_path="frontend/e2e/visual.spec.ts-snapshots/settings-kubernetes-page-chromium-win32.png",
    ),
    FrontendE2EEvidence(
        name="kubernetes empty state",
        spec_token='test("kubernetes empty state snapshot"',
        snapshot_path="frontend/e2e/visual.spec.ts-snapshots/kubernetes-empty-state-chromium-win32.png",
    ),
    FrontendE2EEvidence(
        name="kubernetes healthy inventory",
        spec_token='test("kubernetes healthy inventory snapshot"',
        snapshot_path="frontend/e2e/visual.spec.ts-snapshots/kubernetes-healthy-inventory-chromium-win32.png",
    ),
    FrontendE2EEvidence(
        name="kubernetes degraded inventory",
        spec_token='test("kubernetes degraded inventory snapshot"',
        snapshot_path="frontend/e2e/visual.spec.ts-snapshots/kubernetes-degraded-inventory-chromium-win32.png",
    ),
)


def _repo_root() -> Path:
    return Path(settings.BASE_DIR).resolve()


def _snapshot_ok(root: Path, relative_path: str) -> bool:
    path = root / relative_path
    try:
        return path.is_file() and path.stat().st_size > 1024
    except OSError:
        return False


def kubernetes_frontend_e2e_check() -> dict[str, Any]:
    root = _repo_root()
    spec_path = root / "frontend/e2e/visual.spec.ts"
    missing: list[str] = []
    try:
        spec_text = spec_path.read_text(encoding="utf-8")
    except OSError:
        spec_text = ""
        missing.append("frontend/e2e/visual.spec.ts")

    for evidence in REQUIRED_FRONTEND_E2E_EVIDENCE:
        if evidence.spec_token not in spec_text:
            missing.append(f"{evidence.name} visual test")
        if not _snapshot_ok(root, evidence.snapshot_path):
            missing.append(evidence.snapshot_path)

    if missing:
        return {
            "id": "frontend_e2e",
            "status": "manual",
            "detail": "Frontend e2e evidence is incomplete: " + ", ".join(missing) + ".",
            "required": False,
        }
    return {
        "id": "frontend_e2e",
        "status": "ready",
        "detail": f"Frontend visual e2e evidence is present for {len(REQUIRED_FRONTEND_E2E_EVIDENCE)} Kubernetes states.",
        "required": False,
    }
