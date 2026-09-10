from types import SimpleNamespace

import pytest

from servers import linux_ui


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state,excerpt,exit_code,expected_running",
    [("Z", "450 qa sleep <defunct>", 0, False),
     ("Z+", "450 qa sleep <defunct>", 0, False),
     ("S", "450 qa sleep 3600", 0, True),
     ("", "", 0, False),
     ("S", "450 root sleep 3600", 1, True)],
)
async def test_signal_result_distinguishes_zombie_from_live_process(monkeypatch, state, excerpt, exit_code, expected_running):
    async def run(_server, **kwargs):
        assert "ps -p 450 -o stat=,pid=" in kwargs["command"]
        return {"stdout": f"__ACTION_EXIT__={exit_code}\n__PROCESS__\n{state} {excerpt}\n", "stderr": ""}

    monkeypatch.setattr(linux_ui, "_run_command_result", run)
    result = await linux_ui.run_linux_ui_process_action(SimpleNamespace(), pid=450, action="terminate")
    assert result["still_running"] is expected_running
    assert result["success"] is (exit_code == 0)
    assert result["process_excerpt"] == f"{state} {excerpt}".strip()
