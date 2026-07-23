#!/usr/bin/env python3
"""Architecture boundary fitness checker CLI."""

from __future__ import annotations

import argparse
import dataclasses
import sys

from architecture_guard_baseline import BaselineWriter
from architecture_guard_config import ArchitectureConfig
from architecture_guard_imports import ImportBoundaryChecker
from architecture_guard_report import GuardReport
from architecture_guard_scan import ProjectScanner
from architecture_guard_size import DefaultSizeValidator


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check architecture fitness: file-size limits and import boundaries.")
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


def _load_config(*, config_path: str, strict_new: bool) -> ArchitectureConfig:
    config = ArchitectureConfig.from_toml(config_path)
    if strict_new and not config.strict_new_files:
        return dataclasses.replace(config, strict_new_files=True)
    return config


def main(argv: list[str] | None = None) -> None:
    args = _build_arg_parser().parse_args(argv)
    config = _load_config(config_path=args.config, strict_new=args.strict_new)

    metrics = ProjectScanner(config, DefaultSizeValidator()).scan(args.root)

    if args.update_baseline:
        BaselineWriter(args.config, config).write(metrics)
        return

    import_ok = ImportBoundaryChecker(config).check()
    if not GuardReport(config).display(metrics, import_ok):
        sys.exit(1)


if __name__ == "__main__":
    main()
