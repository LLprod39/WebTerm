from pathlib import Path

from scripts.verify_docs_contract import verify

ROOT = Path(__file__).resolve().parents[1]


def test_authoritative_docs_contract_is_consistent():
    assert verify(ROOT) == []
