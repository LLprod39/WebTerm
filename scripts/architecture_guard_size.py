from __future__ import annotations

from abc import ABC, abstractmethod

from architecture_guard_config import ArchitectureConfig, FileMetric, PathNormalizer


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
        hard_fail = is_critical or config.strict_new_files
        return FileMetric(
            path,
            lines,
            is_legacy=False,
            limit=config.standard_limit,
            passed=not hard_fail,
            error_message=error,
        )
