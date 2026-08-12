from __future__ import annotations

import pytest
from loguru import logger

from app.ai_runtime import ProviderRuntimeError
from app.core.llm_provider_stream import stream_provider_chat
from core_ui.activity import log_llm_activity
from core_ui.logging_setup import _record_filter
from core_ui.models import UserActivityLog


def test_persistent_log_filter_redacts_tokens_and_device_codes() -> None:
    record = {
        "message": "token=super-secret-value user_code=ABCD-EFGH safe=status-ok",
        "extra": {},
    }

    assert _record_filter(record) is True
    assert "super-secret-value" not in record["message"]
    assert "ABCD-EFGH" not in record["message"]
    assert "safe=status-ok" in record["message"]
    assert record["extra"] == {"request_id": "-", "channel": "-", "user_id": "-"}


@pytest.mark.django_db
def test_llm_activity_never_persists_prompt_text() -> None:
    marker = "PROMPT-MUST-NOT-BE-LOGGED-4821"

    log_llm_activity(
        provider="test",
        model_name="test-model",
        prompt=f"diagnose {marker}",
        response="safe response",
        duration_ms=5,
    )

    row = UserActivityLog.objects.get(action="llm_request")
    assert marker not in row.description
    assert marker not in repr(row.metadata)
    assert row.metadata["prompt_length"] == len(f"diagnose {marker}")


@pytest.mark.asyncio
async def test_stream_provider_log_contains_metadata_but_never_prompt(monkeypatch) -> None:
    marker = "PROMPT-LOG-MARKER-9471"
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(str(message)), format="{message}")

    class FakeProvider:
        gemini_api_key = ""
        grok_api_key = ""
        anthropic_api_key = ""
        openai_api_key = ""

        async def _load_managed_api_keys(self):
            return None

        def _get_ollama_base_url(self):
            return ""

    monkeypatch.setattr(
        "app.core.llm_provider_stream.resolve_stream_provider",
        lambda **_kwargs: ("unsupported", "metadata-model"),
    )
    try:
        with pytest.raises(ProviderRuntimeError, match="Unknown model target"):
            async for _chunk in stream_provider_chat(
                FakeProvider(),
                f"private prompt {marker}",
                model="unsupported",
            ):
                pass
    finally:
        logger.remove(sink_id)

    rendered = "\n".join(messages)
    assert marker not in rendered
    assert "prompt_length=" in rendered
    assert "metadata-model" in rendered
