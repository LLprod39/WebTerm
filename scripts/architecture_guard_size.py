from __future__ import annotations

from abc import ABC, abstractmethod

try:
    from architecture_guard_config import ArchitectureConfig, FileMetric, PathNormalizer
except ModuleNotFoundError:  # pragma: no cover - package import in tests
    from scripts.architecture_guard_config import ArchitectureConfig, FileMetric, PathNormalizer


class ISizeValidator(ABC):
    """Strategy interface for file-size validation logic."""

    @abstractmethod
    def validate(self, path: str, lines: int, config: ArchitectureConfig) -> FileMetric:
        """Return a :class:`FileMetric` describing whether *path* passes."""


class DefaultSizeValidator(ISizeValidator):
    """Validate legacy baseline growth and new-file size limits."""

    def validate(self, path: str, lines: int, config: ArchitectureConfig) -> FileMetric:
        norm_path = PathNormalizer.normalize(path)
        baseline = config.legacy_baselines.get(norm_path)

        if baseline is not None:
            return self._check_legacy(path, lines, baseline)

        return self._check_new_file(path, lines, config)

    @staticmethod
    def _check_legacy(path: str, lines: int, baseline: int) -> FileMetric:
        error = f"Line-count warning: legacy file grew to {lines} > {baseline}" if lines > baseline else ""
        return FileMetric(path, lines, is_legacy=True, limit=baseline, passed=True, error_message=error)

    @staticmethod
    def _check_new_file(path: str, lines: int, config: ArchitectureConfig) -> FileMetric:
        passed = lines <= config.standard_limit
        if passed:
            return FileMetric(path, lines, is_legacy=False, limit=config.standard_limit, passed=True)

        severity = "large file" if lines <= config.strict_limit else "very large file"
        error = f"Line-count warning ({severity}): {lines} > {config.standard_limit}"
        return FileMetric(
            path,
            lines,
            is_legacy=False,
            limit=config.standard_limit,
            passed=True,
            error_message=error,
        )
