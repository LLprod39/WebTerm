#!/usr/bin/env python3
"""
Architecture boundary fitness checker.

Enforces the structural constraints defined in docs/local/ARCHITECTURE_CONTRACT.md:
  1. God-file prevention — file line-count limits with legacy baselines.
  2. Import boundary validation — delegates to ``lint-imports`` (import-linter).

Usage:
    python scripts/check_architecture_sizes.py
    python scripts/check_architecture_sizes.py --config path/to/pyproject.toml
    python scripts/check_architecture_sizes.py --root src/
    python scripts/check_architecture_sizes.py --update-baseline
        Scan the project and pin every file currently over the standard limit
        into [tool.architecture.legacy_baselines] in pyproject.toml.  Use this
        ONCE before starting a refactoring effort to freeze the current state.
    python scripts/check_architecture_sizes.py --strict-new
        Treat any *new* (non-legacy) file above the strict limit as a hard
        failure instead of the default soft GOD-FILE warning.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Final

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]  # pip install tomli


# ---------------------------------------------------------------------------
# Path utility
# ---------------------------------------------------------------------------


class PathNormalizer:
    """
    Centralises the rule for converting raw filesystem paths into the
    canonical ``./forward/slash`` form used throughout the codebase.

    Keeping this in its own class prevents the normalisation logic from
    being scattered across :class:`ArchitectureConfig` and
    :class:`DefaultSizeValidator`.
    """

    @staticmethod
    def normalize(path: str) -> str:
        """Return *path* with back-slashes replaced and prefixed with ``'./'``."""
        p = path.replace("\\", "/").lstrip("/")
        return p if p.startswith("./") else "./" + p


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileMetric:
    """Immutable snapshot of a single file's size-check outcome."""

    path: str
    lines: int
    is_legacy: bool
    limit: int
    passed: bool
    error_message: str = ""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


_DEFAULT_EXCLUDE_DIRS: Final[frozenset[str]] = frozenset(
    {
        "node_modules",
        "venv",
        "migrations",
        "dist",
        ".git",
        ".ruff_cache",
        "__pycache__",
    }
)

_DEFAULT_EXCLUDE_FRAGMENTS: Final[frozenset[str]] = frozenset(
    {"production-upload-bundle"}
)

_DEFAULT_EXTENSIONS: Final[frozenset[str]] = frozenset({".py", ".ts", ".tsx"})


@dataclass(frozen=True)
class ArchitectureConfig:
    """
    Immutable configuration for all architecture checks.

    Loaded from ``pyproject.toml`` via :meth:`from_toml`.  Defaults are set
    so the checker is functional even without a config file (CI bootstrap).

    The class is ``frozen=True`` so it can be safely shared across threads
    and passed by reference without risk of accidental mutation.
    """

    standard_limit: int = 500
    strict_limit: int = 1000
    enforce_import_boundaries: bool = False
    strict_new_files: bool = False
    contract_file: str = "docs/local/ARCHITECTURE_CONTRACT.md"
    legacy_baselines: dict[str, int] = field(default_factory=dict)
    exclude_dirs: frozenset[str] = field(default_factory=lambda: _DEFAULT_EXCLUDE_DIRS)
    exclude_path_fragments: frozenset[str] = field(
        default_factory=lambda: _DEFAULT_EXCLUDE_FRAGMENTS
    )
    extensions: frozenset[str] = field(default_factory=lambda: _DEFAULT_EXTENSIONS)

    @classmethod
    def from_toml(cls, config_path: str = "pyproject.toml") -> ArchitectureConfig:
        """
        Factory: parse *config_path* and return a fully-populated instance.

        Falls back gracefully to defaults when the file is missing or
        contains an unreadable ``[tool.architecture]`` section.
        """
        if not os.path.exists(config_path):
            return cls()

        try:
            with open(config_path, "rb") as fh:
                data = tomllib.load(fh)

            arch: dict = data.get("tool", {}).get("architecture", {})
            return cls(
                standard_limit=arch.get("standard_limit", 500),
                strict_limit=arch.get("strict_limit", 1000),
                enforce_import_boundaries=arch.get("enforce_import_boundaries", False),
                strict_new_files=arch.get("strict_new_files", False),
                contract_file=arch.get("contract_file", "docs/local/ARCHITECTURE_CONTRACT.md"),
                legacy_baselines={
                    PathNormalizer.normalize(k): v
                    for k, v in arch.get("legacy_baselines", {}).items()
                },
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"Warning: could not load architecture config from {config_path}: {exc}"
            )
            return cls()


# ---------------------------------------------------------------------------
# Validator interface and default implementation
# ---------------------------------------------------------------------------


class ISizeValidator(ABC):
    """Strategy interface for file-size validation logic."""

    @abstractmethod
    def validate(self, path: str, lines: int, config: ArchitectureConfig) -> FileMetric:
        """Return a :class:`FileMetric` describing whether *path* passes."""


class DefaultSizeValidator(ISizeValidator):
    """
    Enforces two tiers of size rules:

    * **Legacy files** — pinned to their recorded baseline; must not grow.
    * **New files** — must stay below ``config.standard_limit``.  Files that
      also exceed ``config.strict_limit`` are flagged as CRITICAL GOD-FILEs.
    """

    def validate(self, path: str, lines: int, config: ArchitectureConfig) -> FileMetric:
        norm_path = PathNormalizer.normalize(path)
        baseline = config.legacy_baselines.get(norm_path)

        if baseline is not None:
            return self._check_legacy(path, lines, baseline)

        return self._check_new_file(path, lines, config)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_legacy(path: str, lines: int, baseline: int) -> FileMetric:
        passed = lines <= baseline
        error = f"Legacy file grew: {lines} > {baseline}" if not passed else ""
        return FileMetric(path, lines, is_legacy=True, limit=baseline, passed=passed, error_message=error)

    @staticmethod
    def _check_new_file(path: str, lines: int, config: ArchitectureConfig) -> FileMetric:
        passed = lines <= config.standard_limit
        if passed:
            return FileMetric(path, lines, is_legacy=False, limit=config.standard_limit, passed=True)

        is_critical = lines > config.strict_limit
        severity = "CRITICAL GOD-FILE" if is_critical else "GOD-FILE"
        error = f"{severity}: {lines} > {config.standard_limit}"
        # Hard-fail logic:
        #   * CRITICAL GOD-FILE (above strict_limit) → always a hard failure.
        #   * GOD-FILE (between standard_limit and strict_limit) → hard failure
        #     only when --strict-new / strict_new_files=true is active;
        #     otherwise it is a warning (passes the check but is printed).
        hard_fail = is_critical or config.strict_new_files
        return FileMetric(
            path, lines, is_legacy=False, limit=config.standard_limit, passed=not hard_fail,
            error_message=error,
        )


# ---------------------------------------------------------------------------
# Project scanner
# ---------------------------------------------------------------------------


class ProjectScanner:
    """Walks the project tree and produces :class:`FileMetric` results."""

    def __init__(self, config: ArchitectureConfig, validator: ISizeValidator) -> None:
        self._config = config
        self._validator = validator

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self, root_dir: str = ".") -> list[FileMetric]:
        """Return metrics for all tracked files under *root_dir*."""
        metrics: list[FileMetric] = []

        for dirpath, dirnames, filenames in os.walk(root_dir):
            # Prune excluded directory names in-place so os.walk won't descend.
            dirnames[:] = [
                d for d in dirnames if d not in self._config.exclude_dirs
            ]

            if self._path_is_excluded(dirpath):
                continue

            for filename in filenames:
                if self._has_tracked_extension(filename):
                    full_path = os.path.join(dirpath, filename)
                    lines = self._count_lines(full_path)
                    metrics.append(self._validator.validate(full_path, lines, self._config))

        return metrics

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _path_is_excluded(self, dirpath: str) -> bool:
        norm = dirpath.replace("\\", "/")
        return any(fragment in norm for fragment in self._config.exclude_path_fragments)

    def _has_tracked_extension(self, filename: str) -> bool:
        _, ext = os.path.splitext(filename)
        return ext in self._config.extensions

    @staticmethod
    def _count_lines(path: str) -> int:
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                return sum(1 for _ in fh)
        except OSError as exc:
            print(f"Warning: could not read {path}: {exc}")
            return 0


# ---------------------------------------------------------------------------
# Import boundary checker
# ---------------------------------------------------------------------------


class ImportBoundaryChecker:
    """
    Delegates import-boundary enforcement to the ``lint-imports`` CLI tool
    (provided by the *import-linter* package).

    When ``config.enforce_import_boundaries`` is ``False`` this check is a
    no-op and returns ``True`` so downstream logic is unaffected.
    """

    _TOOL: Final[str] = "lint-imports"

    def __init__(self, config: ArchitectureConfig) -> None:
        self._config = config

    def check(self) -> bool:
        """Run ``lint-imports`` and return ``True`` on success."""
        if not self._config.enforce_import_boundaries:
            return True

        print("\n=== Checking Import Boundaries (import-linter) ===")
        tool = self._TOOL
        if os.name == "nt":
            import shutil
            if not shutil.which(tool):
                appdata = os.environ.get("APPDATA")
                if appdata:
                    import glob
                    candidates = glob.glob(os.path.join(appdata, "Python", "Python*", "Scripts", "lint-imports.exe"))
                    if candidates:
                        candidates.sort(reverse=True)
                        tool = candidates[0]

        try:
            result = subprocess.run(
                [tool, "--no-cache"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(result.stderr)
                return False

            print("SUCCESS: Import boundaries respected.")
            return True

        except FileNotFoundError:
            print(
                f"ERROR: '{tool}' not found — import boundary enforcement is enabled\n"
                "but the tool is not installed.  Run:  pip install import-linter\n"
                "Refusing to pass: import boundaries are NOT verified."
            )
            return False  # Hard fail: enforce_import_boundaries=true requires the tool to be present.

        except Exception as exc:  # noqa: BLE001
            print(f"Error running {self._TOOL}: {exc}")
            return False


# ---------------------------------------------------------------------------
# Baseline writer (--update-baseline mode)
# ---------------------------------------------------------------------------


class BaselineWriter:
    """
    Scans the project for files that exceed the standard line limit and writes
    (or updates) their current line counts as legacy baselines in
    ``[tool.architecture.legacy_baselines]`` inside ``pyproject.toml``.

    Use this **once** before beginning a major refactoring effort to freeze
    the current state.  Subsequent runs of the checker will enforce that these
    files may not grow beyond the pinned baseline.
    """

    def __init__(self, config_path: str, config: ArchitectureConfig) -> None:
        self._config_path = config_path
        self._config = config

    def write(self, metrics: list[FileMetric]) -> int:
        """
        Merge over-limit files into the legacy_baselines table in
        ``pyproject.toml``.  Returns the number of entries added or updated.
        """
        over_limit = [
            m for m in metrics
            if not m.is_legacy and m.lines > self._config.standard_limit
        ]
        # Also include legacy files that have grown beyond their baseline so
        # the user can choose to re-pin them at the new (higher) size.
        grown_legacy = [
            m for m in metrics
            if m.is_legacy and not m.passed
        ]
        candidates = over_limit + grown_legacy

        if not candidates:
            print("No files exceed the standard limit — baseline unchanged.")
            return 0

        try:
            with open(self._config_path, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            print(f"ERROR: Cannot read {self._config_path}: {exc}")
            return 0

        updated = 0
        for m in candidates:
            # Normalise to a relative key without leading './'.
            key = PathNormalizer.normalize(m.path).lstrip("./")
            line_count = m.lines
            quoted_key = f'"{key}"'
            # Try to update an existing entry.
            pattern = re.compile(
                rf'^({re.escape(quoted_key)}\s*=\s*)\d+',
                re.MULTILINE,
            )
            if pattern.search(raw):
                raw = pattern.sub(rf'\g<1>{line_count}', raw)
            else:
                # Append to the [tool.architecture.legacy_baselines] section.
                section_pattern = re.compile(
                    r'(\[tool\.architecture\.legacy_baselines\][^\[]*)',
                    re.DOTALL,
                )
                m_section = section_pattern.search(raw)
                if m_section:
                    insert_pos = m_section.end()
                    new_entry = f'{quoted_key} = {line_count}\n'
                    raw = raw[:insert_pos] + new_entry + raw[insert_pos:]
                else:
                    raw += f'\n[tool.architecture.legacy_baselines]\n{quoted_key} = {line_count}\n'
            updated += 1

        try:
            with open(self._config_path, "w", encoding="utf-8") as fh:
                fh.write(raw)
        except OSError as exc:
            print(f"ERROR: Cannot write {self._config_path}: {exc}")
            return 0

        print(f"Pinned {updated} file(s) into {self._config_path} legacy_baselines.")
        for m in candidates:
            key = PathNormalizer.normalize(m.path).lstrip("./")
            print(f"  {key} = {m.lines}")
        return updated


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------


class GuardReport:
    """Formats and prints the combined result of all architecture checks."""

    def __init__(self, config: ArchitectureConfig) -> None:
        self._config = config

    def display(self, metrics: list[FileMetric], import_ok: bool) -> bool:
        """
        Print a human-readable summary and return ``True`` iff all checks pass.
        """
        size_failures = [m for m in metrics if not m.passed]
        # Non-legacy files that exceeded standard_limit but did not hard-fail
        # (i.e. between standard_limit and strict_limit, strict-new mode off).
        size_warnings = [
            m for m in metrics
            if m.passed and not m.is_legacy and m.error_message
        ]
        overall_ok = not size_failures and import_ok

        print("\n=== Architecture Fitness Check: God-File Prevention ===")
        print(f"Total files scanned: {len(metrics)}")

        if size_warnings:
            print(f"\nWARNING: {len(size_warnings)} file(s) exceed the standard limit (non-blocking):")
            for m in size_warnings:
                print(f"  [WARNING] {m.path}")
                print(f"            {m.error_message}")

        if overall_ok:
            print("SUCCESS: All architecture contracts satisfied.")
            return True

        if size_failures:
            print(f"FAILURE: {len(size_failures)} file(s) violated size limits:\n")
            for m in size_failures:
                tag = "[LEGACY GROWTH]" if m.is_legacy else "[GOD-FILE]"
                print(f"  {tag} {m.path}")
                print(f"          {m.error_message}")

        if not import_ok:
            print(
                f"\nFAILURE: Import boundary violations detected — "
                f"see {self._config.contract_file} for the full contract set."
            )

        print(f"\nAction: Review {self._config.contract_file} and refactor accordingly.")
        return False


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check architecture fitness: file-size limits and import boundaries."
    )
    parser.add_argument(
        "--config",
        default="pyproject.toml",
        metavar="PATH",
        help="Path to pyproject.toml (default: %(default)s)",
    )
    parser.add_argument(
        "--root",
        default=".",
        metavar="DIR",
        help="Root directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "Scan the project and pin all files currently over the standard "
            "limit into [tool.architecture.legacy_baselines] in pyproject.toml. "
            "Use once before a refactoring effort to freeze the current state."
        ),
    )
    parser.add_argument(
        "--strict-new",
        action="store_true",
        help=(
            "Fail the check if any NEW (non-legacy) file exceeds the strict "
            "line limit (default: %(default)s). "
            "Overrides strict_new_files in pyproject.toml for this run."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    args = _build_arg_parser().parse_args(argv)

    config = ArchitectureConfig.from_toml(args.config)

    # --strict-new on the CLI overrides the pyproject.toml flag.
    if args.strict_new and not config.strict_new_files:
        import dataclasses
        config = dataclasses.replace(config, strict_new_files=True)

    validator = DefaultSizeValidator()
    scanner = ProjectScanner(config, validator)
    boundary_checker = ImportBoundaryChecker(config)

    metrics = scanner.scan(args.root)

    # --update-baseline: pin over-limit files and exit without running checks.
    if args.update_baseline:
        writer = BaselineWriter(args.config, config)
        writer.write(metrics)
        return

    import_ok = boundary_checker.check()

    reporter = GuardReport(config)
    if not reporter.display(metrics, import_ok):
        sys.exit(1)


if __name__ == "__main__":
    main()
