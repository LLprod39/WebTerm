"""Drive shipped parse_response for classic ACTION text and JSON action form."""

from __future__ import annotations

from app.agent_kernel.runtime.parsing import parse_json_action, parse_response


def test_parse_classic_thought_action_text():
    text = (
        'THOUGHT: Сначала проверю сервис\n'
        'ACTION: ssh_execute {"server": "prod-web-1", "command": "systemctl status nginx"}'
    )
    thought, name, args = parse_response(text)
    assert "проверю" in thought or "сервис" in thought
    assert name == "ssh_execute"
    assert args.get("server") == "prod-web-1"
    assert "systemctl status nginx" in str(args.get("command") or "")


def test_parse_json_action_object():
    raw = (
        '{"thinking": "читаю логи", "tool": "ssh_execute", '
        '"args": {"server": "prod-web-1", "command": "journalctl -n 50 --no-pager"}}'
    )
    thought, name, args = parse_response(raw)
    assert name == "ssh_execute"
    assert args["command"] == "journalctl -n 50 --no-pager"
    assert "логи" in thought


def test_parse_json_action_alternate_keys():
    raw = '{"action": "read_console", "arguments": {"server": "s1", "lines": 40}}'
    thought, name, args = parse_response(raw)
    assert name == "read_console"
    assert args.get("server") == "s1"
    assert args.get("lines") == 40


def test_parse_json_and_text_prefer_text_action_when_both_present():
    # Classic ACTION wins when both styles appear.
    raw = (
        'THOUGHT: use text form\n'
        'ACTION: ssh_execute {"command": "uptime"}\n'
        '{"tool": "report", "args": {"text": "nope"}}'
    )
    thought, name, args = parse_response(raw)
    assert name == "ssh_execute"
    assert args.get("command") == "uptime"


def test_parse_json_action_helper_rejects_non_tool_objects():
    assert parse_json_action('{"foo": 1}') is None
    assert parse_json_action("not json") is None


def test_parse_final_answer_without_action():
    thought, name, args = parse_response("THOUGHT: Цель достигнута, сервис healthy.\nИтог: ok")
    assert name is None
    assert args == {}
    assert "достигнута" in thought or "healthy" in thought or "ok" in thought.lower()


def test_engines_delegate_to_shared_parse_response():
    import inspect

    from servers.agent_engine import AgentEngine
    from servers.multi_agent_engine import MultiAgentEngine

    assert "parse_response" in inspect.getsource(AgentEngine._parse_response)
    assert "parse_response" in inspect.getsource(MultiAgentEngine._parse_response)
