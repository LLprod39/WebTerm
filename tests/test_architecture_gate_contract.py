from pathlib import Path

from scripts.architecture_guard_config import ArchitectureConfig
from scripts.architecture_guard_size import DefaultSizeValidator

ROOT = Path(__file__).resolve().parents[1]


def test_line_count_is_warning_without_legacy_pins():
    config = ArchitectureConfig.from_toml(str(ROOT / "pyproject.toml"))
    metric = DefaultSizeValidator().validate("oversized.py", 1500, config)

    assert config.legacy_baselines == {}
    assert metric.passed is True
    assert "Line-count warning" in metric.error_message


def test_architecture_contract_declares_blocking_connectivity_metrics():
    contract = (ROOT / "docs" / "architecture" / "ARCHITECTURE_CONTRACT.md").read_text(encoding="utf-8")
    assert "Cyclomatic complexity blocks" in contract
    assert "fan-out blocks" in contract
    assert "fan-in blocks" in contract
