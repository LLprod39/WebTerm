from __future__ import annotations

from django.contrib.auth.models import User

from studio.models import Pipeline, PipelineRun

RUNTIME_COVERED_NODE_TYPES = {
    "trigger/manual",
    "trigger/webhook",
    "trigger/schedule",
    "trigger/monitoring",
    "agent/react",
    "agent/multi",
    "agent/ssh_cmd",
    "agent/llm_query",
    "agent/mcp_call",
    "ops/server_snapshot",
    "ops/log_query",
    "ops/file_action",
    "ops/package_action",
    "ops/disk_cleanup",
    "ops/backup_restore_check",
    "ops/service_action",
    "ops/docker_action",
    "ops/process_action",
    "ops/http_check",
    "ops/alert_update",
    "logic/condition",
    "logic/parallel",
    "logic/merge",
    "logic/wait",
    "logic/human_approval",
    "logic/telegram_input",
    "output/report",
    "output/webhook",
    "output/email",
    "output/telegram",
}


class Decision:
    def __init__(
        self,
        *,
        allowed: bool = True,
        reason: str = "",
        sandbox_profile: str = "ops_exec",
        notes: list[str] | None = None,
    ) -> None:
        self.allowed = allowed
        self.reason = reason
        self.sandbox_profile = sandbox_profile
        self.notes = list(notes or [])


class PermissionEngine:
    def __init__(self, mode: str | None = None, **kwargs) -> None:
        self.mode = mode
        self.sudo_policy = kwargs.get("sudo_policy", "")

    def evaluate(self, spec, payload):
        return Decision()

    def record_success(self, spec, payload, output) -> None:
        return None

    def verification_summary(self) -> str:
        return "verified"


class SandboxManager:
    def validate(self, spec, payload, sandbox_profile):
        return Decision()


class HookManager:
    async def post_tool_use(self, tool_name: str, output: str) -> str:
        return output


class FakeHttpResponse:
    def __init__(self, status_code: int = 200, text: str = "ok") -> None:
        self.status_code = status_code
        self.text = text


def make_user(username: str, *, is_staff: bool = False) -> User:
    return User.objects.create_user(username=username, password="x", is_staff=is_staff)


def make_run(username: str = "node-suite-user") -> PipelineRun:
    owner = make_user(username)
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


def disable_activity_logging(monkeypatch) -> None:
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("studio.pipeline.pipeline_agent_runtime.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline.pipeline_run_state.log_user_activity_async", _noop)
    monkeypatch.setattr("studio.pipeline.pipeline_run_state.get_channel_layer", lambda: None)
