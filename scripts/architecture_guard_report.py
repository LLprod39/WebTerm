from __future__ import annotations

from architecture_guard_config import ArchitectureConfig, FileMetric


class GuardReport:
    """Formats and prints the combined result of all architecture checks."""

    def __init__(self, config: ArchitectureConfig) -> None:
        self._config = config

    def display(self, metrics: list[FileMetric], import_ok: bool) -> bool:
        size_failures = [m for m in metrics if not m.passed]
        size_warnings = [m for m in metrics if m.passed and not m.is_legacy and m.error_message]
        overall_ok = not size_failures and import_ok

        print("\n=== Architecture Fitness Check: God-File Prevention ===")
        print(f"Total files scanned: {len(metrics)}")

        if size_warnings:
            print(f"\nWARNING: {len(size_warnings)} file(s) exceed the standard limit (non-blocking):")
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

        if not import_ok:
            print(
                f"\nFAILURE: Import boundary violations detected — "
                f"see {self._config.contract_file} for the full contract set."
            )

        print(f"\nAction: Review {self._config.contract_file} and refactor accordingly.")
        return False
