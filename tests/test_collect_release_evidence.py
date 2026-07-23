import json
import subprocess
from pathlib import Path

import pytest

from scripts.collect_release_evidence import (
    EvidenceError,
    build_bundle,
    load_command_results,
    parse_mapping,
    render_markdown,
    require_clean_worktree,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def clean_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "release-evidence@example.invalid")
    _git(tmp_path, "config", "user.name", "Release Evidence Test")
    (tmp_path / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "baseline")
    return tmp_path


def test_dirty_worktree_is_refused(clean_repo: Path):
    (clean_repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(EvidenceError, match="clean worktree"):
        require_clean_worktree(clean_repo)


def test_command_results_require_real_exit_codes(tmp_path: Path):
    path = tmp_path / "commands.json"
    path.write_text(json.dumps({"commands": [{"name": "backend", "command": "pytest", "exit_code": "0"}]}))

    with pytest.raises(EvidenceError, match="exit_code"):
        load_command_results(path)


def test_bundle_preserves_failure_and_never_approves_release(clean_repo: Path):
    artifact = clean_repo / "junit.xml"
    artifact.write_text("<testsuites failures='1'/>\n", encoding="utf-8")
    _git(clean_repo, "add", "junit.xml")
    _git(clean_repo, "commit", "-m", "add evidence fixture")
    commands = [
        {
            "name": "backend",
            "command": "pytest --junitxml=junit.xml",
            "exit_code": 1,
            "tool_versions": {"python": "3.11.15", "pytest": "9.1.1"},
            "state": "failed",
        }
    ]

    bundle = build_bundle(
        repo=clean_repo,
        commands=commands,
        artifacts=[("junit", artifact)],
        configs=[("test-config", clean_repo / "tracked.txt")],
        ci_run_url=None,
        created_at="2026-07-22T00:00:00+00:00",
    )

    assert bundle["summary"] == {
        "command_count": 1,
        "failed_command_count": 1,
        "command_state": "failed",
        "release_decision": "NOT_EVALUATED",
    }
    assert bundle["artifacts"][0]["sha256"]
    assert "Release decision: **NOT EVALUATED**" in render_markdown(bundle, "evidence.json")


def test_mapping_requires_existing_file(clean_repo: Path):
    with pytest.raises(EvidenceError, match="does not exist"):
        parse_mapping("junit=missing.xml", clean_repo)
