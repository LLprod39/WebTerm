"""Tests for B2: per-user LLM token budget."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from core_ui.models import LLMUsageLog
from core_ui.services.llm_budget import (
    BudgetExceededError,
    BudgetStatus,
    get_user_daily_budget_status,
)

# ---------------------------------------------------------------------------
# get_user_daily_budget_status
# ---------------------------------------------------------------------------


class TestBudgetService:
    def test_disabled_when_user_id_falsy(self, settings):
        settings.LLM_DAILY_TOKEN_LIMIT_PER_USER = 1000
        status = get_user_daily_budget_status(None)
        assert status.enabled is False
        assert status.exceeded is False

    def test_disabled_when_limit_zero(self, settings):
        settings.LLM_DAILY_TOKEN_LIMIT_PER_USER = 0
        status = get_user_daily_budget_status(123)
        assert status.enabled is False
        assert status.exceeded is False

    @pytest.mark.django_db
    def test_returns_full_remaining_for_new_user(self, settings, django_user_model):
        settings.LLM_DAILY_TOKEN_LIMIT_PER_USER = 1000
        user = django_user_model.objects.create_user("budget_u1", password="x")
        status = get_user_daily_budget_status(user.pk)
        assert status.enabled is True
        assert status.used_tokens == 0
        assert status.remaining_tokens == 1000
        assert status.exceeded is False

    @pytest.mark.django_db
    def test_aggregates_input_plus_output(self, settings, django_user_model):
        settings.LLM_DAILY_TOKEN_LIMIT_PER_USER = 1000
        user = django_user_model.objects.create_user("budget_u2", password="x")
        LLMUsageLog.objects.create(
            provider="openai", model_name="gpt-x", user=user,
            input_tokens=100, output_tokens=200,
        )
        LLMUsageLog.objects.create(
            provider="openai", model_name="gpt-x", user=user,
            input_tokens=50, output_tokens=50,
        )
        status = get_user_daily_budget_status(user.pk)
        assert status.used_tokens == 400  # 100+200+50+50
        assert status.remaining_tokens == 600
        assert status.exceeded is False

    @pytest.mark.django_db
    def test_exceeded_when_over_limit(self, settings, django_user_model):
        settings.LLM_DAILY_TOKEN_LIMIT_PER_USER = 1000
        user = django_user_model.objects.create_user("budget_u3", password="x")
        LLMUsageLog.objects.create(
            provider="openai", model_name="gpt-x", user=user,
            input_tokens=600, output_tokens=500,
        )
        status = get_user_daily_budget_status(user.pk)
        assert status.used_tokens == 1100
        assert status.remaining_tokens == 0
        assert status.exceeded is True

    @pytest.mark.django_db
    def test_ignores_old_usage_outside_24h_window(self, settings, django_user_model):
        settings.LLM_DAILY_TOKEN_LIMIT_PER_USER = 1000
        user = django_user_model.objects.create_user("budget_u4", password="x")
        old = LLMUsageLog.objects.create(
            provider="openai", model_name="gpt-x", user=user,
            input_tokens=500, output_tokens=500,
        )
        # Backdate 25 hours
        LLMUsageLog.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        status = get_user_daily_budget_status(user.pk)
        assert status.used_tokens == 0
        assert status.remaining_tokens == 1000
        assert status.exceeded is False

    @pytest.mark.django_db
    def test_other_users_usage_does_not_count(self, settings, django_user_model):
        settings.LLM_DAILY_TOKEN_LIMIT_PER_USER = 1000
        u1 = django_user_model.objects.create_user("budget_u5a", password="x")
        u2 = django_user_model.objects.create_user("budget_u5b", password="x")
        LLMUsageLog.objects.create(
            provider="openai", model_name="gpt-x", user=u2,
            input_tokens=900, output_tokens=900,
        )
        status = get_user_daily_budget_status(u1.pk)
        assert status.used_tokens == 0


class TestBudgetStatusDataclass:
    def test_disabled_never_exceeded(self):
        s = BudgetStatus(enabled=False, used_tokens=10**9, limit_tokens=0, remaining_tokens=0)
        assert s.exceeded is False

    def test_enabled_and_remaining_zero_means_exceeded(self):
        s = BudgetStatus(enabled=True, used_tokens=1000, limit_tokens=1000, remaining_tokens=0)
        assert s.exceeded is True

    def test_enabled_with_remaining_is_not_exceeded(self):
        s = BudgetStatus(enabled=True, used_tokens=500, limit_tokens=1000, remaining_tokens=500)
        assert s.exceeded is False


class TestBudgetExceededError:
    def test_is_runtime_error(self):
        assert issubclass(BudgetExceededError, RuntimeError)
