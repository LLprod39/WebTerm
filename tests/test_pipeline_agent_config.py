from __future__ import annotations

from studio.ops_controls import assert_agents_not_paused, get_ops_control_status, set_ops_paused
from studio.pipeline_agent_config import (
    INTERACTION_UNATTENDED,
    agent_node_allows_ask_user,
    default_max_iterations,
    is_unattended_mode,
    resolve_agent_model_preference,
    resolve_interaction_mode,
    resolve_tools_config,
)


def test_tools_mode_allowlist_empty_fails():
    tools, err = resolve_tools_config({"tools_mode": "allowlist", "allowed_tools": []})
    assert err is not None
    assert "allowlist" in err
    assert tools == {}


def test_tools_mode_all_returns_empty_map():
    tools, err = resolve_tools_config({"tools_mode": "all"})
    assert err is None
    assert tools == {}


def test_tools_mode_allowlist_ok():
    tools, err = resolve_tools_config(
        {"tools_mode": "allowlist", "allowed_tools": ["ssh_execute", "read_console"]}
    )
    assert err is None
    assert tools == {"ssh_execute": True, "read_console": True}


def test_tools_mode_denylist_disables_named_tools():
    tools, err = resolve_tools_config(
        {"tools_mode": "denylist", "allowed_tools": ["ask_user"]},
        all_tool_names=["ssh_execute", "ask_user", "report"],
    )
    assert err is None
    assert tools["ssh_execute"] is True
    assert tools["report"] is True
    assert tools["ask_user"] is False


def test_legacy_empty_allowed_tools_means_all():
    tools, err = resolve_tools_config({"allowed_tools": []})
    assert err is None
    assert tools == {}


def test_unattended_for_schedule_and_explicit():
    assert resolve_interaction_mode({}, trigger_type="schedule") == INTERACTION_UNATTENDED
    assert resolve_interaction_mode({}, trigger_type="webhook") == INTERACTION_UNATTENDED
    assert is_unattended_mode({"interaction_mode": "unattended"})
    assert not is_unattended_mode({"interaction_mode": "interactive"}, trigger_type="schedule")


def test_default_iterations_unified():
    assert default_max_iterations("agent/react") == 6
    assert default_max_iterations("agent/multi") == 6


def test_model_preference_no_experimental_hardcode():
    provider, model = resolve_agent_model_preference({})
    assert provider == "auto"
    assert model is None


def test_ask_user_allowlist_detection():
    assert agent_node_allows_ask_user({"tools_mode": "all"})
    assert not agent_node_allows_ask_user(
        {"tools_mode": "allowlist", "allowed_tools": ["ssh_execute"]}
    )
    assert agent_node_allows_ask_user(
        {"tools_mode": "allowlist", "allowed_tools": ["ask_user"]}
    )


def test_ops_kill_switch_pause_and_resume(tmp_path, monkeypatch):
    flag = tmp_path / "kill.json"
    monkeypatch.setenv("WEBTERM_OPS_KILL_SWITCH_PATH", str(flag))
    monkeypatch.delenv("WEBTERM_OPS_PAUSE_ALL", raising=False)
    set_ops_paused(False)
    assert assert_agents_not_paused() is None
    set_ops_paused(True, reason="test pause", actor="pytest")
    err = assert_agents_not_paused()
    assert err is not None
    assert "kill switch" in err.lower() or "Paused" in err or "pause" in err.lower()
    status = get_ops_control_status()
    assert status["paused"] is True
    set_ops_paused(False)
    assert assert_agents_not_paused() is None
