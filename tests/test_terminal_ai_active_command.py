from __future__ import annotations

from types import SimpleNamespace

from servers.services.terminal_ai.active_command import (
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
    owner = SimpleNamespace()
    future = FakeFuture()

    initialize_active_command_state(owner)
    register_active_command(owner, 7, future)

    assert active_command_id(owner) == 7
    assert exit_future(owner, 7) is future
    assert owner._ai_active_output == ""


def test_resolve_pop_and_cancel_exit_futures():
    owner = SimpleNamespace()
    first = FakeFuture()
    second = FakeFuture()
    initialize_active_command_state(owner)
    register_active_command(owner, 1, first)
    owner._ai_exit_futures[2] = second

    resolve_exit_future(owner, 1, 130)
    pop_exit_future(owner, 1)
    cancel_exit_futures(owner)

    assert first.result == 130
    assert 1 not in owner._ai_exit_futures
    assert second.cancelled is True
    assert owner._ai_exit_futures == {}


def test_append_tail_and_clear_active_command():
    owner = SimpleNamespace()
    initialize_active_command_state(owner)

    append_active_output(owner, "ignored")
    assert active_output_tail(owner) == ""

    register_active_command(owner, 3, FakeFuture())
    append_active_output(owner, "abc")
    append_active_output(owner, "def", limit=4)

    assert active_output_tail(owner) == "cdef"

    clear_active_command(owner, cmd_id=99)
    assert active_command_id(owner) == 3

    clear_active_command(owner, cmd_id=3)
    assert active_command_id(owner) is None
    assert active_output_tail(owner) == ""
