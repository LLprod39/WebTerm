from __future__ import annotations

from pathlib import Path

from scripts.architecture_guard_config import ArchitectureConfig
from scripts.architecture_guard_quality import ArchitectureQualityChecker
from scripts.architecture_guard_size import DefaultSizeValidator


def _config() -> ArchitectureConfig:
    return ArchitectureConfig(
        standard_limit=10,
        strict_limit=20,
        strict_new_files=True,
        complexity_limit=1,
        fan_out_limit=1,
        fan_in_limit=0,
        metrics_baseline_file="architecture-baseline.json",
    )


def _write_fixture(root: Path) -> None:
    (root / "a.py").write_text(
        "import b\nimport c\n\ndef decide(value):\n    if value:\n        return 1\n    return 0\n",
        encoding="utf-8",
    )
    (root / "b.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "c.py").write_text("VALUE = 2\n", encoding="utf-8")


def test_quality_baseline_freezes_complexity_and_coupling_growth(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    checker = ArchitectureQualityChecker(_config())
    checker.update_baseline(str(tmp_path))

    assert checker.check(str(tmp_path)).passed is True

    (tmp_path / "a.py").write_text(
        "import b\nimport c\n\ndef decide(value):\n"
        "    if value:\n        if value > 1:\n            return 2\n        return 1\n    return 0\n",
        encoding="utf-8",
    )
    result = checker.check(str(tmp_path))

    assert result.passed is False
    assert any("frozen complexity violation grew" in error for error in result.errors)


def test_quality_baseline_rejects_new_fan_edges(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    checker = ArchitectureQualityChecker(_config())
    checker.update_baseline(str(tmp_path))

    (tmp_path / "d.py").write_text("VALUE = 3\n", encoding="utf-8")
    source = (tmp_path / "a.py").read_text(encoding="utf-8")
    (tmp_path / "a.py").write_text(f"import d\n{source}", encoding="utf-8")
    result = checker.check(str(tmp_path))

    assert result.passed is False
    assert any("frozen fan-out violation grew" in error for error in result.errors)
    assert any("new fan-in violation" in error for error in result.errors)


def test_line_count_is_a_non_blocking_signal() -> None:
    metric = DefaultSizeValidator().validate("large.py", 100, _config())

    assert metric.passed is True
    assert "Line-count warning" in metric.error_message
