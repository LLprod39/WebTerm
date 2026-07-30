from __future__ import annotations

from servers.services.terminal_ai.active_command import (
    TerminalAiActiveCommandState,
    active_command_id,
    active_output_tail,
    append_active_output,
    cancel_exit_futures,
    clear_active_command,
    exit_future,
    initialize_active_command_state,
    pop_exit_future,
    register_active_command,
    resolve_exit_future,
)


class FakeFuture:
    def __init__(self):
        self.result = None
        self.cancelled = False

    def done(self):
        return self.result is not None or self.cancelled

    def set_result(self, value):
        self.result = value

    def cancel(self):
        self.cancelled = True


def test_initialize_and_register_active_command_state():
    state = TerminalAiActiveCommandState()
    future = FakeFuture()

    initialize_active_command_state(state)
    register_active_command(state, 7, future)

    assert active_command_id(state) == 7
    assert exit_future(state, 7) is future
    assert state.output == ""


def test_resolve_pop_and_cancel_exit_futures():
    state = TerminalAiActiveCommandState()
    first = FakeFuture()
    second = FakeFuture()
    initialize_active_command_state(state)
    register_active_command(state, 1, first)
    state.exit_futures[2] = second

    resolve_exit_future(state, 1, 130)
    pop_exit_future(state, 1)
    cancel_exit_futures(state)

    assert first.result == 130
    assert 1 not in state.exit_futures
    assert second.cancelled is True
    assert state.exit_futures == {}


def test_append_tail_and_clear_active_command():
    state = TerminalAiActiveCommandState()
    initialize_active_command_state(state)

    append_active_output(state, "ignored")
    assert active_output_tail(state) == ""

    register_active_command(state, 3, FakeFuture())
    append_active_output(state, "abc")
    append_active_output(state, "def", limit=4)

    assert active_output_tail(state) == "cdef"

    clear_active_command(state, cmd_id=99)
    assert active_command_id(state) == 3

    clear_active_command(state, cmd_id=3)
    assert active_command_id(state) is None
    assert active_output_tail(state) == ""
