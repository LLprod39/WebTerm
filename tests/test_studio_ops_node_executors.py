from __future__ import annotations

from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from servers.models import Server, ServerAlert
from studio.models import Pipeline, PipelineRun
from studio.pipeline_executor import _execute_registry_node

pytestmark = pytest.mark.django_db(transaction=True)


def _make_user(username: str) -> User:
    return User.objects.create_user(username=username, password="x")


def _make_run(username: str = "ops-node-user") -> PipelineRun:
    owner = _make_user(username)
    pipeline = Pipeline.objects.create(
        name=f"Pipeline for {username}",
        owner=owner,
        nodes=[{"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {"label": "Manual"}}],
        edges=[],
    )
    return PipelineRun.objects.create(
        pipeline=pipeline,
        triggered_by=owner,
        status=PipelineRun.STATUS_PENDING,
        nodes_snapshot=list(pipeline.nodes),
        edges_snapshot=list(pipeline.edges),
        context={},
        entry_node_id="manual",
        routing_state={
            "entry_node_id": "manual",
            "activated_nodes": ["manual"],
            "completed_nodes": [],
            "queued_nodes": [],
            "pending_merges": {},
        },
    )


@pytest.fixture(autouse=True)
def _disable_activity_logging(monkeypatch):
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("studio.pipeline_agent_runtime.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline_run_state.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline_run_state.get_channel_layer", lambda: None)


def test_ops_server_snapshot_node_uses_context_server_id(monkeypatch):
    run = _make_run("ops-snapshot-user")
    server = Server.objects.create(user=run.pipeline.owner, name="ops-srv", host="10.0.0.8", username="root")

    async def fake_secret(_server):
        return ""

    async def fake_overview(_server, *, secret=""):
        return {"summary": {"status": "ok"}}

    async def fake_disk(_server, *, secret=""):
        return {"summary": {"critical_mounts": 0}}

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_overview", fake_overview)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_disk", fake_disk)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "snapshot",
            "type": "ops/server_snapshot",
            "data": {"server_id_context_key": "target_server_id", "sections": ["overview", "disk"]},
        },
        {"target_server_id": server.id},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert "ops-srv" in result["output"]
    assert result["snapshot"]["sections"]["overview"]["summary"]["status"] == "ok"


def test_ops_log_query_node_collects_and_filters_service_logs(monkeypatch):
    run = _make_run("ops-log-query-user")
    server = Server.objects.create(user=run.pipeline.owner, name="logs-srv", host="10.0.0.9", username="root")

    async def fake_secret(_server):
        return ""

    async def fake_logs(_server, *, secret="", source="journal", lines=120, service=""):
        return {
            "source": source,
            "service": service,
            "lines": lines,
            "available": True,
            "content": "ok boot\nERROR failed auth\nwarning slow request",
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_logs", fake_logs)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "log_query",
            "type": "ops/log_query",
            "data": {
                "server_id_context_key": "target_server_id",
                "source": "service",
                "service": "nginx",
                "lines": 60,
                "filter_text": "failed",
            },
        },
        {"target_server_id": server.id},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert "logs-srv" in result["output"]
    assert result["logs"]["source"] == "service"
    assert result["logs"]["service"] == "nginx"
    assert result["logs"]["match_count"] == 1
    assert result["logs"]["matched_lines"] == ["ERROR failed auth"]


def test_ops_file_action_node_reads_text_file(monkeypatch):
    run = _make_run("ops-file-read-user")
    server = Server.objects.create(user=run.pipeline.owner, name="file-srv", host="10.0.0.10", username="root")

    async def fake_secret(_server):
        return ""

    async def fake_read_text_file(_server, *, secret="", path="", max_bytes=131072):
        return {
            "path": path,
            "filename": "os-release",
            "size": 24,
            "encoding": "utf-8",
            "content": "NAME=Demo Linux\nVERSION=1",
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.read_text_file", fake_read_text_file)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "file_read",
            "type": "ops/file_action",
            "data": {
                "server_id_context_key": "target_server_id",
                "action": "read",
                "path": "/etc/os-release",
                "max_bytes": 65536,
            },
        },
        {"target_server_id": server.id},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert result["file"]["action"] == "read"
    assert result["file"]["content"] == "NAME=Demo Linux\nVERSION=1"


def test_ops_file_action_node_writes_text_file_without_echoing_content(monkeypatch):
    run = _make_run("ops-file-write-user")
    server = Server.objects.create(user=run.pipeline.owner, name="file-srv", host="10.0.0.11", username="root")
    captured: dict[str, object] = {}

    async def fake_secret(_server):
        return ""

    async def fake_write_text_file(_server, *, secret="", path="", content="", max_bytes=131072):
        captured["path"] = path
        captured["content"] = content
        return {
            "path": path,
            "filename": "app.conf",
            "size": len(content.encode("utf-8")),
            "encoding": "utf-8",
            "content": content,
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.write_text_file", fake_write_text_file)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "file_write",
            "type": "ops/file_action",
            "data": {
                "server_id": server.id,
                "action": "write",
                "path": "/etc/app/app.conf",
                "content": "token={secret_value}",
            },
        },
        {"secret_value": "redacted-at-output-boundary"},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert captured == {"path": "/etc/app/app.conf", "content": "token=redacted-at-output-boundary"}
    assert result["file"]["action"] == "write"
    assert "content" not in result["file"]
    assert "content_sha256" in result["file"]


def test_ops_package_action_lists_updates(monkeypatch):
    run = _make_run("ops-package-list-user")
    server = Server.objects.create(user=run.pipeline.owner, name="pkg-srv", host="10.0.0.12", username="root")

    async def fake_secret(_server):
        return ""

    async def fake_packages(_server, *, secret=""):
        return {
            "package_manager": "apt",
            "installed": [{"name": "curl", "version": "1.0"}],
            "updates": ["curl/stable 1.1 amd64"],
            "summary": {"installed_common": 1, "update_candidates": 1},
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_packages", fake_packages)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "packages",
            "type": "ops/package_action",
            "data": {"server_id": server.id, "action": "list_updates"},
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert result["packages"]["package_manager"] == "apt"
    assert result["packages"]["summary"]["update_candidates"] == 1


def test_ops_package_action_runs_explicit_install_and_verifies(monkeypatch):
    run = _make_run("ops-package-install-user")
    server = Server.objects.create(user=run.pipeline.owner, name="pkg-srv", host="10.0.0.13", username="root")
    captured: dict[str, object] = {}

    async def fake_secret(_server):
        return ""

    async def fake_capabilities(_server, *, secret=""):
        return {"package_manager": "apt"}

    async def fake_run_command_result(_server, *, secret="", command=""):
        captured["command"] = command
        return {"stdout": "installed curl\n__ACTION_EXIT__=0\n", "stderr": "", "exit_code": 0}

    async def fake_packages(_server, *, secret=""):
        return {"package_manager": "apt", "installed": [], "updates": [], "summary": {"update_candidates": 0}}

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_capabilities", fake_capabilities)
    monkeypatch.setattr("studio.executor.nodes.ops._run_command_result", fake_run_command_result)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_packages", fake_packages)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "package_install",
            "type": "ops/package_action",
            "data": {"server_id": server.id, "action": "install", "packages": ["curl"], "verify": True},
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert "apt-get install -y -- curl" in str(captured["command"])
    assert result["package_action"]["packages"] == ["curl"]
    assert result["package_action"]["success"] is True


def test_ops_disk_cleanup_inspects_disk_state(monkeypatch):
    run = _make_run("ops-disk-inspect-user")
    server = Server.objects.create(user=run.pipeline.owner, name="disk-srv", host="10.0.0.14", username="root")

    async def fake_secret(_server):
        return ""

    async def fake_disk(_server, *, secret=""):
        return {
            "summary": {"critical_mounts": 1, "cleanup_candidates": 3},
            "mounts": [],
            "top_directories": [],
            "large_logs": [],
            "cleanup_candidates": ["/tmp/old"],
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_disk", fake_disk)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "disk",
            "type": "ops/disk_cleanup",
            "data": {"server_id": server.id, "action": "inspect"},
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert result["disk"]["summary"]["cleanup_candidates"] == 3
    assert result["disk"]["action"] == "inspect"


def test_ops_disk_cleanup_runs_tmp_cleanup_and_verifies(monkeypatch):
    run = _make_run("ops-disk-cleanup-user")
    server = Server.objects.create(user=run.pipeline.owner, name="disk-clean-srv", host="10.0.0.15", username="root")
    captured: dict[str, object] = {}

    async def fake_secret(_server):
        return ""

    async def fake_disk(_server, *, secret=""):
        return {
            "summary": {"critical_mounts": 0, "cleanup_candidates": 0},
            "mounts": [],
            "top_directories": [],
            "large_logs": [],
            "cleanup_candidates": [],
        }

    async def fake_run_command_result(_server, *, secret="", command=""):
        captured["command"] = command
        return {
            "stdout": "__PLAN__\n/tmp/old\n__ACTION__\nremoved=/tmp/old\n__ACTION_EXIT__=0\n",
            "stderr": "",
            "exit_code": 0,
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_disk", fake_disk)
    monkeypatch.setattr("studio.executor.nodes.ops._run_command_result", fake_run_command_result)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "disk_cleanup",
            "type": "ops/disk_cleanup",
            "data": {
                "server_id": server.id,
                "action": "tmp_cleanup",
                "min_age_days": 10,
                "max_entries": 25,
                "dry_run": False,
            },
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert "find /tmp /var/tmp -xdev -mindepth 1 -mtime +10" in str(captured["command"])
    assert result["disk_cleanup"]["success"] is True
    assert result["disk_cleanup"]["dry_run"] is False


def test_ops_backup_restore_check_inspects_latest_backup(monkeypatch):
    run = _make_run("ops-backup-check-user")
    server = Server.objects.create(user=run.pipeline.owner, name="backup-srv", host="10.0.0.16", username="root")

    async def fake_secret(_server):
        return ""

    async def fake_run_command_result(_server, *, secret="", command=""):
        return {
            "stdout": "__FILES__\n9999999999\t1048576\t/var/backups/app.tar.gz\n__VERIFY__\nverification=skipped\n",
            "stderr": "",
            "exit_code": 0,
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops._run_command_result", fake_run_command_result)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "backup_check",
            "type": "ops/backup_restore_check",
            "data": {"server_id": server.id, "action": "inspect", "path": "/var/backups", "max_age_hours": 24},
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert result["backup_restore_check"]["summary"]["latest_path"] == "/var/backups/app.tar.gz"
    assert result["backup_restore_check"]["verification"]["requested"] is False


def test_ops_backup_restore_check_verifies_latest_archive(monkeypatch):
    run = _make_run("ops-backup-verify-user")
    server = Server.objects.create(user=run.pipeline.owner, name="backup-verify-srv", host="10.0.0.17", username="root")
    captured: dict[str, object] = {}

    async def fake_secret(_server):
        return ""

    async def fake_run_command_result(_server, *, secret="", command=""):
        captured["command"] = command
        return {
            "stdout": "__FILES__\n9999999999\t1048576\t/var/backups/app.tar.gz\n__VERIFY__\nlatest=/var/backups/app.tar.gz\nverification_exit=0\n",
            "stderr": "",
            "exit_code": 0,
        }

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops._run_command_result", fake_run_command_result)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "backup_verify",
            "type": "ops/backup_restore_check",
            "data": {"server_id": server.id, "action": "verify_latest", "path": "/var/backups", "max_depth": 3},
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert 'find "$BACKUP_DIR" -maxdepth "$MAX_DEPTH"' in str(captured["command"])
    assert result["backup_restore_check"]["verification"]["success"] is True


def test_ops_http_check_node_passes_expected_status(monkeypatch):
    run = _make_run("ops-http-user")
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, timeout: int = 15, follow_redirects: bool = True) -> None:
            self.timeout = timeout
            self.follow_redirects = follow_redirects

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, method: str, url: str):
            captured["method"] = method
            captured["url"] = url
            return SimpleNamespace(status_code=204, text="healthy")

    monkeypatch.setattr("studio.executor.nodes.ops.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "http_check",
            "type": "ops/http_check",
            "data": {
                "url": "https://example.test/health",
                "method": "GET",
                "expected_status": [204],
                "body_contains": "healthy",
            },
        },
        {},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert captured == {"method": "GET", "url": "https://example.test/health"}
    assert result["http_check"]["status_code"] == 204


def test_ops_alert_update_resolves_owned_alert():
    run = _make_run("ops-alert-user")
    server = Server.objects.create(user=run.pipeline.owner, name="alert-srv", host="10.0.0.12", username="root")
    alert = ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_SERVICE,
        severity=ServerAlert.SEVERITY_CRITICAL,
        title="Service down",
        message="nginx failed",
    )

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "resolve_alert",
            "type": "ops/alert_update",
            "data": {"alert_id_context_key": "alert_id", "action": "resolve"},
        },
        {"alert_id": alert.id},
        {},
        run,
    )

    alert.refresh_from_db()
    assert result["status"] == "completed"
    assert alert.is_resolved is True
    assert result["alert"]["alert_id"] == alert.id
