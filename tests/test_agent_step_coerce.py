from servers.services.terminal_ai.agent.schemas import AgentStep
from servers.services.terminal_ai.schemas import parse_or_repair


def test_agent_step_coerces_final_text_without_tool():
    step, err = parse_or_repair('{"final_text":"nikitavm"}', AgentStep)
    assert err == ""
    assert step is not None
    assert step.tool == "done"
    assert step.final_text == "nikitavm"


def test_agent_step_coerces_name_alias_to_tool():
    step, err = parse_or_repair('{"name":"shell","args":{"cmd":"hostname"}}', AgentStep)
    assert err == ""
    assert step is not None
    assert step.tool == "shell"
    assert step.args.get("cmd") == "hostname"
