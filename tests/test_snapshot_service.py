"""Tests for rollback snapshots (2.4).

Covers:
1. ``detect_target_file`` — regex patterns for file-modifying commands.
2. ``save_snapshot`` / ``list_snapshots`` / ``build_restore_command`` — DB CRUD.
3. Dedup logic (same hash → skip).
"""

import pytest
from django.contrib.auth.models import User

from servers.models import CommandSnapshot, Server
from servers.services.snapshot_service import (
    build_restore_command,
    detect_target_file,
    get_snapshot_detail,
    list_snapshots,
    save_snapshot,
)

# ---------------------------------------------------------------------------
# 1. detect_target_file
# ---------------------------------------------------------------------------


class TestDetectTargetFile:
    """Pattern-matching for file-modifying shell commands."""

    @pytest.mark.parametrize(
        "cmd,expected",
        [
            ("sed -i 's/foo/bar/' /etc/nginx/nginx.conf", "/etc/nginx/nginx.conf"),
            ("sed -i.bak 's/old/new/' /tmp/config.yml", "/tmp/config.yml"),
            ("echo 'line' > /etc/hosts", "/etc/hosts"),
            ("echo data >> /var/log/custom.log", "/var/log/custom.log"),
            ("printf 'x' > /opt/app/config", "/opt/app/config"),
            ("tee /etc/cron.d/myjob", "/etc/cron.d/myjob"),
            ("tee -a /etc/profile.d/env.sh", "/etc/profile.d/env.sh"),
            ("cp /tmp/new.conf /etc/app.conf", "/etc/app.conf"),
            ("mv /tmp/old.cfg /etc/new.cfg", "/etc/new.cfg"),
        ],
    )
    def test_detects_file_modification(self, cmd, expected):
        assert detect_target_file(cmd) == expected

    @pytest.mark.parametrize(
        "cmd",
        [
            "ls -la /etc",
            "cat /etc/passwd",
            "df -h",
            "systemctl status nginx",
            "echo hello",
            "rm -rf /tmp/junk",
            "",
            None,
        ],
    )
    def test_non_modifying_returns_none(self, cmd):
        assert detect_target_file(cmd) is None

    def test_relative_path_ignored(self):
        assert detect_target_file("sed -i 's/x/y/' relative.txt") is None


# ---------------------------------------------------------------------------
# 2. DB operations
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSnapshotCRUD:
    """save / list / detail / restore."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.user = User.objects.create_user("snap_user", password="test")
        self.server = Server.objects.create(
            name="snap-srv",
            host="10.0.0.1",
            username="root",
            user=self.user,
        )

    def test_save_and_list(self):
        pk = save_snapshot(
            server_id=self.server.id,
            user_id=self.user.id,
            command="sed -i 's/a/b/' /etc/conf",
            file_path="/etc/conf",
            content="line1\nline2\n",
        )
        assert pk > 0
        items = list_snapshots(self.server.id)
        assert len(items) == 1
        assert items[0]["file_path"] == "/etc/conf"

    def test_dedup_same_content(self):
        kwargs = {
            "server_id": self.server.id,
            "user_id": self.user.id,
            "command": "echo x > /tmp/f",
            "file_path": "/tmp/f",
            "content": "same content",
        }
        pk1 = save_snapshot(**kwargs)
        pk2 = save_snapshot(**kwargs)
        assert pk1 > 0
        assert pk2 == 0  # deduped
        assert CommandSnapshot.objects.filter(server=self.server).count() == 1

    def test_different_content_not_deduped(self):
        base = {
            "server_id": self.server.id,
            "user_id": self.user.id,
            "command": "echo x > /tmp/f",
            "file_path": "/tmp/f",
        }
        save_snapshot(**base, content="v1")
        pk2 = save_snapshot(**base, content="v2")
        assert pk2 > 0
        assert CommandSnapshot.objects.filter(server=self.server).count() == 2

    def test_get_detail(self):
        pk = save_snapshot(
            server_id=self.server.id,
            user_id=self.user.id,
            command="tee /opt/x",
            file_path="/opt/x",
            content="hello",
        )
        detail = get_snapshot_detail(pk)
        assert detail is not None
        assert detail["content"] == "hello"
        assert detail["file_path"] == "/opt/x"

    def test_get_detail_not_found(self):
        assert get_snapshot_detail(999999) is None

    def test_build_restore_command_heredoc(self):
        pk = save_snapshot(
            server_id=self.server.id,
            user_id=self.user.id,
            command="sed -i 's/a/b/' /etc/app.conf",
            file_path="/etc/app.conf",
            content="original\ncontent\n",
        )
        cmd = build_restore_command(pk)
        assert cmd is not None
        assert "/etc/app.conf" in cmd
        assert "original\ncontent\n" in cmd
        assert "_WEUAI_RESTORE_EOF_" in cmd
        # Check restored_at is set
        snap = CommandSnapshot.objects.get(pk=pk)
        assert snap.restored_at is not None

    def test_build_restore_empty_content_means_remove(self):
        pk = save_snapshot(
            server_id=self.server.id,
            user_id=self.user.id,
            command="echo x > /tmp/new_file",
            file_path="/tmp/new_file",
            content="",
        )
        cmd = build_restore_command(pk)
        assert cmd is not None
        assert "rm -f" in cmd

    def test_build_restore_not_found(self):
        assert build_restore_command(999999) is None

    def test_list_respects_limit(self):
        for i in range(5):
            save_snapshot(
                server_id=self.server.id,
                user_id=self.user.id,
                command=f"echo {i} > /tmp/f{i}",
                file_path=f"/tmp/f{i}",
                content=f"content-{i}",
            )
        assert len(list_snapshots(self.server.id, limit=3)) == 3
        assert len(list_snapshots(self.server.id, limit=10)) == 5
