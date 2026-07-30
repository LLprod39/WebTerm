from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from app.monitoring_events import server_alert_opened
from servers.memory_heuristics import should_capture_command_history_memory
from servers.models import (
    AgentRun,
    AgentRunEvent,
    ServerAgent,
    ServerAlert,
    ServerCommandHistory,
    ServerHealthCheck,
    ServerShare,
    ServerWatcherDraft,
)
from servers.tasks import ingest_memory_event_task


@receiver(pre_save, sender=ServerShare)
def ensure_server_share_project_membership(sender, instance: ServerShare, **kwargs):
    """Keep legacy server sharing inside the server's project tenant."""
    if not instance.server_id or not instance.user_id:
        return
    from core_ui.models.projects import ProjectMembership

    operational = any(
        (
            instance.can_connect_terminal,
            instance.can_execute_command,
            instance.can_read_files,
            instance.can_write_files,
        )
    )
    role = ProjectMembership.ROLE_OPERATOR if operational else ProjectMembership.ROLE_VIEWER
    membership, _created = ProjectMembership.objects.get_or_create(
        project_id=instance.server.project_id,
        user_id=instance.user_id,
        defaults={"role": role},
    )
    if operational and membership.role == ProjectMembership.ROLE_VIEWER:
        membership.role = ProjectMembership.ROLE_OPERATOR
        membership.save(update_fields=["role", "updated_at"])
    from core_ui.projects import activate_first_shared_project_if_personal_empty

    activate_first_shared_project_if_personal_empty(instance.user, instance.server.project)


@receiver(m2m_changed, sender=ServerAgent.servers.through)
def enforce_agent_server_project(sender, instance, action: str, reverse: bool, pk_set, **kwargs):
    if action != "pre_add" or not pk_set:
        return
    if reverse:
        mismatched = ServerAgent.objects.filter(pk__in=pk_set).exclude(project_id=instance.project_id).exists()
    else:
        mismatched = (
            instance.servers.model.objects.filter(pk__in=pk_set).exclude(project_id=instance.project_id).exists()
        )
    if mismatched:
        raise ValidationError("Agent and servers must belong to the same project")


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
    raw_output = instance.raw_output if isinstance(instance.raw_output, dict) else {}
    if raw_output.get("lite") and instance.status == ServerHealthCheck.STATUS_HEALTHY:
        return False
    if instance.status != ServerHealthCheck.STATUS_HEALTHY:
        return True
    # OK status → only if previous was not OK (recovery signal)
    previous = (
        ServerHealthCheck.objects.filter(server_id=instance.server_id, checked_at__lt=instance.checked_at)
        .order_by("-checked_at")
        .first()
    )
    # Transition to OK — recovery signal worth capturing.
    return bool(previous and previous.status != ServerHealthCheck.STATUS_HEALTHY)


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
        if instance.severity == ServerAlert.SEVERITY_CRITICAL:
            alert_id = instance.pk

            def _duty_note():
                from core_ui.services.operator_duty import post_critical_alert_to_duty
                from servers.models import ServerAlert as SA

                alert = SA.objects.select_related("server", "server__user").filter(pk=alert_id).first()
                if alert:
                    post_critical_alert_to_duty(alert)

            transaction.on_commit(_duty_note)


def _launch_monitoring_pipelines(alert_id: int) -> None:
    alert = ServerAlert.objects.select_related("server", "server__user").filter(pk=alert_id).first()
    if not alert or alert.is_resolved:
        return
    # Fire shared app-level signal; Studio subscribes without importing servers.
    server_alert_opened.send(
        sender=ServerAlert,
        alert_id=alert.pk,
        server_id=alert.server_id,
        severity=alert.severity,
    )


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


@receiver(post_save, sender=AgentRun)
def operator_resume_on_agent_run(sender, instance: AgentRun, **kwargs):
    """When an agent run finishes, resume any parked Operator chat turns."""
    if instance.status not in {
        AgentRun.STATUS_COMPLETED,
        AgentRun.STATUS_FAILED,
        AgentRun.STATUS_STOPPED,
    }:
        return
    from core_ui.services.operator_async import schedule_async_resume_on_commit

    schedule_async_resume_on_commit(kind="agent_run", run_id=instance.pk)


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
