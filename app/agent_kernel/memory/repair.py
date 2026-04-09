from __future__ import annotations

from datetime import timedelta

from django.utils import timezone


def compute_freshness_score(updated_at, verified_at=None, *, half_life_hours: float = 168.0) -> float:
    """Exponential decay freshness: score = 2^(-age_hours / half_life_hours).

    Default half_life_hours=168 (7 days) means:
    - 1 day old  → ~0.91
    - 7 days old → 0.50
    - 30 days old → ~0.05
    - 90 days old → ~0.0002 (clamped to 0.05)
    """
    reference = verified_at or updated_at
    if not reference:
        return 0.05
    age = timezone.now() - reference
    age_hours = max(0.0, age.total_seconds() / 3600.0)
    return max(0.05, 2.0 ** (-age_hours / half_life_hours))


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


def resolve_winning_fact(
    *,
    existing_updated_at=None,
    existing_confidence: float = 0.7,
    incoming_updated_at=None,
    incoming_confidence: float = 0.7,
) -> str:
    """
    Определяет победителя при конфликте фактов.

    Возвращает:
      - ``"incoming"``    — новый факт достоверней, заменить существующий
      - ``"existing"``    — существующий факт достоверней, оставить
      - ``"revalidate"``  — разрыв слишком мал, нужна ручная/LLM-проверка

    Стратегия: score = confidence * freshness; если gap < 0.12 → revalidate.
    """
    existing_freshness = compute_freshness_score(existing_updated_at)
    incoming_freshness = compute_freshness_score(incoming_updated_at)

    existing_score = float(existing_confidence or 0.7) * existing_freshness
    incoming_score = float(incoming_confidence or 0.7) * incoming_freshness

    gap = abs(incoming_score - existing_score)
    if gap < 0.12:
        return "revalidate"
    return "incoming" if incoming_score > existing_score else "existing"


def auto_resolve_stale_revalidations(server_id: int, *, max_age_days: int = 60) -> int:
    """
    Автоматически закрывает устаревшие open-реvalidations в конце dream cycle.

    Правила:
    - Запись старше ``max_age_days`` → STATUS_RESOLVED (информация наверняка
      уже перекрыта новыми данными).
    - Если ``source_snapshot`` уже неактивен и по тому же memory_key есть
      новый активный снапшот → STATUS_SUPERSEDED.

    Возвращает число закрытых записей.
    """
    from servers.models import ServerMemoryRevalidation, ServerMemorySnapshot

    now = timezone.now()
    cutoff = now - timedelta(days=max_age_days)
    resolved = 0

    open_items = list(
        ServerMemoryRevalidation.objects.filter(
            server_id=server_id,
            status=ServerMemoryRevalidation.STATUS_OPEN,
        ).select_related("source_snapshot")
    )

    for item in open_items:
        # Правило 1: очень старая запись
        if item.created_at < cutoff:
            item.status = ServerMemoryRevalidation.STATUS_RESOLVED
            item.resolved_at = now
            item.save(update_fields=["status", "resolved_at", "updated_at"])
            resolved += 1
            continue

        # Правило 2: source_snapshot заменён новым
        source = getattr(item, "source_snapshot", None)
        if source is not None and not source.is_active:
            newer_exists = ServerMemorySnapshot.objects.filter(
                server_id=server_id,
                memory_key=item.memory_key,
                is_active=True,
            ).exists()
            if newer_exists:
                item.status = ServerMemoryRevalidation.STATUS_SUPERSEDED
                item.resolved_at = now
                item.save(update_fields=["status", "resolved_at", "updated_at"])
                resolved += 1

    return resolved
