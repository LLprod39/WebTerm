from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_migration_history.py"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _run(repo: Path, from_ref: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), "--from-ref", from_ref],
        check=False,
        capture_output=True,
        text=True,
    )


def test_new_migration_is_allowed_but_historical_edit_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    migration_dir = repo / "sample" / "migrations"
    migration_dir.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "release-test@example.test")
    _git(repo, "config", "user.name", "Release Test")
    (migration_dir / "0001_initial.py").write_text("INITIAL = True\n", encoding="utf-8")
    baseline = _commit_all(repo, "baseline")

    (migration_dir / "0002_safe_addition.py").write_text("ADDED = True\n", encoding="utf-8")
    _commit_all(repo, "add migration")
    accepted = _run(repo, baseline)
    assert accepted.returncode == 0, accepted.stderr
    accepted_payload = json.loads(accepted.stdout)
    assert accepted_payload["status"] == "pass"
    assert accepted_payload["added_migrations"] == ["sample/migrations/0002_safe_addition.py"]

    (migration_dir / "0001_initial.py").write_text("INITIAL = False\n", encoding="utf-8")
    _commit_all(repo, "mutate history")
    rejected = _run(repo, baseline)
    assert rejected.returncode == 1
    rejected_payload = json.loads(rejected.stdout)
    assert rejected_payload["status"] == "fail"
    assert rejected_payload["historical_mutations"] == [{"paths": "sample/migrations/0001_initial.py", "status": "M"}]
