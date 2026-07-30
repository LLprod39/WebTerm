from __future__ import annotations

from architecture_guard_config import ArchitectureConfig, FileMetric
from architecture_guard_quality import QualityCheckResult


class GuardReport:
    """Formats and prints the combined result of all architecture checks."""

    def __init__(self, config: ArchitectureConfig) -> None:
        self._config = config

    def display(
        self,
        metrics: list[FileMetric],
        import_ok: bool,
        quality: QualityCheckResult,
    ) -> bool:
        size_failures = [m for m in metrics if not m.passed]
        size_warnings = [m for m in metrics if m.error_message]
        overall_ok = not size_failures and import_ok and quality.passed

        print("\n=== Architecture Fitness Check: Complexity & Coupling ===")
        print(f"Total files scanned: {len(metrics)}")
        print(
            "Python quality scan: "
            f"{quality.snapshot.modules_scanned} modules, "
            f"{quality.snapshot.functions_scanned} functions, "
            f"{quality.frozen_violations} frozen violations"
        )

        if size_warnings:
            print(f"\nWARNING: {len(size_warnings)} line-count signal(s) (non-blocking):")
            for metric in size_warnings:
                print(f"  [WARNING] {metric.path}")
                print(f"            {metric.error_message}")

        if overall_ok:
            print("SUCCESS: All architecture contracts satisfied.")
            return True

        if size_failures:
            print(f"FAILURE: {len(size_failures)} file(s) violated size limits:\n")
            for metric in size_failures:
                tag = "[LEGACY GROWTH]" if metric.is_legacy else "[GOD-FILE]"
                print(f"  {tag} {metric.path}")
                print(f"          {metric.error_message}")

        if quality.errors:
            print(f"FAILURE: {len(quality.errors)} complexity/coupling violation(s):\n")
            for error in quality.errors:
                print(f"  [QUALITY] {error}")

        if not import_ok:
            print(
                f"\nFAILURE: Import boundary violations detected — "
                f"see {self._config.contract_file} for the full contract set."
            )

        print(f"\nAction: Review {self._config.contract_file} and refactor accordingly.")
        return False
