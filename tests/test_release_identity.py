from pathlib import Path

from scripts.verify_release_identity import verify

ROOT = Path(__file__).resolve().parents[1]


def test_release_identity_is_synchronized():
    assert verify(ROOT) == []
