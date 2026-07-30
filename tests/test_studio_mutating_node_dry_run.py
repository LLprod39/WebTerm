from __future__ import annotations

from typing import Any

import pytest
from asgiref.sync import async_to_sync

from studio.executor.nodes.base import NodeResult
from studio.executor.registry import registry
from studio.node_manifest import NODE_MANIFESTS
from studio.pipeline.pipeline_executor import PipelineExecutor, _execute_registry_node
from tests.test_studio_ops_node_executors import Server, _make_run
from tests.test_studio_ops_node_executors_extra import ServerAlert

pytestmark = pytest.mark.django_db(transaction=True)


def _server(run: Any, name: str) -> Server:
    return Server.objects.create(user=run.pipeline.owner, name=name, host="10.20.30.40", username="root")


def _assert_preview(result: dict, *, operation: str) -> None:
    assert result["status"] == "completed"
    assert result["change_preview"]["schema_version"] == "webterm.change-preview.v1"
    assert result["change_preview"]["operation"] == operation
    assert result["change_preview"]["dry_run"] is True
    assert result["change_preview"]["diff"]


def test_every_mutating_ops_manifest_declares_dry_run_and_change_preview() -> None:
    manifests = [manifest for manifest in NODE_MANIFESTS.values() if manifest.mutates_state]

    assert manifests
    for manifest in manifests:
        assert manifest.supports_dry_run is True, manifest.node_type
        assert "dry_run" in manifest.input_schema["properties"], manifest.node_type
        assert "change_preview" in manifest.output_schema["properties"], manifest.node_type

    ssh_manifest = NODE_MANIFESTS["agent/ssh_cmd"]
    assert "dry_run" in ssh_manifest.input_schema["properties"]
    assert "change_preview" in ssh_manifest.output_schema["properties"]


def test_executor_rejects_successful_mutation_without_change_preview(monkeypatch) -> None:
    run = _make_run("missing-preview")

    class MissingPreviewNode:
        async def execute(self, _ctx):
            return NodeResult(output={"output": "mutation claimed success"})

    monkeypatch.setattr(registry, "create", lambda *args, **kwargs: MissingPreviewNode())

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "service",
            "type": "ops/service_action",
            "data": {"action": "restart", "service": "nginx"},
        },
        {},
        {},
        run,
    )

    assert result["status"] == "failed"
    assert "required change preview" in result["error"]


def test_file_write_dry_run_returns_redacted_diff_without_write(monkeypatch) -> None:
    run = _make_run("dry-file")
    server = _server(run, "file-srv")

    async def fake_secret(_server):
        return ""

    async def fake_read(_server, *, secret="", path="", max_bytes=0):
        return {"path": path, "filename": "app.conf", "size": 11, "encoding": "utf-8", "content": "mode=old\n"}

    async def fail_write(*args, **kwargs):
        raise AssertionError("dry-run must not write")

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.read_text_file", fake_read)
    monkeypatch.setattr("studio.executor.nodes.ops.write_text_file", fail_write)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "file",
            "type": "ops/file_action",
            "data": {
                "server_id": server.id,
                "action": "write",
                "path": "/etc/app.conf",
                "content": "mode=new\ntoken=super-secret-value\n",
                "dry_run": True,
            },
        },
        {},
        {},
        run,
    )

    _assert_preview(result, operation="file.write")
    assert "super-secret-value" not in result["change_preview"]["diff"]
    assert "REDACTED" in result["change_preview"]["diff"]


def test_package_action_dry_run_does_not_invoke_package_manager(monkeypatch) -> None:
    run = _make_run("dry-package")
    server = _server(run, "package-srv")

    async def fake_secret(_server):
        return ""

    async def fake_capabilities(_server, *, secret=""):
        return {"package_manager": "apt"}

    async def fake_packages(_server, *, secret=""):
        return {"package_manager": "apt", "installed": [], "updates": [], "summary": {"update_candidates": 0}}

    async def fail_command(*args, **kwargs):
        raise AssertionError("dry-run must not invoke apt")

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_capabilities", fake_capabilities)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_packages", fake_packages)
    monkeypatch.setattr("studio.executor.nodes.ops._run_command_result", fail_command)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "package",
            "type": "ops/package_action",
            "data": {"server_id": server.id, "action": "install", "packages": ["curl"], "dry_run": True},
        },
        {},
        {},
        run,
    )

    _assert_preview(result, operation="package.install")
    assert result["package_action"]["exit_code"] is None


@pytest.mark.parametrize(
    ("node_type", "data", "operation", "read_patch", "read_value", "write_patch"),
    [
        (
            "ops/service_action",
            {"action": "restart", "service": "nginx"},
            "service.restart",
            "studio.executor.nodes.ops.get_linux_ui_service_logs",
            {"source": "systemctl", "content": "active"},
            "studio.executor.nodes.ops.run_linux_ui_service_action",
        ),
        (
            "ops/docker_action",
            {"action": "restart", "container": "web"},
            "docker.restart",
            "studio.executor.nodes.ops.get_linux_ui_docker",
            {"summary": {"running": 1}, "containers": [{"name": "web", "state": "running"}]},
            "studio.executor.nodes.ops.run_linux_ui_docker_action",
        ),
    ],
)
def test_service_and_docker_dry_run_skip_mutation(
    monkeypatch,
    node_type: str,
    data: dict,
    operation: str,
    read_patch: str,
    read_value: dict,
    write_patch: str,
) -> None:
    run = _make_run(f"dry-{node_type.rsplit('/', 1)[-1]}")
    server = _server(run, "ops-srv")

    async def fake_secret(_server):
        return ""

    async def fake_read(*args, **kwargs):
        return read_value

    async def fail_write(*args, **kwargs):
        raise AssertionError("dry-run must not mutate")

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr(read_patch, fake_read)
    monkeypatch.setattr(write_patch, fail_write)

    result = async_to_sync(_execute_registry_node)(
        {"id": "action", "type": node_type, "data": {"server_id": server.id, "dry_run": True, **data}},
        {},
        {},
        run,
    )

    _assert_preview(result, operation=operation)
    assert result["action_result"]["dry_run"] is True


def test_process_dry_run_does_not_send_signal(monkeypatch) -> None:
    run = _make_run("dry-process")
    server = _server(run, "process-srv")

    async def fake_secret(_server):
        return ""

    async def fail_action(*args, **kwargs):
        raise AssertionError("dry-run must not send a signal")

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.run_linux_ui_process_action", fail_action)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "process",
            "type": "ops/process_action",
            "data": {"server_id": server.id, "pid": 4321, "action": "terminate", "dry_run": True},
        },
        {},
        {},
        run,
    )

    _assert_preview(result, operation="process.terminate")


def test_disk_cleanup_dry_run_executes_only_guarded_preview_command(monkeypatch) -> None:
    run = _make_run("dry-disk")
    server = _server(run, "disk-srv")
    captured: dict[str, str] = {}

    async def fake_secret(_server):
        return ""

    async def fake_disk(_server, *, secret=""):
        return {"summary": {"cleanup_candidates": 1}, "cleanup_candidates": ["/tmp/old"]}

    async def fake_command(_server, *, secret="", command=""):
        captured["command"] = command
        return {"stdout": "__PLAN__\n/tmp/old\n__ACTION__\ndry_run=true\n__ACTION_EXIT__=0\n", "stderr": "", "exit_code": 0}

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_disk", fake_disk)
    monkeypatch.setattr("studio.executor.nodes.ops._run_command_result", fake_command)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "disk",
            "type": "ops/disk_cleanup",
            "data": {"server_id": server.id, "action": "tmp_cleanup", "dry_run": True},
        },
        {},
        {},
        run,
    )

    _assert_preview(result, operation="disk.tmp_cleanup")
    assert "if [ 1 -eq 1 ]" in captured["command"]


def test_alert_update_dry_run_preserves_database_row() -> None:
    run = _make_run("dry-alert")
    server = _server(run, "alert-srv")
    alert = ServerAlert.objects.create(
        server=server,
        alert_type=ServerAlert.TYPE_SERVICE,
        severity=ServerAlert.SEVERITY_WARNING,
        title="Service degraded",
        message="latency",
    )

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "alert",
            "type": "ops/alert_update",
            "data": {"alert_id": alert.id, "action": "resolve", "dry_run": True},
        },
        {},
        {},
        run,
    )

    alert.refresh_from_db()
    _assert_preview(result, operation="alert.resolve")
    assert alert.is_resolved is False
    assert result["alert"]["is_resolved"] is True


def test_mutating_ssh_dry_run_does_not_connect(monkeypatch) -> None:
    run = _make_run("dry-ssh")
    server = _server(run, "ssh-srv")

    def fail_connect(**kwargs):
        raise AssertionError("dry-run must not open SSH")

    monkeypatch.setattr("asyncssh.connect", fail_connect)

    result = async_to_sync(PipelineExecutor(run)._execute_node)(
        {
            "id": "ssh",
            "type": "agent/ssh_cmd",
            "data": {"server_id": server.id, "command": "systemctl restart nginx", "dry_run": True},
        },
        {},
        {},
    )

    _assert_preview(result, operation="ssh.command")
    assert result["command"]["executed"] is False
