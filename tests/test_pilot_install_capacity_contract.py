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


def test_pilot_capacity_accepts_compact_host_profile() -> None:
    result = _validate(global_limit=3, per_user=1, replicas=3, worker_slots=1)

    assert result.returncode == 0, result.stderr
    assert "database cap=3" in result.stdout
    assert "per-user cap=1" in result.stdout
    assert "local worker slots=3" in result.stdout


def test_pilot_capacity_rejects_global_limit_above_ten() -> None:
    result = _validate(global_limit=11)

    assert result.returncode != 0
    assert "global concurrency must not exceed 10" in result.stderr


def test_pilot_capacity_rejects_an_undersized_worker_pool() -> None:
    result = _validate(global_limit=10, replicas=4, worker_slots=2)

    assert result.returncode != 0
    assert "provide at least 10 local slots" in result.stderr


def test_pilot_capacity_rejects_per_user_limit_above_two() -> None:
    result = _validate(global_limit=3, per_user=3, replicas=3, worker_slots=1)

    assert result.returncode != 0
    assert "per-user concurrency must not exceed 2" in result.stderr


def test_pilot_capacity_rejects_per_user_limit_above_global_limit() -> None:
    result = _validate(global_limit=1, per_user=2, replicas=1, worker_slots=1)

    assert result.returncode != 0
    assert "per-user concurrency must not exceed global concurrency" in result.stderr
