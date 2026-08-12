from __future__ import annotations

from types import SimpleNamespace

import pytest

from servers.services.terminal_manual_command_state import ManualCommandState
from servers.services.terminal_manual_input import handle_terminal_input


class DummyStdin:
    def __init__(self) -> None:
        self.writes: list[str] = []

    def write(self, data: str) -> None:
        self.writes.append(data)


class DummyProc:
    def __init__(self) -> None:
        self.stdin = DummyStdin()


class DummyOwner:
    def __init__(self) -> None:
        self.server = SimpleNamespace(id=20, name="lunix")
        self._user_id = 1
        self._ssh_proc = DummyProc()
        self._server_connection_id = "term-manual-test"
        self._ai_marker_token = "manualtest"
        self.manual_state = ManualCommandState()
        self._nova_session_context = {"cwd": "/srv/app"}
        self.recent_activity: list[dict] = []
        self.sent: list[dict] = []
        self.mutation_allowed = False

    def _marker_prefix(self) -> str:
        return f"__WEUAI_EXIT_{self._ai_marker_token}_"

    def _append_nova_recent_activity(self, **kwargs) -> None:
        self.recent_activity.append(kwargs)

    async def _safe_send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def handle_input(self, data: str) -> None:
        await handle_terminal_input(
            self.manual_state,
            data,
            server=self.server,
            user_id=self._user_id,
            ssh_proc=self._ssh_proc,
            server_connection_id=self._server_connection_id,
            session_context=self._nova_session_context,
            marker_prefix=self._marker_prefix(),
            intercept_editors=True,
            send_json=self._safe_send_json,
            append_recent_activity=self._append_nova_recent_activity,
            log_activity=_log_activity,
            persist_result=_persist_result,
            mutation_allowed=self.mutation_allowed,
        )


async def _log_activity(**kwargs) -> None:
    _log_activity.calls.append(kwargs)


_log_activity.calls = []


async def _persist_result(**kwargs) -> None:
    _persist_result.calls.append(kwargs)


_persist_result.calls = []


@pytest.fixture(autouse=True)
def _clear_calls():
    _log_activity.calls = []
    _persist_result.calls = []


@pytest.mark.asyncio
async def test_handle_terminal_input_adds_marker_for_single_safe_command():
    owner = DummyOwner()

    await owner.handle_input("systemctl status nginx\r")

    assert owner.manual_state.active_command_id == 1_000_000
    assert owner.manual_state.pending_commands[0]["command"] == "systemctl status nginx"
    assert owner.manual_state.pending_commands[0]["cwd"] == "/srv/app"
    assert any("__WEUAI_EXIT_manualtest_1000000" in item for item in owner._ssh_proc.stdin.writes)
    assert _log_activity.calls[0]["description"] == "systemctl status nginx"
    assert _persist_result.calls == []


@pytest.mark.asyncio
async def test_handle_terminal_input_persists_uncaptured_block_without_marker():
    owner = DummyOwner()
    owner.mutation_allowed = True

    await owner.handle_input("if true; then\r")

    assert owner.manual_state.active_command_id is None
    assert not any("__WEUAI_EXIT_" in item for item in owner._ssh_proc.stdin.writes)
    assert _persist_result.calls == [
        {
            "user_id": 1,
            "server_id": 20,
            "session_id": "term-manual-test",
            "command": "if true; then",
            "output": "",
            "exit_code": None,
            "cwd": "/srv/app",
        }
    ]
    assert owner.recent_activity[0]["command"] == "if true; then"


@pytest.mark.asyncio
async def test_handle_terminal_input_intercepts_editor_commands_without_persisting():
    owner = DummyOwner()
    owner.mutation_allowed = True

    await owner.handle_input("nano /etc/hosts\r")

    assert owner._ssh_proc.stdin.writes == ["\x15\x03"]
    assert owner.sent == [
        {
            "type": "editor_intercept",
            "path": "/etc/hosts",
            "editor": "nano",
            "sudo": False,
        }
    ]
    assert owner.manual_state.pending_commands == []
    assert _persist_result.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        "touch /tmp/pilot-bypass",
        "mkdir -p /tmp/pilot-bypass",
        "printf owned > /tmp/pilot-bypass",
        "systemctl restart nginx",
        "sudo -n cat /etc/shadow",
    ],
)
async def test_restricted_manual_terminal_never_forwards_mutating_or_sudo_command(command):
    owner = DummyOwner()

    await owner.handle_input(command)
    assert owner._ssh_proc.stdin.writes == []

    await owner.handle_input("\r")

    assert owner._ssh_proc.stdin.writes == ["\x15"]
    assert all(command not in write for write in owner._ssh_proc.stdin.writes)
    assert owner.sent[-1]["code"] == "read_only_command_required"
    assert _persist_result.calls == []


@pytest.mark.asyncio
async def test_restricted_manual_terminal_reconstructs_split_read_only_command():
    owner = DummyOwner()

    await owner.handle_input("systemctl status")
    assert owner._ssh_proc.stdin.writes == []

    await owner.handle_input(" nginx\r")

    assert owner._ssh_proc.stdin.writes[:2] == ["\x15", "systemctl status nginx\r"]
    assert any("__WEUAI_EXIT_manualtest_1000000" in write for write in owner._ssh_proc.stdin.writes)


@pytest.mark.asyncio
async def test_restricted_manual_terminal_does_not_forward_shell_history_escape_or_enter():
    owner = DummyOwner()

    await owner.handle_input("\x1b[A\r")

    assert owner._ssh_proc.stdin.writes == []
    assert owner.sent == []
