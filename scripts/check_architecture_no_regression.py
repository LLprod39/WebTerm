#!/usr/bin/env python3
"""Block new architecture debt while the frozen legacy debt is removed."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from architecture_guard_config import ArchitectureConfig  # noqa: E402
from architecture_guard_scan import ProjectScanner  # noqa: E402
from architecture_guard_size import DefaultSizeValidator  # noqa: E402


def parse_import_edges(output: str) -> set[str]:
    edges: set[str] = set()
    for raw in re.findall(r"(?m)^-\s+(.+?\s+->\s+.+?)(?:\s+\(l\.[^)]+\))?\s*$", output):
        edges.add(" ".join(raw.split()))
    return edges


def _lint_imports_command() -> str:
    executable_name = "lint-imports.exe" if sys.platform == "win32" else "lint-imports"
    candidates = (
        Path(sys.executable).parent / executable_name,
        ROOT / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / executable_name,
    )
    for executable in candidates:
        if executable.exists():
            return str(executable)
    return shutil.which("lint-imports") or "lint-imports"


def current_state(root: Path) -> dict[str, Any]:
    config = ArchitectureConfig.from_toml(str(root / "pyproject.toml"))
    metrics = ProjectScanner(config, DefaultSizeValidator()).scan(str(root))
    size_violations = {
        metric.path.replace("\\", "/").lstrip("./"): metric.lines for metric in metrics if not metric.passed
    }
    result = subprocess.run(
        [_lint_imports_command(), "--no-cache"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    combined = f"{result.stdout}\n{result.stderr}"
    import_edges = parse_import_edges(combined)
    if result.returncode not in (0, 1):
        raise RuntimeError(combined.strip() or "lint-imports could not run")
    if result.returncode == 1 and not import_edges:
        raise RuntimeError("lint-imports failed without parseable violation edges")
    return {"sizeViolations": size_violations, "importEdges": sorted(import_edges)}


def compare(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    allowed_sizes: dict[str, int] = baseline["architecture"]["sizeViolations"]
    for path, lines in current["sizeViolations"].items():
        if path not in allowed_sizes:
            errors.append(f"new size violation: {path} ({lines} lines)")
        elif lines > allowed_sizes[path]:
            errors.append(f"legacy size violation grew: {path} {allowed_sizes[path]} -> {lines}")
    allowed_edges = set(baseline["architecture"]["importEdges"])
    for edge in current["importEdges"]:
        if edge not in allowed_edges:
            errors.append(f"new forbidden import edge: {edge}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=Path("config/quality-debt-baseline.json"))
    parser.add_argument("--output", type=Path, default=Path(".ci-artifacts/architecture-no-regression.json"))
    args = parser.parse_args()
    baseline_path = args.baseline if args.baseline.is_absolute() else ROOT / args.baseline
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    try:
        current = current_state(ROOT)
        errors = compare(baseline, current)
    except (OSError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        errors = [f"architecture no-regression check could not run: {exc}"]
        current = {"sizeViolations": {}, "importEdges": []}
    report = {
        "baselineCommit": baseline.get("baselineCommit"),
        "state": "passed" if not errors else "failed",
        "current": current,
        "errors": errors,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if errors:
        print("Architecture no-regression: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "Architecture no-regression: PASS "
        f"({len(current['sizeViolations'])} frozen size violations, {len(current['importEdges'])} frozen import edges)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
