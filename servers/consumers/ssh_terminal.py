"""Thin Channels adapter for interactive SSH terminal sessions."""

from __future__ import annotations

import inspect
from typing import Any

from channels.db import database_sync_to_async as database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from core_ui.activity import log_user_activity_async as log_user_activity_async
from servers.consumers.ssh_terminal_collaborators import (
    TerminalAgentBridge,
    TerminalAiRunner,
    TerminalTransport,
)
from servers.models_inventory import Server
from servers.services import terminal_input
from servers.services.terminal_ai import preferences as ai_preferences
from servers.services.terminal_ai.run_controller import TerminalAiRunController
from servers.services.terminal_ai.session import TerminalAiSession
from servers.services.terminal_ai.state import TerminalAiState
from servers.services.terminal_manual_command_state import ManualCommandState
from servers.services.terminal_transport_state import TerminalTransportState

_TermSize = terminal_input.TerminalSize
_MISSING = object()

__all__ = [
    "SSHTerminalConsumer",
    "TerminalAgentBridge",
    "TerminalAiRunner",
    "TerminalTransport",
    "database_sync_to_async",
    "log_user_activity_async",
]


class SSHTerminalConsumer(AsyncJsonWebsocketConsumer):
    """Adapt Channels lifecycle calls to three explicit terminal collaborators."""

    _TerminalAiSessionCls = TerminalAiSession
    _TerminalAiRunControllerCls = TerminalAiRunController

    _default_ai_settings = staticmethod(ai_preferences.default_ai_settings)
    _normalize_ai_settings = staticmethod(ai_preferences.normalize_ai_settings)
    _clone_ai_settings = staticmethod(ai_preferences.clone_ai_settings)
    _should_use_manual_command_marker = staticmethod(terminal_input.should_use_manual_command_marker)

    server: Server | None = None
    _user_id: int | None = None
    _automation_allowed: bool = False
    _ai_state: TerminalAiState
    _manual_state: ManualCommandState
    _transport_state: TerminalTransportState
    terminal_transport: TerminalTransport
    terminal_ai_runner: TerminalAiRunner
    terminal_agent_bridge: TerminalAgentBridge

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._ai_state = TerminalAiState.create(
            run_controller_factory=self._TerminalAiRunControllerCls,
            session_factory=self._TerminalAiSessionCls,
            settings=self._default_ai_settings(),
        )
        self._manual_state = ManualCommandState()
        self._transport_state = TerminalTransportState()
        self.terminal_transport = TerminalTransport(
            adapter=self,
            dependencies=(lambda: self.terminal_ai_runner, lambda: self.terminal_agent_bridge),
        )
        self.terminal_ai_runner = TerminalAiRunner(
            adapter=self,
            dependencies=(lambda: self.terminal_transport, lambda: self.terminal_agent_bridge),
        )
        self.terminal_agent_bridge = TerminalAgentBridge(
            adapter=self,
            dependencies=(lambda: self.terminal_transport, lambda: self.terminal_ai_runner),
        )

    async def connect(self) -> None:
        await self.terminal_transport.connect()

    async def disconnect(self, code) -> None:
        await self.terminal_transport.disconnect(code)

    async def receive_json(self, content: Any, **kwargs: Any) -> None:
        await self.terminal_transport.receive_json(content, **kwargs)

    def __getattr__(self, name: str):
        for field in ("terminal_transport", "terminal_ai_runner", "terminal_agent_bridge"):
            collaborator = self.__dict__.get(field)
            if collaborator is not None and inspect.getattr_static(collaborator, name, _MISSING) is not _MISSING:
                return getattr(collaborator, name)
        raise AttributeError(f"{type(self).__name__!s} has no terminal behavior {name!r}")
