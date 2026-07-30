from __future__ import annotations

from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from servers.models import Server
from studio.models import Pipeline, PipelineRun
from studio.pipeline.pipeline_executor import _execute_registry_node


def _make_run(username: str) -> PipelineRun:
    owner = User.objects.create_user(username=username, password="x")
    pipeline = Pipeline.objects.create(
        name=f"Pipeline for {username}",
        owner=owner,
        nodes=[{"id": "manual", "type": "trigger/manual", "position": {"x": 0, "y": 0}, "data": {}}],
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
    )


def test_ops_service_action_uses_context_service_name(monkeypatch, db):
    run = _make_run("ops-service-context-user")
    server = Server.objects.create(user=run.pipeline.owner, name="service-srv", host="10.0.0.18", username="root")
    captured: dict[str, object] = {}

    async def fake_secret(_server):
        return ""

    async def fake_service_logs(_server, *, secret="", service="", lines=40):
        captured["last_log_service"] = service
        return {"source": "systemctl", "content": "active"}

    async def fake_service_action(_server, *, secret="", service="", action="restart"):
        captured["service"] = service
        captured["action"] = action
        return {"service": service, "success": True, "dangerous": False, "status_excerpt": "reloaded"}

    monkeypatch.setattr("studio.executor.nodes.ops._server_secret", fake_secret)
    monkeypatch.setattr("studio.executor.nodes.ops.get_linux_ui_service_logs", fake_service_logs)
    monkeypatch.setattr("studio.executor.nodes.ops.run_linux_ui_service_action", fake_service_action)

    result = async_to_sync(_execute_registry_node)(
        {
            "id": "service_action",
            "type": "ops/service_action",
            "data": {"server_id_context_key": "target_server_id", "action": "reload"},
        },
        {"target_server_id": server.id, "service_name": "nginx"},
        {},
        run,
    )

    assert result["status"] == "completed"
    assert captured["service"] == "nginx"
    assert captured["action"] == "reload"
    assert result["action_result"]["service"] == "nginx"
