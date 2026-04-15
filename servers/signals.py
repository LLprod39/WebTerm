from __future__ import annotations

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from app.agent_kernel.memory.store import DjangoServerMemoryStore
from servers.memory_heuristics import should_capture_command_history_memory
from servers.models import AgentRunEvent, ServerAlert, ServerCommandHistory, ServerHealthCheck, ServerWatcherDraft
from servers.tasks import ingest_memory_event_task


def _deferred_ingest_command_history(pk: int):
    """Run after the transaction commits so the row is guaranteed to exist."""
    instance = ServerCommandHistory.objects.filter(pk=pk).first()
    if not instance:
        return
    output = str(instance.output or "")
    output_tail = output[-1200:] if output else ""
    if not should_capture_command_history_memory(
        command=instance.command,
        output=output_tail,
        exit_code=instance.exit_code,
        actor_kind=instance.actor_kind or "human",
        source_kind=instance.source_kind or "terminal",
    ):
        return
    ingest_memory_event_task.delay(
        server_id=instance.server_id,
        source_kind=instance.source_kind or "terminal",
        actor_kind=instance.actor_kind or "human",
        source_ref=instance.session_id or f"command-history:{instance.pk}",
        session_id=instance.session_id or "",
        event_type="command_executed",
        raw_text=f"$ {instance.command}\n{output_tail}".strip(),
        structured_payload={
            "command": instance.command,
            "cwd": instance.cwd,
            "exit_code": instance.exit_code,
            "history_id": instance.pk,
        },
        importance_hint=0.72 if instance.exit_code not in (0, None) else 0.58,
        actor_user_id=instance.user_id,
    )


@receiver(post_save, sender=ServerCommandHistory)
def ingest_command_history(sender, instance: ServerCommandHistory, created: bool, **kwargs):
    if not created:
        return
    transaction.on_commit(lambda: _deferred_ingest_command_history(instance.pk))


def _should_capture_health_check(instance: ServerHealthCheck) -> bool:
    """Only capture health checks that represent a state transition or non-OK status."""
    if instance.status != ServerHealthCheck.STATUS_HEALTHY:
        return True
    # OK status → only if previous was not OK (recovery signal)
    previous = (
        ServerHealthCheck.objects
        .filter(server_id=instance.server_id, checked_at__lt=instance.checked_at)
        .order_by("-checked_at")
        .first()
    )
    if previous and previous.status != ServerHealthCheck.STATUS_HEALTHY:
        return True  # Transition to OK — recovery signal worth capturing
    return False


def _deferred_ingest_health_check(pk: int):
    """Run after the transaction commits."""
    instance = ServerHealthCheck.objects.filter(pk=pk).first()
    if not instance:
        return
    if not _should_capture_health_check(instance):
        return
    raw_output = instance.raw_output or {}
    ingest_memory_event_task.delay(
        server_id=instance.server_id,
        source_kind="monitoring",
        actor_kind="system",
        source_ref=f"health:{instance.pk}",
        session_id=None,
        event_type=f"health_{instance.status}",
        raw_text=(
            f"Health check status={instance.status}, cpu={instance.cpu_percent}, mem={instance.memory_percent}, "
            f"disk={instance.disk_percent}, load={instance.load_1m}"
        ),
        structured_payload={
            "health_id": instance.pk,
            "status": instance.status,
            "cpu_percent": instance.cpu_percent,
            "memory_percent": instance.memory_percent,
            "disk_percent": instance.disk_percent,
            "load_1m": instance.load_1m,
            "response_time_ms": instance.response_time_ms,
            "raw_output": raw_output,
        },
        importance_hint=0.9 if instance.status != ServerHealthCheck.STATUS_HEALTHY else 0.45,
    )


@receiver(post_save, sender=ServerHealthCheck)
def ingest_health_check(sender, instance: ServerHealthCheck, created: bool, **kwargs):
    if not created:
        return
    transaction.on_commit(lambda: _deferred_ingest_health_check(instance.pk))


@receiver(post_save, sender=ServerAlert)
def ingest_alert(sender, instance: ServerAlert, created: bool, **kwargs):
    event_type = "alert_resolved" if instance.is_resolved else "alert_opened"
    importance = 0.95 if instance.severity == ServerAlert.SEVERITY_CRITICAL else 0.82
    ingest_memory_event_task.delay(
        server_id=instance.server_id,
        source_kind="monitoring",
        actor_kind="watcher" if created else "system",
        source_ref=f"alert:{instance.pk}",
        session_id=None,
        event_type=event_type,
        raw_text=f"{instance.title}\n{instance.message}".strip(),
        structured_payload={
            "alert_id": instance.pk,
            "alert_type": instance.alert_type,
            "severity": instance.severity,
            "is_resolved": instance.is_resolved,
            "metadata": instance.metadata,
        },
        importance_hint=importance,
        actor_user_id=instance.resolved_by_id,
        force_compact=not instance.is_resolved,
    )
    if created and not instance.is_resolved:
        transaction.on_commit(lambda: _launch_monitoring_pipelines(instance.pk))


def _launch_monitoring_pipelines(alert_id: int) -> None:
    alert = ServerAlert.objects.select_related("server", "server__user").filter(pk=alert_id).first()
    if not alert or alert.is_resolved:
        return
    try:
        from studio.trigger_dispatch import launch_monitoring_triggers_for_alert

        launch_monitoring_triggers_for_alert(alert)
    except Exception:
        # Monitoring-trigger dispatch must never block core alert ingestion.
        return


@receiver(post_save, sender=AgentRunEvent)
def ingest_agent_run_event(sender, instance: AgentRunEvent, created: bool, **kwargs):
    if not created or not instance.run_id or not instance.run.server_id:
        return
    ingest_memory_event_task.delay(
        server_id=instance.run.server_id,
        source_kind="agent_event",
        actor_kind="agent",
        source_ref=f"agent-run:{instance.run_id}",
        session_id=f"agent-run:{instance.run_id}",
        event_type=instance.event_type or "agent_event",
        raw_text=instance.message or "",
        structured_payload={
            "run_id": instance.run_id,
            "task_id": instance.task_id,
            "payload": instance.payload,
        },
        importance_hint=0.72,
        actor_user_id=instance.run.user_id,
    )


@receiver(post_save, sender=ServerWatcherDraft)
def ingest_watcher_draft(sender, instance: ServerWatcherDraft, created: bool, **kwargs):
    ingest_memory_event_task.delay(
        server_id=instance.server_id,
        source_kind="watcher",
        actor_kind="watcher",
        source_ref=f"watcher-draft:{instance.pk}",
        session_id=None,
        event_type="watcher_draft_opened" if created else f"watcher_draft_{instance.status}",
        raw_text=instance.objective,
        structured_payload={
            "draft_id": instance.pk,
            "severity": instance.severity,
            "status": instance.status,
            "recommended_role": instance.recommended_role,
            "reasons": instance.reasons,
            "memory_excerpt": instance.memory_excerpt,
            "metadata": instance.metadata,
        },
        importance_hint=0.88 if instance.status == ServerWatcherDraft.STATUS_OPEN else 0.65,
        actor_user_id=instance.acknowledged_by_id,
        force_compact=created,
    )
