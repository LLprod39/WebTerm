"""F-10 mutation negative-test matrix and supply-chain scaffold smoke.

Heavy HTTP mutation coverage lives in domain suites (kubernetes_ops action
lifecycle, admin actions, core_ui smoke). This module:

1. Asserts the documented matrix and security process files exist.
2. Smoke-tests SBOM / checksum / provenance generators.
3. Pins a minimal denied-permission style contract via redaction + policy docs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


REQUIRED_SECURITY_DOCS = [
    REPO / "SECURITY.md",
    REPO / "THIRD_PARTY_NOTICES.md",
    REPO / "security" / "THREAT_MODEL.md",
    REPO / "security" / "FINDINGS_LEDGER.md",
]

# Representative domain tests that already encode mutation negatives.
MUTATION_COVERAGE_MARKERS = [
    REPO / "tests" / "test_kubernetes_ops_action_lifecycle.py",
    REPO / "tests" / "test_kubernetes_ops_admin_actions.py",
    REPO / "tests" / "test_egress_redaction.py",
    REPO / "tests" / "test_core_ui_api_smoke.py",
]


def test_security_process_documents_exist():
    missing = [str(path.relative_to(REPO)) for path in REQUIRED_SECURITY_DOCS if not path.is_file()]
    assert not missing, f"Missing security process docs: {missing}"


def test_findings_ledger_records_dependency_remediation():
    text = (REPO / "security" / "FINDINGS_LEDGER.md").read_text(encoding="utf-8")
    assert "DEP-NPM-001" in text
    assert "DEP-NPM-002" in text
    assert "DEP-NPM-003" in text
    assert "owner" in text.lower()
    assert "expiry" in text.lower()
    assert "compensating" in text.lower()


def test_threat_model_covers_f03_surfaces():
    text = (REPO / "security" / "THREAT_MODEL.md").read_text(encoding="utf-8")
    for needle in (
        "Auth",
        "SSH",
        "WebSocket",
        "pipeline",
        "MCP",
        "Plugin",
        "secrets",
        "Kubernetes",
    ):
        assert needle.lower() in text.lower(), f"Threat model missing surface: {needle}"


@pytest.mark.parametrize("path", MUTATION_COVERAGE_MARKERS, ids=lambda p: p.name)
def test_mutation_negative_suites_present(path: Path):
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    # Each suite must exercise at least one deny / redact style assertion.
    assert ("403" in content) or ("redact" in content.lower()) or ("denied" in content.lower())


def test_generate_sbom_checksums_and_provenance(tmp_path: Path):
    sbom_dir = tmp_path / "sbom"
    checksums_dir = tmp_path / "checksums"
    provenance_path = tmp_path / "provenance" / "provenance.intoto.json"

    sbom = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "generate_sbom.py"),
            "--output-dir",
            str(sbom_dir),
            "--repo-root",
            str(REPO),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert sbom.returncode == 0, sbom.stderr or sbom.stdout

    backend = sbom_dir / "sbom-backend.cdx.json"
    frontend = sbom_dir / "sbom-frontend.cdx.json"
    containers = sbom_dir / "sbom-containers.cdx.json"
    assert backend.is_file() and backend.stat().st_size > 0
    assert frontend.is_file() and frontend.stat().st_size > 0
    assert containers.is_file() and containers.stat().st_size > 0

    backend_doc = json.loads(backend.read_text(encoding="utf-8"))
    frontend_doc = json.loads(frontend.read_text(encoding="utf-8"))
    assert backend_doc["bomFormat"] == "CycloneDX"
    assert frontend_doc["bomFormat"] == "CycloneDX"
    assert len(backend_doc.get("components") or []) >= 1
    assert len(frontend_doc.get("components") or []) >= 1

    checksums = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "generate_release_checksums.py"),
            "--input-dir",
            str(sbom_dir),
            "--output",
            str(checksums_dir / "SHA256SUMS.txt"),
            "--repo-root",
            str(REPO),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert checksums.returncode == 0, checksums.stderr or checksums.stdout
    sums = checksums_dir / "SHA256SUMS.txt"
    assert sums.is_file()
    assert sums.read_text(encoding="utf-8").strip()

    provenance = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "generate_provenance.py"),
            "--artifacts-dir",
            str(sbom_dir),
            "--checksums",
            str(checksums_dir),
            "--output",
            str(provenance_path),
            "--repo-root",
            str(REPO),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert provenance.returncode == 0, provenance.stderr or provenance.stdout
    statement = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert statement["_type"] == "https://in-toto.io/Statement/v1"
    assert statement["predicateType"] == "https://slsa.dev/provenance/v1"
    assert statement["subject"]
    assert statement["predicate"]["buildDefinition"]["internalParameters"]["signature_status"] == "unsigned_scaffold"

    # CI path: mark as GitHub-attested and embed attestation metadata.
    signed_path = provenance_path.parent / "provenance.signed.intoto.json"
    signed = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "generate_provenance.py"),
            "--artifacts-dir",
            str(sbom_dir),
            "--checksums",
            str(checksums_dir),
            "--output",
            str(signed_path),
            "--repo-root",
            str(REPO),
            "--signature-status",
            "github_attestation",
            "--attestation-id",
            "test-attestation-id",
            "--attestation-url",
            "https://example.test/attestations/1",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert signed.returncode == 0, signed.stderr or signed.stdout
    signed_doc = json.loads(signed_path.read_text(encoding="utf-8"))
    assert signed_doc["webterm"]["signature_status"] == "github_attestation"
    assert (
        signed_doc["predicate"]["buildDefinition"]["internalParameters"]["attestation"]["id"] == "test-attestation-id"
    )
    sidecar = signed_path.parent / "github-attestation.json"
    assert sidecar.is_file()
    sidecar_doc = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_doc["signature_status"] == "github_attestation"
    assert sidecar_doc["subjects"]

    # Image flag without Syft/Trivy must not fail; may write pending note.
    image_run = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "generate_sbom.py"),
            "--output-dir",
            str(tmp_path / "sbom-images"),
            "--repo-root",
            str(REPO),
            "--image",
            "example.local/webterm@sha256:deadbeef",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert image_run.returncode == 0, image_run.stderr or image_run.stdout
    image_dir = tmp_path / "sbom-images"
    assert (image_dir / "sbom-containers.cdx.json").is_file()
    # Either a real image SBOM or a pending note when scanners are absent.
    has_image = any(image_dir.glob("sbom-image-*.cdx.json"))
    has_pending = (image_dir / "IMAGE_SBOM_PENDING.md").is_file()
    assert has_image or has_pending
