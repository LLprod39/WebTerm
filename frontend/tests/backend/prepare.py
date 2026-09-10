"""Create the dedicated frontend QA database and local-only test identities."""
import json
import os
import secrets
from pathlib import Path

os.environ["DJANGO_SETTINGS_MODULE"] = "qa_settings"
import django
django.setup()
from django.conf import settings
from django.db import connection
from django.core.management import call_command
from django.contrib.auth.models import User
from core_ui.models.access import FEATURE_CHOICES, UserAppPermission
from core_ui.projects import ensure_default_project
from servers.models import Server, ServerGroup
from servers.secret_utils import store_server_auth_secret
import asyncssh
import psycopg
from psycopg import sql

db = settings.DATABASES["default"]
assert db["NAME"] == "webterm_frontend_qa_20260902"
with psycopg.connect(dbname="postgres", user=db["USER"], password=db["PASSWORD"], host=db["HOST"], port=db["PORT"], autocommit=True) as admin:
    if not admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db["NAME"],)).fetchone():
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db["NAME"])))
call_command("migrate", interactive=False, verbosity=0)
root = Path(__file__).resolve().parents[1] / ".auth"
root.mkdir(exist_ok=True)
keyfile = root / "ssh_key"
if not keyfile.exists():
    asyncssh.generate_private_key("ssh-ed25519").write_private_key(str(keyfile))
key = asyncssh.read_private_key(str(keyfile))
password = secrets.token_urlsafe(24)
payload = {"password": password, "sshPassword": secrets.token_urlsafe(24), "fingerprint": key.get_fingerprint("sha256")}
for name, staff in [("frontend-qa-admin", True), ("frontend-qa-viewer", False)]:
    user, _ = User.objects.get_or_create(username=name)
    user.is_staff, user.is_superuser, user.is_active = staff, False, True
    user.email = f"{name}@example.test"
    user.set_password(password)
    user.save()
    for feature, _ in FEATURE_CHOICES:
        UserAppPermission.objects.update_or_create(user=user, feature=feature, defaults={"allowed": staff or feature in {"servers", "dashboard"}})
    project = ensure_default_project(user)
    project.name = "Frontend QA · isolated" if staff else "Наблюдение · QA"
    project.save(update_fields=["name"])
    payload["admin" if staff else "viewer"] = {"username": name, "id": user.id, "project": str(project.public_id)}
    if staff:
        group, _ = ServerGroup.objects.get_or_create(user=user, name="QA environment")
        server, _ = Server.objects.get_or_create(user=user, name="qa-ssh-local", defaults={"project": project, "group": group, "host": "127.0.0.1", "port": 22391, "username": "qa", "auth_method": "password"})
        server.trusted_host_keys = [{"public_key": key.export_public_key().decode(), "fingerprint_sha256": key.get_fingerprint("sha256")}]
        server.notes = "Изолированный SSH fixture для сквозных тестов. Команды выполняются внутри тестового обработчика."
        server.save()
        store_server_auth_secret(server, secret_value=payload["sshPassword"])
        payload["serverId"] = server.id
        payload["groupId"] = group.id
(root / "credentials.json").write_text(json.dumps(payload), encoding="utf-8")
(root / "files").mkdir(exist_ok=True)
(root / "files" / "readme.txt").write_text("WebTerm QA SFTP file\n", encoding="utf-8")
connection.close()
print("Frontend QA database migrated and seeded; test credentials written to ignored .auth directory.")
