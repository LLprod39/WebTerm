#!/usr/bin/env python3
"""Validate the authoritative documentation and release-contract links."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
AUTHORITATIVE_DOCS = (
    "README.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "docs/architecture/ARCHITECTURE_CONTRACT.md",
    "docs/architecture/CI_GOVERNANCE.md",
    "docs/architecture/KUBERNETES_OPS_OPERATIONS.md",
    "docs/architecture/WEBTERM_OPERATIONS_CONTROL_PLANE_ROADMAP.md",
    "docs/architecture/adr/README.md",
    "docs/architecture/adr/0001-primary-runtime-and-toolchain.md",
    "docs/architecture/adr/0002-public-version-reset.md",
    "docs/pilot/PILOT_UX_SCRIPT_V1.md",
    "docs/pilot/PILOT_UX_RESULTS_V1.template.json",
    "docs/releases/README.md",
    "docs/releases/BRAND_COMPATIBILITY.md",
    "docs/releases/OPERATIONS_RUNBOOK.md",
    "docs/releases/PUBLIC_API_V0_1.md",
    "docs/releases/SUPPORT_MATRIX.md",
    "docs/releases/V0_1_RELEASE_SCOPE.md",
    "docs/releases/V0_1_RELEASE_CHECKLIST.md",
    "docs/releases/V0_1_PERFORMANCE_BUDGET.md",
    "docs/releases/V0_2_1_RELEASE_NOTES.md",
    "docs/releases/V0_2_2_RELEASE_NOTES.md",
    "docs/releases/V0_2_RELEASE_CHECKLIST.md",
    "docs/releases/V0_2_RELEASE_SCOPE.md",
)
REQUIRED_DOMAINS = {
    "Servers inventory and access",
    "SSH terminal and files",
    "Monitoring and alerts",
    "Playbooks",
    "Agents",
    "Chat/operator orchestration",
    "Studio pipelines",
    "MCP integrations",
    "Plugins",
    "Kubernetes Ops",
    "MARS",
}
REQUIRED_STATUSES = {"GA", "preview", "disabled"}


def _local_links(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    links = []
    for raw in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text):
        target = raw.strip().split(maxsplit=1)[0].strip("<>")
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        links.append(unquote(target.split("#", 1)[0]))
    return links


def verify(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for relative in AUTHORITATIVE_DOCS:
        path = root / relative
        if not path.is_file():
            errors.append(f"missing authoritative document: {relative}")
            continue
        for target in _local_links(path):
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                errors.append(f"broken local link in {relative}: {target}")

    scope_path = root / "docs/releases/V0_2_RELEASE_SCOPE.md"
    if scope_path.is_file():
        scope = scope_path.read_text(encoding="utf-8")
        for domain in sorted(REQUIRED_DOMAINS):
            if f"| {domain} |" not in scope:
                errors.append(f"release scope is missing domain: {domain}")
        observed_statuses = set(re.findall(r"\| (GA|preview|disabled) \|", scope))
        if observed_statuses != REQUIRED_STATUSES:
            errors.append(f"release scope statuses are incomplete: {sorted(observed_statuses)}")

    support_path = root / "docs/releases/SUPPORT_MATRIX.md"
    if support_path.is_file():
        support = support_path.read_text(encoding="utf-8")
        for value in ("3.11.15", "5.2.16", "22.23.1", "10.9.8", "PostgreSQL", "Redis", "Playwright 1.58.2"):
            if value not in support:
                errors.append(f"support matrix is missing: {value}")

    checklist_path = root / "docs/releases/V0_2_RELEASE_CHECKLIST.md"
    if checklist_path.is_file():
        checklist = checklist_path.read_text(encoding="utf-8")
        for command in (
            "python scripts/verify_runtime_contract.py",
            "python scripts/check_architecture_sizes.py --strict-new",
            "npm run typecheck",
            "npm run test:e2e",
            "npm run performance:budget",
            "npm run test:e2e:performance",
            "python scripts/verify_pilot_ux_results.py",
            "./docker/production-install-smoke.sh",
            "python scripts/collect_release_evidence.py",
        ):
            if command not in checklist:
                errors.append(f"release checklist is missing command: {command}")

    version_path = root / "VERSION"
    if not version_path.is_file():
        errors.append("missing release version file: VERSION")
    elif version_path.read_text(encoding="utf-8").strip() != "0.2.3":
        errors.append("VERSION must declare 0.2.3")

    api_inventory = root / "config/public-api-v0.1.json"
    if not api_inventory.is_file():
        errors.append("missing public API inventory: config/public-api-v0.1.json")
    return errors


def main() -> int:
    errors = verify(ROOT)
    if errors:
        print("Documentation contract: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Documentation contract: PASS ({len(AUTHORITATIVE_DOCS)} documents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
