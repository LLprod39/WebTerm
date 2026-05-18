from jules_tg_orchestrator.coordinator import Coordinator, DelegationDraft, MessageIntent


def test_coordinator_requires_source_when_default_missing() -> None:
    coordinator = Coordinator(default_source="", default_branch="main")
    decision = coordinator.evaluate(DelegationDraft(prompt="Add tests for memory policy updates", branch="main"))
    assert not decision.ready
    assert "source" in decision.question.lower()


def test_coordinator_accepts_specific_task_with_defaults() -> None:
    coordinator = Coordinator(default_source="sources/github-acme-app", default_branch="main")
    draft = coordinator.build_draft("Fix Settings AI Memory policy save error and add pytest coverage")
    decision = coordinator.evaluate(draft)
    assert decision.ready
    assert decision.draft is not None
    assert decision.draft.source == "sources/github-acme-app"


def test_parse_key_values() -> None:
    values = Coordinator.parse_key_values("source=sources/github-acme-app\nbranch=develop\ntask=Fix flaky tests")
    assert values == {
        "source": "sources/github-acme-app",
        "branch": "develop",
        "task": "Fix flaky tests",
    }


def test_classifies_greeting_without_delegation() -> None:
    coordinator = Coordinator(default_source="", default_branch="main")
    assert coordinator.classify_message("Привет") == MessageIntent.GREETING


def test_classifies_project_task() -> None:
    coordinator = Coordinator(default_source="", default_branch="main")
    assert coordinator.classify_message("исправь ошибку сохранения настроек памяти") == MessageIntent.TASK
