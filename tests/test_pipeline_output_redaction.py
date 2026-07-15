import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from studio.models import Pipeline, PipelineRun
from studio.pipeline_executor import PipelineExecutor

pytestmark = pytest.mark.django_db(transaction=True)


class _FakeHttpResponse:
    def __init__(self, status_code: int = 204):
        self.status_code = status_code


def _make_run() -> PipelineRun:
    user = User.objects.create_user(username="pipeline-output-redaction-user", password="x")
    pipeline = Pipeline.objects.create(name="Output Redaction", owner=user, nodes=[], edges=[])
    return PipelineRun.objects.create(pipeline=pipeline, status=PipelineRun.STATUS_RUNNING, context={})


def test_webhook_output_redacts_context_headers_and_result_url(monkeypatch):
    run = _make_run()
    executor = PipelineExecutor(run)
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, timeout: int = 30) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict | None = None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers or {}
            return _FakeHttpResponse()

    monkeypatch.setattr("studio.executor.nodes.output_webhook.httpx.AsyncClient", FakeHttpClient)

    result = async_to_sync(executor._execute_node)(
        {
            "id": "webhook_out",
            "type": "output/webhook",
            "data": {
                "url": "https://example.com/hook?token=sk-proj-abc123def456ghi789jkl012mno",
                "extra_payload": {"note": "{prep_output}", "auth": "{auth_header}"},
                "headers": {"Authorization": "{auth_header}"},
            },
        },
        {"auth_header": "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload"},
        {"prep": {"status": "completed", "output": "done password=super-secret"}},
    )

    payload_text = str(captured["json"])
    header_text = str(captured["headers"])
    assert result["status"] == "completed"
    assert captured["url"] == "https://example.com/hook?token=sk-proj-abc123def456ghi789jkl012mno"
    assert "super-secret" not in payload_text
    assert "Bearer eyJ" not in payload_text
    assert "Bearer eyJ" not in header_text
    assert "sk-proj-" not in result["output"]
    assert "[REDACTED:secret_assignment]" in payload_text
    assert "[REDACTED:auth_header]" in header_text
