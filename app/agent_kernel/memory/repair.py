from __future__ import annotations

from datetime import timedelta

from django.utils import timezone


def compute_freshness_score(updated_at, verified_at=None) -> float:
    reference = verified_at or updated_at
    if not reference:
        return 0.2

    age = timezone.now() - reference
    if age <= timedelta(days=1):
        return 1.0
    if age <= timedelta(days=7):
        return 0.85
    if age <= timedelta(days=30):
        return 0.65
    if age <= timedelta(days=90):
        return 0.45
    return 0.25


def decay_confidence(current_confidence: float, freshness_score: float) -> float:
    normalized_confidence = max(0.05, min(float(current_confidence or 0.0), 1.0))
    normalized_freshness = max(0.05, min(float(freshness_score or 0.0), 1.0))
    return round(min(normalized_confidence, max(0.25, normalized_freshness)), 2)


def needs_revalidation(updated_at, verified_at=None, *, max_age_days: int = 30) -> bool:
    reference = verified_at or updated_at
    if not reference:
        return True
    return (timezone.now() - reference) >= timedelta(days=max_age_days)


def detect_fact_conflicts(existing_records: list[dict], new_facts: list[dict]) -> list[dict]:
    conflicts: list[dict] = []
    for fact in new_facts:
        title = (fact.get("title") or "").strip().lower()
        category = (fact.get("category") or "").strip().lower()
        content = (fact.get("content") or "").strip()
        if not title or not content:
            continue
        for current in existing_records:
            current_title = (current.get("title") or "").strip().lower()
            current_category = (current.get("category") or "").strip().lower()
            current_content = (current.get("content") or "").strip()
            if title == current_title and category == current_category and current_content and current_content != content:
                conflicts.append(
                    {
                        "title": fact.get("title"),
                        "category": fact.get("category"),
                        "old_content": current_content,
                        "new_content": content,
                    }
                )
    return conflicts
