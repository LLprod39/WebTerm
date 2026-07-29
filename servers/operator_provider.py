"""servers-side implementation of the Operator provider port.

Implements :class:`app.agent_kernel.operator_provider_registry.OperatorServersProvider`
so the ``core_ui`` Operator layer can reach ``servers`` behaviour without a
direct import (import-linter contract 5). Registered in
``servers.apps.ServersConfig.ready()``.

Data-gathering that genuinely belongs to ``servers`` (duty facts, operator
lesson ingestion) lives here; thin accessors just proxy an existing helper.
Imports of ``servers`` submodules are deferred into the methods to preserve the
original call sites' lazy-import ordering behaviour.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone


class ServersOperatorProvider:
    """Concrete Operator port backed by the Django ``servers`` app."""

    def accessible_servers_queryset(self, user: Any) -> Any:
        from servers.views.server_helpers import _accessible_servers_queryset

        return _accessible_servers_queryset(user)

    def owned_servers_queryset(self, user: Any) -> Any:
        from servers.models import Server

        return Server.objects.filter(user=user, is_active=True, server_type="ssh")

    def server_names_for_ids(self, ids: list[int]) -> list[str]:
        from servers.models import Server

        if not ids:
            return []
        return list(Server.objects.filter(pk__in=ids).values_list("name", flat=True)[:40])

    def get_agent_run(self, run_id: int) -> Any | None:
        from servers.models import AgentRun

        return AgentRun.objects.filter(pk=run_id).first()

    def get_playbook_run(self, run_id: int) -> Any | None:
        from servers.models import PlaybookRun

        return PlaybookRun.objects.filter(pk=run_id).first()

    def build_agent_run_report_response(self, run: Any) -> dict[str, Any]:
        from servers.agent_run_report import build_agent_run_report_response

        return build_agent_run_report_response(run)

    def memory_overview(self, server_id: int) -> dict[str, Any]:
        from servers.services.memory_service import get_memory_overview

        return get_memory_overview(int(server_id))

    def ingest_operator_lesson(
        self,
        *,
        server_id: int,
        title: str,
        body: str,
        actor_user_id: int | None,
        chat_id: int | None,
        importance: float,
        run_dream: bool,
    ) -> dict[str, Any]:
        import contextlib

        from servers.adapters.memory_store import DjangoServerMemoryStore

        store = DjangoServerMemoryStore()
        raw_text = f"{title.strip()}\n\n{body.strip()}".strip()
        event_id = store._ingest_event_sync(
            int(server_id),
            source_kind="operator_chat",
            actor_kind="operator",
            source_ref=f"operator-chat:{chat_id or 'adhoc'}:{title[:40]}",
            session_id=f"operator-chat:{chat_id}" if chat_id else "",
            event_type="operator_lesson",
            raw_text=raw_text[:8000],
            structured_payload={
                "title": title[:200],
                "lesson": body[:4000],
                "chat_id": chat_id,
                "source": "operator_chat",
            },
            importance_hint=max(0.5, min(float(importance or 0.85), 1.0)),
            actor_user_id=actor_user_id,
            force_compact=True,
        )
        dream_result = None
        if run_dream:
            with contextlib.suppress(Exception):
                dream_result = store._run_dream_cycle_sync(int(server_id), job_kind="nearline", force=True)
        return {
            "server_id": int(server_id),
            "event_id": event_id,
            "dream": dream_result,
        }

    def collect_duty_facts(self, user: Any, *, include_agent_runs: bool, since_hours: int = 16) -> dict[str, Any]:
        from servers.models import AgentRun, ServerAlert, ServerHealthCheck, ServerPrediction

        now = timezone.now()
        since = now - timedelta(hours=since_hours)
        servers = list(self.accessible_servers_queryset(user).order_by("name")[:200])
        ids = [s.id for s in servers]

        status_counts = {"healthy": 0, "warning": 0, "critical": 0, "unreachable": 0, "unknown": 0}
        latest_health: dict[int, Any] = {}
        if ids:
            for h in ServerHealthCheck.objects.filter(server_id__in=ids).order_by("server_id", "-checked_at"):
                if h.server_id not in latest_health:
                    latest_health[h.server_id] = h
        worst = []
        for s in servers:
            health = latest_health.get(s.id)
            status = getattr(health, "status", None) or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1
            if status in {"critical", "warning", "unreachable"}:
                worst.append({"name": s.name, "status": status})
        worst = worst[:10]

        alerts = []
        if ids:
            for a in (
                ServerAlert.objects.filter(server_id__in=ids, created_at__gte=since)
                .select_related("server")
                .order_by("-created_at")[:20]
            ):
                if a.is_resolved:
                    continue
                alerts.append(
                    {
                        "id": a.id,
                        "server": a.server.name if a.server_id else "",
                        "severity": a.severity,
                        "title": a.title,
                    }
                )

        predictions = []
        if ids:
            for p in (
                ServerPrediction.objects.filter(
                    server_id__in=ids,
                    status=ServerPrediction.STATUS_ACTIVE,
                )
                .select_related("server")
                .order_by("eta_days", "id")[:15]
            ):
                predictions.append(
                    {
                        "server": p.server.name if p.server_id else "",
                        "kind": p.kind,
                        "severity": p.severity,
                        "eta_days": p.eta_days,
                        "target": p.target,
                    }
                )

        agent_runs = []
        if include_agent_runs:
            for run in (
                AgentRun.objects.filter(Q(user=user) | Q(agent__user=user), started_at__gte=since)
                .select_related("agent", "server")
                .order_by("-started_at")[:15]
            ):
                agent_runs.append(
                    {
                        "id": run.id,
                        "agent": run.agent.name if run.agent_id else "",
                        "status": run.status,
                        "server": run.server.name if run.server_id else "",
                    }
                )

        return {
            "generated_at": now.isoformat(),
            "server_count": len(servers),
            "status_counts": status_counts,
            "worst": worst,
            "open_alerts": alerts,
            "predictions": predictions,
            "agent_runs": agent_runs,
        }

    def prefer_resolve_server_for_message(
        self, arguments: dict[str, Any], *, user_message: str
    ) -> dict[str, Any] | None:
        from servers.operator_tools import prefer_resolve_server_for_message

        return prefer_resolve_server_for_message(arguments, user_message=user_message)

    def prepare_list_servers_arguments(self, arguments: dict[str, Any], *, user_message: str) -> dict[str, Any]:
        from servers.operator_tools import prepare_list_servers_arguments

        return prepare_list_servers_arguments(arguments, user_message=user_message)
