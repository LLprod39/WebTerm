"""Tests for app.core.model_config.ModelManager.resolve_purpose (F1-8).

Ensures terminal AI purposes route to cheap ``chat`` tier by default.
"""
from __future__ import annotations

from app.core.model_config import ModelConfig, ModelManager


def _make_manager(**config_overrides) -> ModelManager:
    mgr = ModelManager()
    mgr.config = ModelConfig(**config_overrides)
    return mgr


class TestPurposeAliasesForTerminalAi:
    def test_terminal_planning_routes_to_chat(self):
        mgr = _make_manager(internal_llm_provider="openai", chat_model_openai="gpt-5-mini")
        provider, model = mgr.resolve_purpose("terminal_planning")
        assert provider == "openai"
        assert model == "gpt-5-mini"

    def test_memory_extraction_routes_to_chat(self):
        mgr = _make_manager(internal_llm_provider="gemini", chat_model_gemini="models/gemini-3-flash-preview")
        provider, model = mgr.resolve_purpose("memory_extraction")
        assert provider == "gemini"
        assert model == "models/gemini-3-flash-preview"

    def test_terminal_planning_uses_chat_llm_override_when_set(self):
        # Operator overrides chat_llm_provider → terminal_planning follows it.
        mgr = _make_manager(
            internal_llm_provider="openai",
            chat_llm_provider="claude",
            chat_llm_model="claude-haiku-4-5-20251001",
        )
        provider, model = mgr.resolve_purpose("terminal_planning")
        assert provider == "claude"
        assert model == "claude-haiku-4-5-20251001"

    def test_memory_extraction_uses_chat_llm_override(self):
        mgr = _make_manager(
            internal_llm_provider="openai",
            chat_llm_provider="grok",
            chat_llm_model="grok-4-1-fast-non-reasoning",
        )
        provider, model = mgr.resolve_purpose("memory_extraction")
        assert provider == "grok"
        assert model == "grok-4-1-fast-non-reasoning"

    def test_agent_purpose_is_not_affected_by_terminal_aliases(self):
        # Guard: terminal aliases must NOT reroute existing agent purpose.
        mgr = _make_manager(
            internal_llm_provider="openai",
            agent_model_openai="gpt-5",
            chat_model_openai="gpt-5-mini",
        )
        provider, model = mgr.resolve_purpose("agent")
        assert provider == "openai"
        assert model == "gpt-5"

    def test_existing_ops_aliases_still_work(self):
        mgr = _make_manager(
            internal_llm_provider="grok",
            agent_model_grok="grok-3",
            chat_model_grok="grok-3",
        )
        # ops aliases → agent bucket
        provider, _ = mgr.resolve_purpose("ops")
        assert provider == "grok"
        # opssummary aliases → chat bucket
        provider, _ = mgr.resolve_purpose("opssummary")
        assert provider == "grok"

    def test_unknown_purpose_falls_back_to_internal_provider(self):
        mgr = _make_manager(internal_llm_provider="gemini", chat_model_gemini="models/gemini-3-flash-preview")
        provider, _ = mgr.resolve_purpose("totally_made_up_purpose")
        assert provider == "gemini"


class TestA4ExpandedTerminalPurposes:
    """A4: expanded per-purpose routing — each sub-call of Terminal AI
    (step decision, recovery, report, answer, explain) must land in the
    ``chat`` bucket by default so a ``chat_llm_model`` override affects
    all of them.
    """

    def test_step_decision_routes_to_chat(self):
        mgr = _make_manager(
            internal_llm_provider="openai",
            chat_model_openai="gpt-5-mini",
            agent_model_openai="gpt-5",
        )
        provider, model = mgr.resolve_purpose("terminal_step_decision")
        assert provider == "openai"
        assert model == "gpt-5-mini"

    def test_recovery_routes_to_chat(self):
        mgr = _make_manager(
            internal_llm_provider="openai",
            chat_model_openai="gpt-5-mini",
        )
        _provider, model = mgr.resolve_purpose("terminal_recovery")
        assert model == "gpt-5-mini"

    def test_report_routes_to_chat(self):
        mgr = _make_manager(
            internal_llm_provider="gemini",
            chat_model_gemini="models/gemini-3-flash-preview",
        )
        _provider, model = mgr.resolve_purpose("terminal_report")
        assert model == "models/gemini-3-flash-preview"

    def test_answer_routes_to_chat(self):
        mgr = _make_manager(
            internal_llm_provider="claude",
            chat_model_claude="claude-haiku-4-5",
        )
        _provider, model = mgr.resolve_purpose("terminal_answer")
        assert model == "claude-haiku-4-5"

    def test_explain_routes_to_chat(self):
        """A6 depends on this purpose — pin it here too."""
        mgr = _make_manager(
            internal_llm_provider="openai",
            chat_model_openai="gpt-5-mini",
        )
        _provider, model = mgr.resolve_purpose("terminal_explain")
        assert model == "gpt-5-mini"

    def test_chat_override_applies_to_all_terminal_subcalls(self):
        """A single ``chat_llm_provider`` / ``chat_llm_model`` knob must
        affect every terminal sub-call at once."""
        mgr = _make_manager(
            internal_llm_provider="openai",
            chat_llm_provider="claude",
            chat_llm_model="claude-haiku-4-5",
        )
        for purpose in (
            "terminal_planning",
            "terminal_step_decision",
            "terminal_recovery",
            "terminal_report",
            "terminal_answer",
            "terminal_explain",
            "memory_extraction",
        ):
            provider, model = mgr.resolve_purpose(purpose)
            assert provider == "claude", f"{purpose} provider"
            assert model == "claude-haiku-4-5", f"{purpose} model"

    def test_agent_purpose_unaffected_by_terminal_overrides(self):
        mgr = _make_manager(
            internal_llm_provider="openai",
            chat_llm_provider="claude",
            chat_llm_model="claude-haiku-4-5",
            agent_model_openai="gpt-5",
        )
        provider, model = mgr.resolve_purpose("agent")
        assert provider == "openai"
        assert model == "gpt-5"
