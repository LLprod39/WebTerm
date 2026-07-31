from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_kubernetes_and_mars_boundary_is_an_accepted_indexed_decision() -> None:
    adr_path = ROOT / "docs" / "architecture" / "adr" / "0003-kubernetes-ops-and-mars-boundary.md"
    adr = adr_path.read_text(encoding="utf-8")
    index = (adr_path.parent / "README.md").read_text(encoding="utf-8")
    release_scope = (ROOT / "docs" / "releases" / "V0_2_RELEASE_SCOPE.md").read_text(encoding="utf-8")

    assert "Status: Accepted" in adr
    assert "optional bounded contexts" in adr
    assert "separate release cycle" in adr
    assert "recalculated" in adr and "coverage" in adr
    assert "0003-kubernetes-ops-and-mars-boundary.md" in index
    assert "| Kubernetes Ops | disabled |" in release_scope
    assert "| MARS | disabled |" in release_scope
