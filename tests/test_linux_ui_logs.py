from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from servers import linux_ui, linux_ui_resources, linux_ui_runtime
from servers.linux_ui_commands import LOG_SOURCES


@pytest.fixture
def log_shell(monkeypatch, tmp_path):
    """Execute the generated read command locally, without SSH or a database."""
    shell = shutil.which("sh")
    if not shell and os.name == "nt":
        candidate = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Git/bin/sh.exe"
        if candidate.is_file():
            shell = str(candidate)
    if not shell:
        pytest.skip("A POSIX shell is required to verify log command exit status")
    monkeypatch.setitem(LOG_SOURCES, "syslog", {**LOG_SOURCES["syslog"], "path": "qa-read.log"})
    prefix = {"command": ""}

    async def run(_server, *, command, **_kwargs):
        result = subprocess.run(
            [shell, "-c", prefix["command"] + command],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}

    monkeypatch.setattr(linux_ui_resources, "_run_command_result", run)
    monkeypatch.setattr(linux_ui, "_run_command_result", run)
    return tmp_path, prefix


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["first QA line\nsecond QA line\n", "", None])
async def test_file_log_distinguishes_readable_empty_and_missing(log_shell, content):
    root, _ = log_shell
    if content is not None:
        (root / "qa-read.log").write_text(content, encoding="utf-8")
    logs = await linux_ui_resources.get_linux_ui_logs(SimpleNamespace(), source="syslog")
    preset = next(item for item in logs["presets"] if item["key"] == "syslog")
    assert logs["available"] is (content is not None)
    assert preset["available"] is logs["available"]
    assert logs["content"] == (content or "").strip()
    if content is None:
        assert "не найден" in logs["unavailable_reason"]
    else:
        assert logs["unavailable_reason"] == ""


@pytest.mark.asyncio
async def test_file_log_does_not_report_failed_tail_as_success(log_shell):
    root, prefix = log_shell
    (root / "qa-read.log").write_text("not returned on failure", encoding="utf-8")
    # The file passed the existence/readability probe but became unreadable at read time.
    prefix["command"] = "tail() { printf 'tail: Permission denied\\n' >&2; return 1; };\n"
    logs = await linux_ui_resources.get_linux_ui_logs(SimpleNamespace(), source="syslog")
    assert logs["available"] is False
    assert logs["content"] == ""
    assert "недостаточно прав" in logs["unavailable_reason"]
    assert next(item for item in logs["presets"] if item["key"] == "syslog")["available"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("reader", ["journal", "service", "service_drawer", "docker_drawer"])
async def test_failed_log_command_is_unavailable_and_keeps_diagnostics_out_of_content(log_shell, reader):
    _, prefix = log_shell
    prefix["command"] = (
        "journalctl() { printf 'Permission denied\\n' >&2; return 1; };\n"
        "docker() { printf 'permission denied while connecting to daemon\\n' >&2; return 1; };\n"
    )
    if reader == "service_drawer":
        logs = await linux_ui.get_linux_ui_service_logs(SimpleNamespace(), service="qa.service")
    elif reader == "docker_drawer":
        logs = await linux_ui_resources.get_linux_ui_docker_logs(SimpleNamespace(), container="qa-container")
    else:
        logs = await linux_ui_resources.get_linux_ui_logs(SimpleNamespace(), source=reader, service="qa.service")
    assert logs["available"] is False
    assert logs["content"] == ""
    assert "недостаточно прав" in logs["unavailable_reason"]


@pytest.mark.asyncio
async def test_missing_journal_tool_is_unavailable(log_shell):
    _, prefix = log_shell
    prefix["command"] = "PATH=/nonexistent;\n"
    logs = await linux_ui_resources.get_linux_ui_logs(SimpleNamespace())
    assert logs["available"] is False
    assert logs["content"] == ""
    assert "нет утилиты" in logs["unavailable_reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_code,available", [(3, True), (4, False)])
async def test_service_status_fallback_distinguishes_inactive_from_missing(log_shell, exit_code, available):
    _, prefix = log_shell
    prefix["command"] = (
        "PATH=/nonexistent;\n"
        f"systemctl() {{ printf 'Loaded: qa.service\\nActive: inactive\\n'; return {exit_code}; }};\n"
    )
    logs = await linux_ui.get_linux_ui_service_logs(SimpleNamespace(), service="qa.service")
    assert logs["available"] is available
    if available:
        assert "Active: inactive" in logs["content"]
        assert logs["unavailable_reason"] == ""
    else:
        assert logs["content"] == ""
        assert logs["unavailable_reason"]


@pytest.mark.asyncio
@pytest.mark.parametrize("reader", ["journal", "service_drawer", "docker_drawer"])
async def test_ssh_failure_is_an_error_not_an_empty_log(monkeypatch, reader):
    async def disconnected(*_args, **_kwargs):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(linux_ui_runtime.ssh_connection_pool, "run_command", disconnected)
    server = SimpleNamespace(network_config={}, sudo_auth_mode="none")
    with pytest.raises(ConnectionError, match="соединение SSH"):
        if reader == "service_drawer":
            await linux_ui.get_linux_ui_service_logs(server, service="qa.service")
        elif reader == "docker_drawer":
            await linux_ui_resources.get_linux_ui_docker_logs(server, container="qa-container")
        else:
            await linux_ui_resources.get_linux_ui_logs(server)


@pytest.mark.asyncio
async def test_success_without_log_response_framing_is_not_an_empty_log(monkeypatch):
    async def incomplete(_server, **_kwargs):
        return {"stdout": "incomplete SSH response", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(linux_ui_resources, "_run_command_result", incomplete)
    with pytest.raises(ConnectionError, match="неполный ответ"):
        await linux_ui_resources.get_linux_ui_logs(SimpleNamespace())
