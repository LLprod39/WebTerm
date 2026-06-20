from __future__ import annotations

from typing import Protocol


class ChatServerProvider(Protocol):
    def get_servers_context_for_prompt(self, user_id: int) -> str: ...

    def get_server_names_for_user(self, user_id: int) -> list[str]: ...

    async def try_server_command_by_name(self, user_id: int, message: str) -> str | None: ...


_chat_server_provider: ChatServerProvider | None = None


def register_chat_server_provider(provider: ChatServerProvider | None) -> None:
    """Register server-aware helpers used by chat orchestration."""
    global _chat_server_provider
    _chat_server_provider = provider


def get_servers_context_for_prompt(user_id: int) -> str:
    if _chat_server_provider is None:
        return ""
    return _chat_server_provider.get_servers_context_for_prompt(user_id)


def get_server_names_for_user(user_id: int) -> list[str]:
    if _chat_server_provider is None:
        return []
    return list(_chat_server_provider.get_server_names_for_user(user_id))


async def try_server_command_by_name(user_id: int, message: str) -> str | None:
    if _chat_server_provider is None:
        return None
    return await _chat_server_provider.try_server_command_by_name(user_id, message)
