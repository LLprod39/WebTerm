from servers.agent_inputs import build_agent_materials_prompt


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
    assert "кандидат на выполнение" in prompt
    assert "сопоставь его с целью/описанием задачи" in prompt
    assert "mktemp -d" in prompt
    assert "chmod" in prompt
    assert "timeout" in prompt
    assert "exit code" in prompt
    assert "удали временный файл/директорию" in prompt
    assert "не запускай его молча" in prompt
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
