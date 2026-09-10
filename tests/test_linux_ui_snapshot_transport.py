import json
from types import SimpleNamespace

import pytest

from servers import linux_ui, linux_ui_runtime
from servers.views.server_linux_ui import _linux_ui_error_response


@pytest.fixture
def ssh_server():
    return SimpleNamespace(network_config={}, sudo_auth_mode="none", host="qa.example.test", username="qa")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reader",
    [linux_ui_runtime.get_linux_ui_capabilities, linux_ui.get_linux_ui_overview, linux_ui.get_linux_ui_processes],
    ids=["capabilities", "overview", "processes"],
)
@pytest.mark.parametrize("transport_failure", ["connection_refused", "no_exit_status"])
async def test_snapshot_transport_failure_is_not_a_successful_empty_snapshot(
    monkeypatch, ssh_server, reader, transport_failure
):
    async def disconnected(*_args, **_kwargs):
        if transport_failure == "connection_refused":
            raise ConnectionError("connection refused")
        return SimpleNamespace(stdout="", stderr="connection dropped", exit_status=None)

    monkeypatch.setattr(linux_ui_runtime.ssh_connection_pool, "run_command", disconnected)
    with pytest.raises(ConnectionError, match="SSH"):
        await reader(ssh_server)


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [{}, {"exit_code": None}, {"exit_code": -1}, {"exit_code": -15}])
async def test_snapshot_command_requires_a_completed_remote_exit_status(monkeypatch, ssh_server, result):
    async def incomplete(*_args, **_kwargs):
        return {"stdout": "partial output", **result}

    monkeypatch.setattr(linux_ui_runtime, "_run_command_result", incomplete)
    with pytest.raises(ConnectionError, match="SSH"):
        await linux_ui_runtime._run_command(ssh_server, command="read-only snapshot")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stdout,stderr,expected",
    [("diagnostic data", "warning", "diagnostic data"), ("", "tool unavailable", "tool unavailable")],
)
async def test_nonzero_remote_command_diagnostics_remain_available(monkeypatch, ssh_server, stdout, stderr, expected):
    async def diagnostic(*_args, **_kwargs):
        return {"stdout": stdout, "stderr": stderr, "exit_code": 3, "success": False}

    monkeypatch.setattr(linux_ui_runtime, "_run_command_result", diagnostic)
    assert await linux_ui_runtime._run_command(ssh_server, command="read-only diagnostic") == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("systemctl,is_systemd,available", [(1, 1, True), (1, 0, False), (0, 1, False), (0, 0, False)])
async def test_services_require_systemctl_and_a_booted_systemd(monkeypatch, ssh_server, systemctl, is_systemd, available):
    async def capabilities(*_args, **_kwargs):
        return {
            "stdout": f"cmd_systemctl={systemctl}\nis_systemd={is_systemd}\ncmd_sh=1\ncmd_ip=1\n",
            "stderr": "",
            "exit_code": 0,
        }

    monkeypatch.setattr(linux_ui_runtime, "_run_command_result", capabilities)
    result = await linux_ui_runtime.get_linux_ui_capabilities(ssh_server)
    assert result["available_apps"]["services"] is available
    assert result["is_systemd"] is bool(is_systemd)
    assert result["available_apps"]["settings"] is True
    assert result["available_apps"]["network"] is True


def test_snapshot_transport_failure_response_is_actionable_without_raw_connection_details():
    response = _linux_ui_error_response(ConnectionError("private connection diagnostics"))
    payload = json.loads(response.content)
    assert response.status_code == 502
    assert payload["success"] is False
    assert payload["code"] == "ssh_connection_failed"
    assert "SSH" in payload["error"] and "повторите попытку" in payload["error"]
    assert "private connection diagnostics" not in payload["error"]
