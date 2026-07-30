#!/usr/bin/env python3
"""Architecture boundary fitness checker CLI."""

from __future__ import annotations

import argparse
import sys

from architecture_guard_baseline import BaselineWriter
from architecture_guard_config import ArchitectureConfig
from architecture_guard_imports import ImportBoundaryChecker
from architecture_guard_quality import ArchitectureQualityChecker
from architecture_guard_report import GuardReport
from architecture_guard_scan import ProjectScanner
from architecture_guard_size import DefaultSizeValidator


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check architecture fitness: complexity, coupling, size signals, and import boundaries."
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
            "Refresh legacy line-count warning pins in pyproject.toml. "
            "This does not affect the blocking complexity/coupling gate."
        ),
    )
    parser.add_argument(
        "--strict-new",
        action="store_true",
        help=(
            "Deprecated compatibility flag. Line count is diagnostic; "
            "complexity and coupling metrics are enforced."
        ),
    )
    parser.add_argument(
        "--update-metrics-baseline",
        action="store_true",
        help="Freeze current complexity/fan-in/fan-out debt in the configured baseline.",
    )
    return parser


def _load_config(*, config_path: str, strict_new: bool) -> ArchitectureConfig:  # noqa: ARG001
    return ArchitectureConfig.from_toml(config_path)


def main(argv: list[str] | None = None) -> None:
    args = _build_arg_parser().parse_args(argv)
    config = _load_config(config_path=args.config, strict_new=args.strict_new)

    metrics = ProjectScanner(config, DefaultSizeValidator()).scan(args.root)
    quality_checker = ArchitectureQualityChecker(config)

    if args.update_baseline:
        BaselineWriter(args.config, config).write(metrics)
        return
    if args.update_metrics_baseline:
        path = quality_checker.update_baseline(args.root)
        print(f"Updated architecture metrics baseline: {path}")
        return

    import_ok = ImportBoundaryChecker(config).check()
    try:
        quality = quality_checker.check(args.root)
    except RuntimeError as exc:
        print(f"FAILURE: {exc}")
        sys.exit(1)
    if not GuardReport(config).display(metrics, import_ok, quality):
        sys.exit(1)


if __name__ == "__main__":
    main()
