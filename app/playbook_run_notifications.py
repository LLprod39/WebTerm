"""Dependency-inverted delivery hook for terminal playbook runs."""

from __future__ import annotations

from collections.abc import Callable

PlaybookRunTerminalNotifier = Callable[[int], None]

_playbook_run_terminal_notifier: PlaybookRunTerminalNotifier | None = None


def register_playbook_run_terminal_notifier(provider: PlaybookRunTerminalNotifier | None) -> None:
    """Register the delivery-layer notifier used after a run becomes terminal."""

    global _playbook_run_terminal_notifier
    _playbook_run_terminal_notifier = provider


def notify_playbook_run_terminal(run_id: int) -> None:
    """Notify the registered delivery layer, failing closed when it is unavailable."""

    provider = _playbook_run_terminal_notifier
    if provider is None:
        raise RuntimeError("Playbook run terminal notifier is not registered")
    provider(int(run_id))
