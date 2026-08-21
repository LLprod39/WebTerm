"""Default-off lifecycle bridge into normalized DevOps memory events."""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from servers.models import (
    AgentRun,
    PlaybookRun,
    Server,
    ServerAlert,
    ServerHealthCheck,
    ServerWatcherDraft,
)
from servers.services.devops_memory_events import (
    devops_memory_events_enabled,
    enqueue_devops_memory_event,
    pipeline_snapshot_server_ids,
)
from studio.models import PipelineRun

logger = logging.getLogger(__name__)

PLAYBOOK_TERMINAL_STATUSES = frozenset(
    {
        PlaybookRun.STATUS_COMPLETED,
        PlaybookRun.STATUS_FAILED,
        PlaybookRun.STATUS_PARTIAL,
        PlaybookRun.STATUS_CANCELLED,
    }
)
AGENT_TERMINAL_STATUSES = frozenset(
    {
        AgentRun.STATUS_COMPLETED,
        AgentRun.STATUS_FAILED,
        AgentRun.STATUS_STOPPED,
    }
)
PIPELINE_TERMINAL_STATUSES = frozenset(
    {
        PipelineRun.STATUS_COMPLETED,
        PipelineRun.STATUS_FAILED,
        PipelineRun.STATUS_STOPPED,
    }
)


def _safe_enqueue(*, model, source_id: int, server_id: int, event_family: str, transition: str) -> None:
    try:
        source = model.objects.filter(pk=source_id).first()
        server = Server.objects.filter(pk=server_id).first()
        if source is None or server is None:
            return
        enqueue_devops_memory_event(
            server=server,
            source=source,
            event_family=event_family,
            transition=transition,
            redacted_excerpt="",
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "DevOps memory lifecycle enqueue failed for %s:%s on server:%s",
            model._meta.label_lower,
            source_id,
            server_id,
        )


def _schedule(*, model, source_id: int, server_id: int, event_family: str, transition: str) -> None:
    transaction.on_commit(
        lambda: _safe_enqueue(
            model=model,
            source_id=source_id,
            server_id=server_id,
            event_family=event_family,
            transition=transition,
        )
    )


def _validated_project_server_ids(*, project_id: int | None, candidate_ids: set[int]) -> list[int]:
    if not project_id or not candidate_ids:
        return []
    return list(
        Server.objects.filter(project_id=project_id, id__in=sorted(candidate_ids)).values_list("id", flat=True)
    )


def _bounded_integer_ids(values: Any) -> set[int]:
    if not isinstance(values, list):
        return set()
    result: set[int] = set()
    for value in values[:100]:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue
    return result


@receiver(pre_save, sender=ServerAlert, dispatch_uid="devops_memory_alert_previous_state")
def remember_alert_state(sender, instance: ServerAlert, **kwargs) -> None:
    if not devops_memory_events_enabled() or not instance.pk:
        return
    instance._devops_previous_is_resolved = sender.objects.filter(pk=instance.pk).values_list(
        "is_resolved", flat=True
    ).first()


@receiver(post_save, sender=ServerAlert, dispatch_uid="devops_memory_alert_lifecycle")
def enqueue_alert_lifecycle(sender, instance: ServerAlert, created: bool, **kwargs) -> None:
    if not devops_memory_events_enabled():
        return
    transition = "opened" if created and not instance.is_resolved else ""
    if not created and instance.is_resolved and getattr(instance, "_devops_previous_is_resolved", None) is False:
        transition = "resolved"
    if transition:
        _schedule(
            model=sender,
            source_id=instance.id,
            server_id=instance.server_id,
            event_family="alert",
            transition=transition,
        )


@receiver(post_save, sender=ServerHealthCheck, dispatch_uid="devops_memory_health_lifecycle")
def enqueue_health_lifecycle(sender, instance: ServerHealthCheck, created: bool, **kwargs) -> None:
    if not devops_memory_events_enabled() or not created:
        return
    _schedule(
        model=sender,
        source_id=instance.id,
        server_id=instance.server_id,
        event_family="monitoring",
        transition="observed",
    )


@receiver(pre_save, sender=ServerWatcherDraft, dispatch_uid="devops_memory_watcher_previous_state")
def remember_watcher_state(sender, instance: ServerWatcherDraft, **kwargs) -> None:
    if not devops_memory_events_enabled() or not instance.pk:
        return
    instance._devops_previous_status = sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()


@receiver(post_save, sender=ServerWatcherDraft, dispatch_uid="devops_memory_watcher_lifecycle")
def enqueue_watcher_lifecycle(sender, instance: ServerWatcherDraft, created: bool, **kwargs) -> None:
    if not devops_memory_events_enabled():
        return
    previous = getattr(instance, "_devops_previous_status", None)
    if not created and previous == instance.status:
        return
    transition = "created" if created else f"status_{instance.status}"
    _schedule(
        model=sender,
        source_id=instance.id,
        server_id=instance.server_id,
        event_family="incident",
        transition=transition,
    )


@receiver(post_save, sender=PlaybookRun, dispatch_uid="devops_memory_playbook_run_lifecycle")
def enqueue_playbook_run_lifecycle(sender, instance: PlaybookRun, **kwargs) -> None:
    if not devops_memory_events_enabled() or instance.status not in PLAYBOOK_TERMINAL_STATUSES:
        return
    server_ids = _validated_project_server_ids(
        project_id=instance.project_id,
        candidate_ids=_bounded_integer_ids(instance.target_server_ids),
    )
    for server_id in server_ids:
        _schedule(
            model=sender,
            source_id=instance.id,
            server_id=server_id,
            event_family="playbook",
            transition=instance.status,
        )


@receiver(post_save, sender=AgentRun, dispatch_uid="devops_memory_agent_run_lifecycle")
def enqueue_agent_run_lifecycle(sender, instance: AgentRun, **kwargs) -> None:
    if (
        not devops_memory_events_enabled()
        or instance.status not in AGENT_TERMINAL_STATUSES
        or not instance.server_id
    ):
        return
    server_ids = _validated_project_server_ids(
        project_id=instance.project_id,
        candidate_ids={instance.server_id},
    )
    if not server_ids:
        return
    _schedule(
        model=sender,
        source_id=instance.id,
        server_id=server_ids[0],
        event_family="agent_run",
        transition=instance.status,
    )


@receiver(post_save, sender=PipelineRun, dispatch_uid="devops_memory_pipeline_run_lifecycle")
def enqueue_pipeline_run_lifecycle(sender, instance: PipelineRun, **kwargs) -> None:
    if not devops_memory_events_enabled() or instance.status not in PIPELINE_TERMINAL_STATUSES:
        return
    server_ids = _validated_project_server_ids(
        project_id=instance.project_id,
        candidate_ids=pipeline_snapshot_server_ids(instance.nodes_snapshot),
    )
    for server_id in server_ids:
        _schedule(
            model=sender,
            source_id=instance.id,
            server_id=server_id,
            event_family="pipeline",
            transition=instance.status,
        )
