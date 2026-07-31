from __future__ import annotations

from types import SimpleNamespace

from asgiref.sync import async_to_sync

from servers.consumers import SSHTerminalConsumer
from servers.consumers.ssh_terminal import TerminalTransport
from servers.services.terminal_ai.run_controller import TerminalAiRunController
from servers.services.terminal_ai.session import TerminalAiSession
from servers.services.terminal_ai.state import TerminalAiState
from servers.services.terminal_manual_command_state import ManualCommandState
from servers.services.terminal_transport_state import TerminalTransportState


class DummyStdin:
    def __init__(self) -> None:
        self.writes: list[str] = []

    def write(self, data: str) -> None:
        self.writes.append(data)


class DummyProc:
    def __init__(self) -> None:
        self.stdin = DummyStdin()


def _immediate_sync_to_async(func, thread_sensitive=True):  # noqa: ARG001
    async def runner(*args, **kwargs):
        return func(*args, **kwargs)

    return runner


async def _fake_log_user_activity_async(**_kwargs) -> None:
    return None


def _build_consumer() -> SSHTerminalConsumer:
    consumer = SSHTerminalConsumer()
    consumer.server = SimpleNamespace(id=20, name="lunix")
    consumer._user_id = 1
    consumer._transport_state = TerminalTransportState(
        ssh_proc=DummyProc(),
        server_connection_id="term-manual-test",
    )
    consumer._ai_state = TerminalAiState.create(
        run_controller_factory=TerminalAiRunController,
        session_factory=TerminalAiSession,
        settings={},
    )
    consumer._ai_state.session.marker_token = "manualtest"
    consumer._manual_state = ManualCommandState()
    return consumer


def _patch_terminal_io(monkeypatch, persisted: list[dict]) -> None:
    monkeypatch.setattr(
        "servers.consumers.ssh_terminal_session_ops.log_user_activity_async",
        _fake_log_user_activity_async,
    )
    monkeypatch.setattr(
        "servers.consumers.ssh_terminal_session_ops.database_sync_to_async",
        _immediate_sync_to_async,
    )
    monkeypatch.setattr(
        "servers.consumers.ssh_terminal_io.database_sync_to_async",
        _immediate_sync_to_async,
    )
    monkeypatch.setattr(
        TerminalTransport,
        "_persist_manual_terminal_command_result",
        staticmethod(lambda **kwargs: persisted.append(kwargs)),
    )


def test_manual_terminal_command_capture_persists_output_and_exit_code(monkeypatch):
    persisted: list[dict] = []
    _patch_terminal_io(monkeypatch, persisted)
    consumer = _build_consumer()

    async_to_sync(consumer._handle_input)("systemctl status nginx\r")

    assert consumer._manual_state.active_command_id == 1_000_000
    assert any("__WEUAI_EXIT_manualtest_1000000" in item for item in consumer._transport_state.ssh_proc.stdin.writes)

    consumer._append_manual_output("systemctl status nginx\nnginx.service - active (running)\n")
    async_to_sync(consumer._finalize_manual_terminal_command)(1_000_000, 0)

    assert len(persisted) == 1
    assert persisted[0]["command"] == "systemctl status nginx"
    assert "nginx.service - active (running)" in persisted[0]["output"]
    assert persisted[0]["exit_code"] == 0


def test_manual_terminal_multiline_block_skips_marker_injection(monkeypatch):
    persisted: list[dict] = []
    _patch_terminal_io(monkeypatch, persisted)
    consumer = _build_consumer()

    async_to_sync(consumer._handle_input)("if true; then\r")

    assert consumer._manual_state.active_command_id is None
    assert not any("__WEUAI_EXIT_" in item for item in consumer._transport_state.ssh_proc.stdin.writes)
    assert len(persisted) == 1
    assert persisted[0]["command"] == "if true; then"
    assert persisted[0]["output"] == ""
    assert persisted[0]["exit_code"] is None
