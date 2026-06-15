import os
import subprocess

import pytest

from mars.models import default_deny_globs
from mars.policy import MarsPolicyError, validate_workspace_child, validate_workspace_root


def _init_git_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "mars@example.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "MARS Test"], cwd=root, check=True)
    (root / "README.md").write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True, text=True)
    return root


def test_validate_workspace_root_requires_absolute_existing_git_repo(tmp_path):
    root = _init_git_repo(tmp_path)
    assert validate_workspace_root(str(root)) == root.resolve()

    with pytest.raises(MarsPolicyError):
        validate_workspace_root("relative/repo")

    with pytest.raises(MarsPolicyError):
        validate_workspace_root(str(tmp_path / "missing"))

    nongit = tmp_path / "plain"
    nongit.mkdir()
    with pytest.raises(MarsPolicyError):
        validate_workspace_root(str(nongit))


def test_validate_workspace_child_blocks_parent_escape_and_denied_globs(tmp_path):
    root = _init_git_repo(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")

    with pytest.raises(MarsPolicyError):
        validate_workspace_child(root_path=str(root), child_path=str(outside), deny_globs=default_deny_globs())

    env_file = root / ".env"
    env_file.write_text("SECRET=1\n", encoding="utf-8")
    with pytest.raises(MarsPolicyError):
        validate_workspace_child(root_path=str(root), child_path=str(env_file), deny_globs=default_deny_globs())

    source_file = root / "src" / "app.py"
    source_file.parent.mkdir()
    source_file.write_text("print('ok')\n", encoding="utf-8")
    assert validate_workspace_child(root_path=str(root), child_path=str(source_file), deny_globs=default_deny_globs()) == source_file.resolve()


def test_validate_workspace_child_blocks_symlink_outside_root(tmp_path):
    root = _init_git_repo(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    link = root / "linked-outside.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not available in this Windows environment.")

    assert os.path.islink(link)
    with pytest.raises(MarsPolicyError):
        validate_workspace_child(root_path=str(root), child_path=str(link), deny_globs=default_deny_globs())
