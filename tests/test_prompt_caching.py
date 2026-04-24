"""Tests for 4.3 — Prompt caching support.

Verifies:
1. ``build_planner_prompt_parts`` returns a proper ``(system, user)`` tuple.
2. ``build_planner_prompt`` backward-compat: full prompt == system + user.
3. ``LLMProvider.stream_chat`` accepts ``system_prompt`` kwarg and each
   provider branch uses it instead of the default "You are a helpful
   assistant." message.
"""

import pytest

# ---------------------------------------------------------------------------
# 1. Prompt builder split
# ---------------------------------------------------------------------------


class TestPlannerPromptParts:
    """build_planner_prompt_parts returns a proper (system, user) split."""

    @staticmethod
    def _base_args() -> dict:
        return {
            "user_message": "Проверь свободное место на /opt/legacy",
            "rules_context": "Не удалять логи без бэкапа.\n- df -h обязательна.",
            "terminal_tail": "root@srv:~# ",
            "history": [{"role": "user", "text": "Привет"}, {"role": "assistant", "text": "Здравствуйте"}],
            "unavailable_cmds": ["netstat"],
            "chat_mode": "agent",
            "execution_mode": "step",
        }

    def test_returns_tuple(self):
        from servers.services.terminal_ai.prompts import build_planner_prompt_parts

        result = build_planner_prompt_parts(**self._base_args())
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_system_contains_role_and_rules(self):
        from servers.services.terminal_ai.prompts import build_planner_prompt_parts

        system, _user = build_planner_prompt_parts(**self._base_args())
        assert "DevOps/SSH ассистент" in system
        assert "df -h" in system
        assert "JSON" in system

    def test_user_contains_request_and_history(self):
        from servers.services.terminal_ai.prompts import build_planner_prompt_parts

        _system, user = build_planner_prompt_parts(**self._base_args())
        assert "/opt/legacy" in user
        assert "Привет" in user
        assert "Верни только JSON" in user

    def test_system_does_not_contain_user_message(self):
        from servers.services.terminal_ai.prompts import build_planner_prompt_parts

        system, _user = build_planner_prompt_parts(**self._base_args())
        assert "/opt/legacy" not in system

    def test_user_does_not_contain_role_instructions(self):
        from servers.services.terminal_ai.prompts import build_planner_prompt_parts

        _system, user = build_planner_prompt_parts(**self._base_args())
        assert "DevOps/SSH ассистент" not in user

    def test_backward_compat_full_prompt(self):
        """build_planner_prompt == system + '\\n\\n' + user."""
        from servers.services.terminal_ai.prompts import (
            build_planner_prompt,
            build_planner_prompt_parts,
        )

        full = build_planner_prompt(**self._base_args())
        system, user = build_planner_prompt_parts(**self._base_args())
        assert full == f"{system}\n\n{user}"

    def test_dry_run_block_in_system(self):
        from servers.services.terminal_ai.prompts import build_planner_prompt_parts

        system, _user = build_planner_prompt_parts(**self._base_args(), dry_run=True)
        assert "DRY-RUN" in system

    def test_unavailable_tools_in_system(self):
        from servers.services.terminal_ai.prompts import build_planner_prompt_parts

        system, _user = build_planner_prompt_parts(**self._base_args())
        assert "netstat" in system


# ---------------------------------------------------------------------------
# 2. LLMProvider.stream_chat accepts system_prompt
# ---------------------------------------------------------------------------


class TestStreamChatSystemPrompt:
    """stream_chat forwards system_prompt to the provider API call."""

    @pytest.mark.asyncio
    async def test_grok_uses_system_prompt(self):
        """Grok branch should put system_prompt into the system message."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.core.llm import LLMProvider

        provider = LLMProvider()
        provider.grok_api_key = "test-key"

        captured_data: dict = {}

        # Mock aiohttp session
        mock_response = AsyncMock()
        mock_response.status = 200

        async def fake_content():
            line = json.dumps({"choices": [{"delta": {"content": "ok"}}]})
            yield f"data: {line}\n".encode()
            yield b"data: [DONE]\n"

        mock_response.content = fake_content()
        mock_response.text = AsyncMock(return_value="")

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        def capture_post(url, headers=None, json=None):
            captured_data.update(json or {})
            return mock_session_ctx

        mock_session.post = capture_post

        with (
            patch("aiohttp.ClientSession", return_value=mock_session),
            patch("app.core.model_config.model_manager") as mm,
        ):
            mm.config = MagicMock()
            mm.config.grok_enabled = True
            mm.get_chat_model.return_value = "grok-test"
            chunks = []
            async for chunk in provider.stream_chat(
                "user msg",
                model="grok",
                system_prompt="Custom system instructions",
            ):
                chunks.append(chunk)

        assert captured_data.get("messages", [{}])[0].get("content") == "Custom system instructions"

    @pytest.mark.asyncio
    async def test_grok_default_system_when_none(self):
        """Without system_prompt, Grok uses the default 'helpful assistant' message."""
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.core.llm import LLMProvider

        provider = LLMProvider()
        provider.grok_api_key = "test-key"

        captured_data: dict = {}

        mock_response = AsyncMock()
        mock_response.status = 200

        async def fake_content():
            line = json.dumps({"choices": [{"delta": {"content": "ok"}}]})
            yield f"data: {line}\n".encode()
            yield b"data: [DONE]\n"

        mock_response.content = fake_content()
        mock_response.text = AsyncMock(return_value="")

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        def capture_post(url, headers=None, json=None):
            captured_data.update(json or {})
            return mock_session_ctx

        mock_session.post = capture_post

        with (
            patch("aiohttp.ClientSession", return_value=mock_session),
            patch("app.core.model_config.model_manager") as mm,
        ):
            mm.config = MagicMock()
            mm.config.grok_enabled = True
            mm.get_chat_model.return_value = "grok-test"
            async for _ in provider.stream_chat("user msg", model="grok"):
                pass

        assert captured_data["messages"][0]["content"] == "You are a helpful assistant."
