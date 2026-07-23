from pathlib import Path

from scripts.verify_runtime_contract import verify

ROOT = Path(__file__).resolve().parents[1]


def test_repository_runtime_contract_is_consistent():
    assert verify(ROOT) == []
