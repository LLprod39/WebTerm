"""Prometheus metrics owned by the servers domain."""

from asgiref.sync import async_to_sync
from django.utils import timezone

from servers.models_agents import AgentRunDispatch
from servers.models_monitoring import BackgroundWorkerState
from servers.services.ssh_pool import ssh_connection_pool


def server_prometheus_lines() -> list[str]:
    now = timezone.now()
    queued = AgentRunDispatch.objects.filter(status=AgentRunDispatch.STATUS_QUEUED)
    oldest = queued.order_by("queued_at").values_list("queued_at", flat=True).first()
    active_dispatches = AgentRunDispatch.objects.filter(
        status=AgentRunDispatch.STATUS_CLAIMED,
        lease_expires_at__gt=now,
    ).count()
    active_workers = BackgroundWorkerState.objects.filter(
        worker_kind=BackgroundWorkerState.KIND_AGENT_EXECUTION,
        status=BackgroundWorkerState.STATUS_RUNNING,
        lease_expires_at__gt=now,
    ).count()
    try:
        ssh_stats = async_to_sync(ssh_connection_pool.stats)()
    except Exception:
        ssh_stats = {"active_connections": 0, "in_use_connections": 0}
    return [
        "# HELP webterm_agent_queue_depth Agent dispatches waiting for a worker.",
        "# TYPE webterm_agent_queue_depth gauge",
        f"webterm_agent_queue_depth {queued.count()}",
        "# HELP webterm_agent_queue_oldest_age_seconds Age of the oldest waiting agent dispatch.",
        "# TYPE webterm_agent_queue_oldest_age_seconds gauge",
        f"webterm_agent_queue_oldest_age_seconds {max((now - oldest).total_seconds(), 0.0) if oldest else 0.0:.6f}",
        "# HELP webterm_agent_active_dispatches Agent dispatches with a current execution lease.",
        "# TYPE webterm_agent_active_dispatches gauge",
        f"webterm_agent_active_dispatches {active_dispatches}",
        "# HELP webterm_agent_execution_workers Agent execution worker replicas with a current heartbeat.",
        "# TYPE webterm_agent_execution_workers gauge",
        f"webterm_agent_execution_workers {active_workers}",
        "# HELP webterm_ssh_pool_active_connections Connections retained by the process-local SSH pool.",
        "# TYPE webterm_ssh_pool_active_connections gauge",
        f"webterm_ssh_pool_active_connections {int(ssh_stats.get('active_connections') or 0)}",
        "# HELP webterm_ssh_pool_in_use_connections SSH pool connections currently serving operations.",
        "# TYPE webterm_ssh_pool_in_use_connections gauge",
        f"webterm_ssh_pool_in_use_connections {int(ssh_stats.get('in_use_connections') or 0)}",
    ]
