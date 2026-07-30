from __future__ import annotations

from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from servers.models import Server, ServerAlert
from studio.models import Pipeline, PipelineRun
from studio.pipeline.pipeline_executor import _execute_registry_node

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

    async def _public_resolver(_host: str, _port: int) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr("studio.pipeline.pipeline_agent_runtime.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline.pipeline_run_state.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline.pipeline_run_state.get_channel_layer", lambda: None)
    monkeypatch.setattr("app.outbound_http._resolve_host_addresses", _public_resolver)


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
        def __init__(
            self,
            timeout: int = 15,
            follow_redirects: bool = False,
            trust_env: bool = False,
        ) -> None:
            self.timeout = timeout
            self.follow_redirects = follow_redirects
            self.trust_env = trust_env

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def request(self, method: str, url, **_kwargs):
            captured["method"] = method
            captured["url"] = str(url)
            return SimpleNamespace(status_code=204, text="healthy", headers={})

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
    assert captured == {"method": "GET", "url": "https://93.184.216.34/health"}
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
