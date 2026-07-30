from __future__ import annotations

from typing import Any, Protocol


class PipelineSshProvider(Protocol):
    async def get_server_connect_kwargs(self, server: Any, *, connect_timeout: int | None = None) -> dict[str, Any]: ...

    def get_server_sudo_password(self, server: Any) -> str: ...

    async def run_agent_command(
        self,
        server: Any,
        command: str,
        *,
        connect_kwargs: dict[str, Any] | None = None,
        input_text: str | None = None,
        timeout_seconds: int | None = None,
    ) -> Any: ...


_pipeline_ssh_provider: PipelineSshProvider | None = None


def register_pipeline_ssh_provider(provider: PipelineSshProvider | None) -> None:
    global _pipeline_ssh_provider
    _pipeline_ssh_provider = provider


def _require_pipeline_ssh_provider() -> PipelineSshProvider:
    if _pipeline_ssh_provider is None:
        raise RuntimeError("Pipeline SSH provider is not registered")
    return _pipeline_ssh_provider


async def get_server_connect_kwargs(server: Any, *, connect_timeout: int | None = None) -> dict[str, Any]:
    return await _require_pipeline_ssh_provider().get_server_connect_kwargs(
        server,
        connect_timeout=connect_timeout,
    )


def get_server_sudo_password(server: Any) -> str:
    return _require_pipeline_ssh_provider().get_server_sudo_password(server)


async def run_agent_command(
    server: Any,
    command: str,
    *,
    connect_kwargs: dict[str, Any] | None = None,
    input_text: str | None = None,
    timeout_seconds: int | None = None,
) -> Any:
    return await _require_pipeline_ssh_provider().run_agent_command(
        server,
        command,
        connect_kwargs=connect_kwargs,
        input_text=input_text,
        timeout_seconds=timeout_seconds,
    )
