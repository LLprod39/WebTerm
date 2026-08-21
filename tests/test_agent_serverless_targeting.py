from servers.agents.agent_budgets import resolve_agent_runtime_budget
from servers.agents.agent_targeting import server_requirement_reasons


def test_external_agent_needs_no_server_for_safe_tools():
    assert server_requirement_reasons(
        mode="full",
        commands=[],
        tools_config={"report": True, "read_material": True, "read_skill": True},
        sudo_policy="disabled",
        skill_slugs=[],
    ) == []


def test_ssh_capabilities_require_server():
    reasons = server_requirement_reasons(
        mode="full",
        commands=[],
        tools_config={"ssh_execute": True},
        sudo_policy="disabled",
        skill_slugs=[],
    )
    assert reasons == ["server_tools"]


def test_runtime_budget_grows_with_task_complexity():
    simple = resolve_agent_runtime_budget(mode="full", goal="Summarize a document")
    complex_task = resolve_agent_runtime_budget(
        mode="full",
        goal="Investigate and document a cross-system incident " * 20,
        skill_slugs=["logs", "api"],
        input_artifacts=[{"name": "runbook"}],
    )
    assert simple.max_iterations == 40
    assert complex_task.max_iterations > simple.max_iterations
    assert complex_task.session_timeout_seconds > simple.session_timeout_seconds
