from __future__ import annotations

import os
import subprocess

from architecture_guard_config import ArchitectureConfig, FileMetric
from architecture_guard_size import ISizeValidator


class ProjectScanner:
    """Walks the project tree and produces :class:`FileMetric` results."""

    def __init__(self, config: ArchitectureConfig, validator: ISizeValidator) -> None:
        self._config = config
        self._validator = validator

    def scan(self, root_dir: str = ".") -> list[FileMetric]:
        """Return metrics for all tracked files under *root_dir*."""
        metrics: list[FileMetric] = []
        git_files = self._git_candidate_files(root_dir)
        if git_files is not None:
            root_abs = os.path.abspath(root_dir)
            for full_path in git_files:
                if not os.path.exists(full_path):
                    continue
                if self._file_is_excluded(full_path) or not self._has_tracked_extension(full_path):
                    continue
                lines = self._count_lines(full_path)
                rel_path = os.path.relpath(full_path, root_abs)
                metrics.append(self._validator.validate(rel_path, lines, self._config))
            return metrics

        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d not in self._config.exclude_dirs]

            if self._path_is_excluded(dirpath):
                continue

            for filename in filenames:
                if self._has_tracked_extension(filename):
                    full_path = os.path.join(dirpath, filename)
                    lines = self._count_lines(full_path)
                    metrics.append(self._validator.validate(full_path, lines, self._config))

        return metrics

    def _git_candidate_files(self, root_dir: str) -> list[str] | None:
        try:
            result = subprocess.run(
                ["git", "-C", root_dir, "ls-files", "--cached", "--others", "--exclude-standard"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return None
        if result.returncode != 0:
            return None
        root = os.path.abspath(root_dir)
        files: list[str] = []
        for raw in result.stdout.splitlines():
            rel = raw.strip()
            if rel:
                files.append(os.path.join(root, rel))
        return files

    def _path_is_excluded(self, dirpath: str) -> bool:
        norm = dirpath.replace("\\", "/")
        return any(fragment in norm for fragment in self._config.exclude_path_fragments)

    def _file_is_excluded(self, path: str) -> bool:
        norm = path.replace("\\", "/")
        if any(fragment in norm for fragment in self._config.exclude_path_fragments):
            return True
        return any(part in self._config.exclude_dirs for part in norm.split("/"))

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
