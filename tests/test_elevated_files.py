"""Unit tests for elevated file path validation and error classification."""

from __future__ import annotations

import pytest

from servers.elevated_files import ElevatedFileError, _classify_sudo_failure, _validate_remote_path


def test_validate_remote_path_accepts_absolute():
    assert _validate_remote_path("/etc/nginx/nginx.conf") == "/etc/nginx/nginx.conf"


def test_validate_remote_path_rejects_empty():
    with pytest.raises(ValueError):
        _validate_remote_path("  ")


def test_validate_remote_path_rejects_null_byte():
    with pytest.raises(ValueError):
        _validate_remote_path("/etc/pass\x00wd")


def test_validate_remote_path_rejects_directory_trailing_slash():
    with pytest.raises(ValueError):
        _validate_remote_path("/etc/nginx/")


def test_classify_sudo_required():
    err = _classify_sudo_failure("sudo: a password is required", 1, had_password=False)
    assert isinstance(err, ElevatedFileError)
    assert err.code == "sudo_required"


def test_classify_permission_denied():
    err = _classify_sudo_failure("Permission denied", 1, had_password=True)
    assert err.code == "permission_denied"
