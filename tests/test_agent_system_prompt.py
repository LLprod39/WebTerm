from __future__ import annotations

from servers.services.terminal_ai.agent.prompts import build_system_prompt
from servers.services.terminal_ai.agent.tools import ServerTarget, default_tool_set


def _primary() -> ServerTarget:
    return ServerTarget(
        name="primary",
        server_id=1,
        display_name="srv-main",
        host="10.0.0.1",
        is_primary=True,
    )


class TestAgentSystemPrompt:
    """Guard prompt directives other parts of the product rely on."""

    def test_system_prompt_enforces_russian_output(self):
        prompt = build_system_prompt(
            tools=default_tool_set(),
            primary=_primary(),
            extras={},
        )
        assert "Russian" in prompt, "system prompt must force Russian output for user-facing fields"
        for field in ("thinking", "final_text", "ask_user", "todo"):
            assert field in prompt, f"language policy must name the user-facing field {field!r}"

    def test_system_prompt_inlines_memory_context(self):
        memory = (
            "Сервер: prod-db (10.0.0.5)\n"
            "Тип: postgres 14; конфиг /etc/postgresql/14/main/postgresql.conf\n"
            "Риски: WAL архив на /mnt/wal — не заполнять >80%"
        )
        prompt = build_system_prompt(
            tools=default_tool_set(),
            primary=_primary(),
            extras={},
            memory_context=memory,
        )
        assert "Persistent server memory" in prompt
        for line in memory.splitlines():
            assert line in prompt, f"memory line missing from prompt: {line!r}"

    def test_system_prompt_memory_block_has_fallback_when_empty(self):
        prompt = build_system_prompt(
            tools=default_tool_set(),
            primary=_primary(),
            extras={},
            memory_context="",
        )
        assert "Persistent server memory" in prompt
        assert "remember" in prompt
