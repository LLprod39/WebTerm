"""Explicit behavioral collaborators for the SSH terminal WebSocket adapter."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from servers.consumers.ssh_terminal_agent_runner import TerminalAgentRunOperations
from servers.consumers.ssh_terminal_agent_support import TerminalAgentSupportOperations
from servers.consumers.ssh_terminal_ai_controls import TerminalAiControlOperations
from servers.consumers.ssh_terminal_ai_execution import TerminalAiExecutionOperations
from servers.consumers.ssh_terminal_ai_tools import TerminalAiToolOperations
from servers.consumers.ssh_terminal_io import TerminalIoOperations
from servers.consumers.ssh_terminal_lifecycle import TerminalLifecycleOperations
from servers.consumers.ssh_terminal_session_ops import TerminalSessionOperations

Dependency = Callable[[], "_TerminalCollaborator | None"]
_MISSING = object()


class _TerminalCollaborator:
    """Share explicit state while resolving behavior only through declared peers."""

    def __init__(self, *, adapter: Any, dependencies: tuple[Dependency, ...]) -> None:
        self._adapter = adapter
        self._dependencies = dependencies

    @property
    def server(self):
        return self._adapter.server

    @server.setter
    def server(self, value) -> None:
        self._adapter.server = value

    @property
    def _user_id(self):
        return self._adapter._user_id

    @_user_id.setter
    def _user_id(self, value) -> None:
        self._adapter._user_id = value

    @property
    def _ai_state(self):
        return self._adapter._ai_state

    @property
    def _manual_state(self):
        return self._adapter._manual_state

    @property
    def _transport_state(self):
        return self._adapter._transport_state

    def __getattr__(self, name: str):
        adapter_value = inspect.getattr_static(self._adapter, name, _MISSING)
        if adapter_value is not _MISSING:
            return getattr(self._adapter, name)
        for dependency in self._dependencies:
            collaborator = dependency()
            if collaborator is not None and inspect.getattr_static(collaborator, name, _MISSING) is not _MISSING:
                return getattr(collaborator, name)
        raise AttributeError(f"{type(self).__name__!s} has no declared dependency for {name!r}")


class TerminalTransport(
    _TerminalCollaborator,
    TerminalLifecycleOperations,
    TerminalSessionOperations,
    TerminalIoOperations,
):
    """Own connection lifecycle, SSH transport, terminal input, and WebSocket output."""


class TerminalAiRunner(
    _TerminalCollaborator,
    TerminalAiControlOperations,
    TerminalAiToolOperations,
    TerminalAiExecutionOperations,
):
    """Own AI request control, plan mutation, and command execution."""


class TerminalAgentBridge(
    _TerminalCollaborator,
    TerminalAgentRunOperations,
    TerminalAgentSupportOperations,
):
    """Own the bridge from terminal AI sessions to agent planning and memory."""
