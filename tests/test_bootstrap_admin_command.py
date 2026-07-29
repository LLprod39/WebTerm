from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from core_ui.models import UserAppPermission


@pytest.mark.django_db
def test_bootstrap_admin_reads_password_only_from_stdin(monkeypatch, tmp_path) -> None:
    injection_marker = tmp_path / "must-not-exist"
    password = f"private '$(touch {injection_marker})' ; $HOME sentinel"
    stdout = StringIO()
    monkeypatch.setattr("sys.stdin", StringIO(password + "\n"))

    call_command(
        "bootstrap_admin",
        username="secure-admin",
        email="secure-admin@example.test",
        profile="admin_full",
        password_stdin=True,
        stdout=stdout,
    )

    user = get_user_model().objects.get(username="secure-admin")
    assert user.check_password(password)
    assert user.is_staff is True
    assert user.is_superuser is True
    assert UserAppPermission.objects.filter(user=user).exists()
    assert password not in stdout.getvalue()
    assert not injection_marker.exists()


@pytest.mark.django_db
def test_bootstrap_admin_rejects_multiline_password_without_creating_user(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("first-line\nsecond-line\n"))

    with pytest.raises(CommandError, match="exactly one non-empty line"):
        call_command(
            "bootstrap_admin",
            username="rejected-admin",
            profile="admin_full",
            password_stdin=True,
        )

    assert not get_user_model().objects.filter(username="rejected-admin").exists()
