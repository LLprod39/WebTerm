from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "docker/validate-pilot-capacity.py"


def _validate(*, global_limit: int, per_user: int = 2, replicas: int = 5, worker_slots: int = 2):
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--global-concurrency",
            str(global_limit),
            "--per-user-concurrency",
            str(per_user),
            "--replicas",
            str(replicas),
            "--worker-concurrency",
            str(worker_slots),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_pilot_capacity_accepts_ten_database_capped_slots() -> None:
    result = _validate(global_limit=10)

    assert result.returncode == 0, result.stderr
    assert "database cap=10" in result.stdout


def test_pilot_capacity_rejects_global_limit_above_ten() -> None:
    result = _validate(global_limit=11)

    assert result.returncode != 0
    assert "global concurrency must be exactly 10" in result.stderr


def test_pilot_capacity_rejects_an_undersized_worker_pool() -> None:
    result = _validate(global_limit=10, replicas=4, worker_slots=2)

    assert result.returncode != 0
    assert "provide at least 10 local slots" in result.stderr
