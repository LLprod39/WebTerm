"""Seed isolated Linux SSH and file snapshots for manual browser UX checks."""
import asyncio
import json
import os
import subprocess
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "qa_settings")
import django
django.setup()

import asyncssh
from django.conf import settings
from servers.models import Server
from servers.secret_utils import store_server_auth_secret
from servers.services.snapshot_service import save_snapshot
from servers.services.terminal_snapshotting import capture_pre_execution_snapshot

root = Path(__file__).resolve().parents[1] / ".auth"
credentials = json.loads((root / "credentials.json").read_text())
assert settings.DATABASES["default"]["NAME"] == "webterm_frontend_qa_20260902"
subprocess.run(["docker", "exec", "-i", "webterm-ux-ssh-20260902", "chpasswd"],
               input=("qa:" + credentials["sshPassword"] + "\n").encode(), check=True, capture_output=True)
public_key = subprocess.check_output([
    "docker", "exec", "webterm-ux-ssh-20260902", "cat", "/etc/ssh/ssh_host_ed25519_key.pub"
]).decode()
key = asyncssh.import_public_key(public_key)
original = Server.objects.get(pk=credentials["serverId"])
server, created = Server.objects.get_or_create(
    user_id=credentials["admin"]["id"], name="QA Linux UX 20260902",
    defaults=dict(project=original.project, host="127.0.0.1", port=22392, username="qa", auth_method="password"),
)
server.trusted_host_keys = [{"public_key": public_key, "fingerprint_sha256": key.get_fingerprint("sha256")}]
server.notes = "Изолированный Linux-контейнер для проверки интерфейса. Нет доступа к файлам хоста."
server.save()
store_server_auth_secret(server, secret_value=credentials["sshPassword"])

async def seed():
    async with asyncssh.connect("127.0.0.1", port=22392, username="qa",
        password=credentials["sshPassword"], known_hosts=([key], [], [])) as conn:
        async with conn.start_sftp_client() as sftp:
            await sftp.makedirs("/home/qa/ux-snapshots", exist_ok=True)
            expected = {
                "text.txt": "Исходный текст\n_WEUAI_RESTORE_EOF_\n$(literal) без перевода строки",
                "empty.txt": "",
                "missing.txt": None,
            }
            for name, content in expected.items():
                path = "/home/qa/ux-snapshots/" + name
                if content is not None:
                    async with sftp.open(path, "wb") as f:
                        await f.write(content.encode())
                else:
                    try:
                        await sftp.remove(path)
                    except asyncssh.SFTPNoSuchFile:
                        pass
                captured = await capture_pre_execution_snapshot(
                    command="printf changed > " + path, cmd_id=1, ssh_conn=conn,
                    server_id=server.id, user_id=server.user_id,
                )
                assert captured, name
                async with sftp.open(path, "wb") as f:
                    await f.write(b"changed")
        return expected

if created or not (root / "linux-snapshots.json").exists():
    expected = asyncio.run(seed())
    save_snapshot(server.id, server.user_id, "tee /home/qa/ux-snapshots/legacy.txt",
                  "/home/qa/ux-snapshots/legacy.txt", "", file_existed=None)
    from servers.models import CommandSnapshot
    truncated = save_snapshot(server.id, server.user_id, "tee /home/qa/ux-snapshots/large.txt",
                              "/home/qa/ux-snapshots/large.txt", "incomplete", file_existed=True)
    CommandSnapshot.objects.filter(pk=truncated).update(content_truncated=True)
    (root / "linux-snapshots.json").write_text(json.dumps({"serverId": server.id, "expected": expected}), encoding="utf-8")
print(json.dumps({"serverId": server.id, "created": created}))
