import pytest

import app.chat_server_provider as chat_server_provider
from core_ui.views import chat_helpers


class _FakeChatServerProvider:
    def get_servers_context_for_prompt(self, user_id: int) -> str:
        return f"context:{user_id}"

    def get_server_names_for_user(self, user_id: int) -> list[str]:
        return [f"server-{user_id}"]

    async def try_server_command_by_name(self, user_id: int, message: str) -> str | None:
        return f"command:{user_id}:{message}"


@pytest.mark.asyncio
async def test_chat_helpers_use_registered_server_provider(monkeypatch):
    monkeypatch.setattr(chat_server_provider, "_chat_server_provider", _FakeChatServerProvider())

    assert chat_helpers._get_servers_context_for_prompt(7) == "context:7"
    assert await chat_helpers._get_server_names_for_user(7) == ["server-7"]
    assert await chat_helpers._try_server_command_by_name(7, "df") == "command:7:df"
