"""Explicit long-lived state for terminal AI orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from servers.services.terminal_ai.active_command import TerminalAiActiveCommandState
from servers.services.terminal_ai.run_controller import TerminalAiRunController
from servers.services.terminal_ai.session import TerminalAiSession


@dataclass
class TerminalAiState:
    """All mutable AI-session state composed by the terminal consumer.

    Consumer mixins share this object instead of relying on attributes that a
    different mixin happened to initialize during ``connect()``.
    """

    run: TerminalAiRunController
    session: TerminalAiSession
    settings: dict[str, Any]
    active_command: TerminalAiActiveCommandState = field(default_factory=TerminalAiActiveCommandState)
    allowlist_patterns: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    unavailable_commands: set[str] = field(default_factory=set)
    error_retries: dict[int, int] = field(default_factory=dict)
    audit_context: dict[str, Any] = field(default_factory=dict)
    background_tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    extra_connections: dict[str, Any] = field(default_factory=dict)

    @property
    def lock(self) -> asyncio.Lock:
        return self.run.lock

    @classmethod
    def create(
        cls,
        *,
        run_controller_factory: Callable[[], TerminalAiRunController],
        session_factory: Callable[[], TerminalAiSession],
        settings: dict[str, Any],
    ) -> TerminalAiState:
        return cls(
            run=run_controller_factory(),
            session=session_factory(),
            settings=dict(settings),
        )

    def reset_connection_state(self) -> None:
        self.active_command.reset()
        self.allowlist_patterns.clear()
        self.history.clear()
        self.unavailable_commands.clear()
        self.error_retries.clear()
        self.audit_context.clear()
        self.extra_connections.clear()
