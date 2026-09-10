"""Restore only the existing QA SSH fixture secret after a QA encryption-key change.

This does not rotate passwords, create fixtures or print credentials.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
os.environ["DJANGO_SETTINGS_MODULE"] = "qa_settings"

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.db import connection, transaction  # noqa: E402

from servers.models import Server  # noqa: E402
from servers.secret_utils import store_server_auth_secret  # noqa: E402


def restore_fixture_secret() -> None:
    expected_database = "webterm_frontend_qa_20260902"
    if settings.SETTINGS_MODULE != "qa_settings" or connection.vendor != "postgresql":
        raise RuntimeError("This helper requires the isolated PostgreSQL QA settings.")
    if str(settings.DATABASES["default"]["NAME"]) != expected_database:
        raise RuntimeError("Refusing to access a database other than the exact frontend QA database.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        if cursor.fetchone()[0] != expected_database:
            raise RuntimeError("The connected database is not the exact frontend QA database.")

    credentials_path = Path(__file__).resolve().parents[1] / ".auth" / "credentials.json"
    credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    admin = credentials.get("admin") or {}
    server_id = credentials.get("serverId")
    password = credentials.get("sshPassword")
    if (
        type(server_id) is not int
        or type(admin.get("id")) is not int
        or admin.get("username") != "frontend-qa-admin"
        or not isinstance(password, str)
        or not password
    ):
        raise RuntimeError("The QA fixture credentials have an unexpected shape.")

    with transaction.atomic():
        server = Server.objects.select_for_update().select_related("user", "project").get(pk=server_id)
        if (
            server.user_id != admin["id"]
            or server.user.username != "frontend-qa-admin"
            or not server.user.is_staff
            or str(server.project.public_id) != str(admin.get("project"))
            or server.name != "qa-ssh-local"
            or server.host != "127.0.0.1"
            or server.port != 22391
            or server.username != "qa"
            or server.auth_method != "password"
        ):
            raise RuntimeError("The selected server is not the expected admin-owned local QA SSH fixture.")
        store_server_auth_secret(server, secret_value=password)
    print("Existing QA SSH fixture secret restored; fixture password unchanged.")


if __name__ == "__main__":
    restore_fixture_secret()
