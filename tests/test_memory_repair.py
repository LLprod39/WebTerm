"""Tests for app.agent_kernel.memory.repair — freshness, decay, conflict detection."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from app.agent_kernel.memory.repair import (
    compute_freshness_score,
    decay_confidence,
    detect_fact_conflicts,
    needs_revalidation,
    resolve_winning_fact,
)


class TestFreshnessScore:
    """Tests for exponential freshness decay."""

    def test_fresh_record_near_one(self):
        """A record just created should have freshness ≈ 1.0."""
        score = compute_freshness_score(timezone.now())
        assert score >= 0.99

    def test_one_day_old(self):
        """A 1-day-old record should still be very fresh."""
        score = compute_freshness_score(timezone.now() - timedelta(days=1))
        assert 0.85 <= score <= 0.95

    def test_seven_days_half_life(self):
        """At the default half-life (7 days), score should be ≈ 0.5."""
        score = compute_freshness_score(timezone.now() - timedelta(days=7))
        assert 0.45 <= score <= 0.55

    def test_thirty_days_very_low(self):
        """A 30-day-old record should be near the floor."""
        score = compute_freshness_score(timezone.now() - timedelta(days=30))
        assert score <= 0.10

    def test_ninety_days_at_floor(self):
        """A 90-day-old record should be at the floor (0.05)."""
        score = compute_freshness_score(timezone.now() - timedelta(days=90))
        assert score == 0.05

    def test_none_reference_returns_floor(self):
        """None dates should return the floor value."""
        score = compute_freshness_score(None, None)
        assert score == 0.05

    def test_verified_at_overrides_updated_at(self):
        """verified_at should be used when provided."""
        old_update = timezone.now() - timedelta(days=60)
        recent_verify = timezone.now() - timedelta(hours=2)
        score = compute_freshness_score(old_update, recent_verify)
        assert score >= 0.95

    def test_custom_half_life(self):
        """Custom half-life should shift the decay curve."""
        # 24-hour half-life: score at 24h should be ~0.5
        score = compute_freshness_score(
            timezone.now() - timedelta(hours=24),
            half_life_hours=24.0,
        )
        assert 0.45 <= score <= 0.55

    def test_monotonic_decay(self):
        """Freshness should strictly decrease with age."""
        now = timezone.now()
        scores = [
            compute_freshness_score(now - timedelta(hours=h))
            for h in [0, 6, 12, 24, 48, 168, 720]
        ]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Not monotonic at index {i}: {scores}"


class TestDecayConfidence:
    """Tests for confidence decay based on freshness."""

    def test_high_freshness_preserves_confidence(self):
        result = decay_confidence(0.9, 1.0)
        assert result >= 0.85

    def test_low_freshness_caps_confidence(self):
        result = decay_confidence(0.9, 0.3)
        assert result <= 0.35

    def test_floor_confidence_never_below_threshold(self):
        result = decay_confidence(0.1, 0.05)
        assert result >= 0.05

    def test_zero_inputs_clamped(self):
        result = decay_confidence(0.0, 0.0)
        assert result >= 0.05


class TestNeedsRevalidation:
    """Tests for the revalidation trigger."""

    def test_recent_not_revalidated(self):
        assert needs_revalidation(timezone.now(), max_age_days=30) is False

    def test_old_needs_revalidation(self):
        old = timezone.now() - timedelta(days=35)
        assert needs_revalidation(old, max_age_days=30) is True

    def test_verified_recently_not_revalidated(self):
        old_update = timezone.now() - timedelta(days=60)
        recent_verify = timezone.now() - timedelta(days=5)
        assert needs_revalidation(old_update, recent_verify, max_age_days=30) is False

    def test_none_needs_revalidation(self):
        assert needs_revalidation(None) is True


class TestDetectFactConflicts:
    """Tests for fact conflict detection."""

    def test_no_conflicts_on_new_facts(self):
        existing = [{"title": "OS", "category": "profile", "content": "Ubuntu 22.04"}]
        new_facts = [{"title": "Firewall", "category": "access", "content": "ufw enabled"}]
        conflicts = detect_fact_conflicts(existing, new_facts)
        assert conflicts == []

    def test_conflict_detected_same_title_different_content(self):
        existing = [{"title": "OS", "category": "profile", "content": "Ubuntu 22.04"}]
        new_facts = [{"title": "OS", "category": "profile", "content": "Ubuntu 24.04"}]
        conflicts = detect_fact_conflicts(existing, new_facts)
        assert len(conflicts) == 1
        assert conflicts[0]["old_content"] == "Ubuntu 22.04"
        assert conflicts[0]["new_content"] == "Ubuntu 24.04"

    def test_no_conflict_same_content(self):
        existing = [{"title": "OS", "category": "profile", "content": "Ubuntu 22.04"}]
        new_facts = [{"title": "OS", "category": "profile", "content": "Ubuntu 22.04"}]
        conflicts = detect_fact_conflicts(existing, new_facts)
        assert conflicts == []

    def test_empty_inputs(self):
        assert detect_fact_conflicts([], []) == []
        assert detect_fact_conflicts([], [{"title": "A", "category": "B", "content": "C"}]) == []


class TestResolveWinningFact:
    """Tests for the fact conflict resolver."""

    def test_newer_higher_confidence_wins(self):
        result = resolve_winning_fact(
            existing_updated_at=timezone.now() - timedelta(days=30),
            existing_confidence=0.5,
            incoming_updated_at=timezone.now(),
            incoming_confidence=0.9,
        )
        assert result == "incoming"

    def test_older_higher_confidence_wins(self):
        result = resolve_winning_fact(
            existing_updated_at=timezone.now(),
            existing_confidence=0.9,
            incoming_updated_at=timezone.now() - timedelta(days=30),
            incoming_confidence=0.3,
        )
        assert result == "existing"

    def test_close_scores_revalidate(self):
        now = timezone.now()
        result = resolve_winning_fact(
            existing_updated_at=now,
            existing_confidence=0.7,
            incoming_updated_at=now,
            incoming_confidence=0.72,
        )
        assert result == "revalidate"
