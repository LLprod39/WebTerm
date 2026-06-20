from __future__ import annotations

from email import message_from_string

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from studio.models import Pipeline, PipelineRun
from studio.pipeline_executor import PipelineExecutor

pytestmark = pytest.mark.django_db(transaction=True)


class _FakeSMTP:
    sent_messages: list[dict[str, str]] = []

    def __init__(self, host: str, port: int, timeout: int = 30) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def ehlo(self) -> None:
        return None

    def starttls(self) -> None:
        return None

    def login(self, username: str, password: str) -> None:
        return None

    def sendmail(self, from_email: str, recipients: list[str], message: str) -> None:
        self.__class__.sent_messages.append(
            {
                "from_email": from_email,
                "recipients": ",".join(recipients),
                "message": message,
            }
        )


class _FakeLoop:
    async def run_in_executor(self, executor, func):
        return func()


class _FakeHttpResponse:
    def __init__(self, status_code: int = 200, text: str = "ok") -> None:
        self.status_code = status_code
        self.text = text


def _make_user(username: str) -> User:
    return User.objects.create_user(username=username, password="x")


def _make_run(username: str = "notification-node-user") -> PipelineRun:
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


def _plain_text_parts(message: str) -> list[str]:
    parsed_message = message_from_string(message)
    return [
        (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8")
        for part in parsed_message.walk()
        if part.get_content_type() == "text/plain"
    ]


def _patch_email_transport(monkeypatch, smtp_class: type[_FakeSMTP] = _FakeSMTP) -> None:
    monkeypatch.setattr(
        "studio.executor.nodes.output_email._global_email_defaults",
        lambda: ("ops@example.com", "smtp.example.com", "", "", ""),
    )
    monkeypatch.setattr("studio.executor.nodes.output_email.asyncio.get_event_loop", lambda: _FakeLoop())
    monkeypatch.setattr("smtplib.SMTP", smtp_class)
    monkeypatch.setattr("smtplib.SMTP_SSL", smtp_class)


def test_output_email_node_sends_rendered_message(monkeypatch):
    run = _make_run("email-node-user")
    executor = PipelineExecutor(run)
    _FakeSMTP.sent_messages = []

    _patch_email_transport(monkeypatch)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "email_out",
            "type": "output/email",
            "data": {"subject": "Run {ticket}", "body": "Body: {prep_output}"},
        },
        {"ticket": "INC-505"},
        {"prep": {"status": "completed", "output": "email ready"}},
    )

    assert result["status"] == "completed"
    assert "ops@example.com" in result["output"]
    assert len(_FakeSMTP.sent_messages) == 1
    assert any("Body: email ready" in part for part in _plain_text_parts(_FakeSMTP.sent_messages[0]["message"]))


def test_output_email_node_redacts_secret_body_and_preserves_approval_links(monkeypatch):
    run = _make_run("email-redaction-user")
    executor = PipelineExecutor(run)
    _FakeSMTP.sent_messages = []
    approval_url = "http://localhost/api/studio/runs/1/approve/node/?token=approval-secret&decision=approved"

    _patch_email_transport(monkeypatch)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "email_out",
            "type": "output/email",
            "data": {
                "subject": "Run {ticket}",
                "body": "Approve: {approval_url}\nBody: {prep_output}",
                "_redaction_preserve_values": [approval_url],
                "_redaction_preserve_context_keys": ["approval_url"],
            },
        },
        {"ticket": "INC-506", "approval_url": approval_url},
        {"prep": {"status": "completed", "output": "email password=super-secret"}},
    )

    assert result["status"] == "completed"
    body = "\n".join(_plain_text_parts(_FakeSMTP.sent_messages[0]["message"]))
    assert approval_url in body
    assert "super-secret" not in body
    assert "[REDACTED:secret_assignment]" in body


def test_output_email_node_fails_on_smtp_error(monkeypatch):
    run = _make_run("email-error-user")
    executor = PipelineExecutor(run)

    class BrokenSMTP(_FakeSMTP):
        def sendmail(self, from_email: str, recipients: list[str], message: str) -> None:
            raise RuntimeError("smtp down")

    _patch_email_transport(monkeypatch, BrokenSMTP)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "email_out",
            "type": "output/email",
            "data": {"subject": "Run {ticket}", "body": "Body"},
        },
        {"ticket": "INC-507"},
        {},
    )

    assert result["status"] == "failed"
    assert result["error"] == "SMTP error: smtp down"


def test_output_telegram_node_sends_rendered_message(monkeypatch):
    run = _make_run("telegram-node-user")
    executor = PipelineExecutor(run)
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, timeout: int = 30) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict):
            captured["url"] = url
            captured["json"] = json
            return _FakeHttpResponse(status_code=200)

    monkeypatch.setattr("studio.executor.nodes.output_telegram._global_tg_defaults", lambda: ("token-123", "chat-9"))
    monkeypatch.setattr("studio.executor.nodes.output_telegram.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "telegram_out",
            "type": "output/telegram",
            "data": {"message": "Pipeline {pipeline_name} run {run_id}\nTicket {ticket}\n{all_outputs}"},
        },
        {"ticket": "INC-606"},
        {"prep": {"status": "completed", "output": "telegram ready"}},
    )

    assert result["status"] == "completed"
    assert "chat-9" in result["output"]
    assert captured["url"] == "https://api.telegram.org/bottoken-123/sendMessage"
    assert "Pipeline Pipeline for telegram-node-user run" in str(captured["json"]["text"])
    assert "INC-606" in str(captured["json"]["text"])
    assert "telegram ready" in str(captured["json"]["text"])


def test_output_telegram_node_redacts_secret_message(monkeypatch):
    run = _make_run("telegram-redaction-user")
    executor = PipelineExecutor(run)
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, timeout: int = 30) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict):
            captured["json"] = json
            return _FakeHttpResponse(status_code=200)

    monkeypatch.setattr("studio.executor.nodes.output_telegram._global_tg_defaults", lambda: ("token-123", "chat-9"))
    monkeypatch.setattr("studio.executor.nodes.output_telegram.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "telegram_out",
            "type": "output/telegram",
            "data": {"message": "Pipeline {pipeline_name}\n{all_outputs}\nDirect {prep_output}"},
        },
        {},
        {"prep": {"status": "completed", "output": "telegram password=super-secret"}},
    )

    assert result["status"] == "completed"
    text = str(captured["json"]["text"])
    assert "super-secret" not in text
    assert "[REDACTED:secret_assignment]" in text


def test_output_telegram_node_fails_on_api_error(monkeypatch):
    run = _make_run("telegram-api-error-user")
    executor = PipelineExecutor(run)

    class FakeHttpClient:
        def __init__(self, timeout: int = 30) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict):
            return _FakeHttpResponse(status_code=400, text="bad request")

    monkeypatch.setattr("studio.executor.nodes.output_telegram._global_tg_defaults", lambda: ("token-123", "chat-9"))
    monkeypatch.setattr("studio.executor.nodes.output_telegram.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "telegram_out",
            "type": "output/telegram",
            "data": {"message": "Pipeline {pipeline_name}"},
        },
        {},
        {},
    )

    assert result["status"] == "failed"
    assert result["error"] == "Telegram API error 400: bad request"
