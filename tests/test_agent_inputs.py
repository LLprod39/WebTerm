from servers.agents.agent_inputs import build_agent_materials_prompt


def test_script_material_adds_runtime_protocol():
    prompt = build_agent_materials_prompt(
        [
            {
                "kind": "script",
                "name": "healthcheck.sh",
                "content": "systemctl status nginx\njournalctl -u nginx -n 50",
            }
        ]
    )

    assert "Script material runtime protocol" in prompt
    # Assert the safety contract, not a particular prose revision.
    assert "run_script_material" in prompt
    assert "dry_run=true" in prompt
    assert "exit_code + stdout/stderr" in prompt
    assert "проверяй side-effects" in prompt
    assert "ask_user" in prompt
    assert "не silent production blast" in prompt
    assert "самодельный аналог" in prompt
    assert "```bash" in prompt
    assert "systemctl status nginx" in prompt


def test_non_script_material_does_not_add_runtime_protocol():
    prompt = build_agent_materials_prompt(
        [
            {
                "kind": "document",
                "name": "runbook.md",
                "content": "Check nginx logs and write a report.",
            }
        ]
    )

    assert "Script material runtime protocol" not in prompt
    assert "mktemp -d" not in prompt
    assert "```text" in prompt
    assert "Check nginx logs" in prompt
