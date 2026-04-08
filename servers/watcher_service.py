from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.db.models import Max
from django.utils import timezone

from app.agent_kernel.memory.store import DjangoServerMemoryStore


@dataclass(frozen=True)
class WatcherDraft:
    server_id: int
    server_name: str
    severity: str
    recommended_role: str
    objective: str
    reasons: list[str]
    memory_excerpt: list[str]

    def to_dict(self) -> dict:
        return {
            "server_id": self.server_id,
            "server_name": self.server_name,
            "severity": self.severity,
            "recommended_role": self.recommended_role,
            "objective": self.objective,
            "reasons": list(self.reasons),
            "memory_excerpt": list(self.memory_excerpt),
        }


class WatcherService:
    def __init__(self):
        self.memory_store = DjangoServerMemoryStore()

    def scan_queryset(self, servers_qs, *, limit: int = 25) -> dict:
        from servers.models import AgentRun, ServerAlert, ServerHealthCheck

        server_ids = list(servers_qs.values_list("id", flat=True)[:limit])
        if not server_ids:
            return {
                "generated_at": timezone.now().isoformat(),
                "summary": {"scanned_servers": 0, "critical": 0, "warning": 0, "drafts": 0},
                "scanned_server_ids": [],
                "drafts": [],
            }

        latest_health_rows = list(
            ServerHealthCheck.objects.filter(server_id__in=server_ids)
            .values("server_id")
            .annotate(last_id=Max("id"))
        )
        latest_health_ids = [row["last_id"] for row in latest_health_rows if row.get("last_id")]
        latest_health = {
            item.server_id: item
            for item in ServerHealthCheck.objects.filter(id__in=latest_health_ids).select_related("server")
        }
        alerts_by_server: dict[int, list] = {}
        for alert in ServerAlert.objects.filter(server_id__in=server_ids, is_resolved=False).select_related("server").order_by("-created_at")[:100]:
            alerts_by_server.setdefault(alert.server_id, []).append(alert)
        recent_runs_by_server: dict[int, list] = {}
        for run in AgentRun.objects.filter(server_id__in=server_ids).select_related("agent").order_by("-started_at")[:100]:
            recent_runs_by_server.setdefault(run.server_id, []).append(run)

        drafts: list[WatcherDraft] = []
        critical_count = 0
        warning_count = 0
        severity_rank = {"info": 0, "warning": 1, "critical": 2}

        for server in servers_qs.filter(id__in=server_ids):
            health = latest_health.get(server.id)
            alerts = alerts_by_server.get(server.id, [])
            recent_runs = recent_runs_by_server.get(server.id, [])
            if not alerts and not health and not recent_runs:
                continue

            reasons: list[str] = []
            severity = "info"
            role = "infra_scout"
            objective = f"Провести инвентаризацию и базовую проверку сервера {server.name}"

            def _promote(target: str) -> None:
                nonlocal severity
                if severity_rank[target] > severity_rank[severity]:
                    severity = target

            if health:
                if health.status in {ServerHealthCheck.STATUS_CRITICAL, ServerHealthCheck.STATUS_UNREACHABLE}:
                    _promote("critical")
                    reasons.append(f"Health status: {health.status}")
                    role = "incident_commander"
                    objective = f"Расследовать критическое состояние сервера {server.name} и подготовить remediation plan"
                elif health.status == ServerHealthCheck.STATUS_WARNING:
                    _promote("warning")
                    reasons.append("Health status: warning")

                if health.disk_percent and health.disk_percent >= 90:
                    _promote("critical" if health.disk_percent >= 95 else "warning")
                    reasons.append(f"Disk usage is {health.disk_percent}%")
                    role = "infra_scout"
                    objective = f"Проверить дефицит диска на сервере {server.name} и подготовить безопасные действия"

            for alert in alerts[:4]:
                reasons.append(f"[{alert.severity}] {alert.title}")
                if alert.severity == "critical":
                    _promote("critical")
                    role = "incident_commander"
                else:
                    _promote("warning")

                if alert.alert_type in {ServerAlert.TYPE_SERVICE, ServerAlert.TYPE_LOG_ERROR, ServerAlert.TYPE_UNREACHABLE}:
                    role = "incident_commander"
                    objective = f"Разобрать инцидент на сервере {server.name}: {alert.title}"
                elif alert.alert_type in {ServerAlert.TYPE_CPU, ServerAlert.TYPE_MEMORY, ServerAlert.TYPE_DISK}:
                    role = "infra_scout"
                    objective = f"Проверить ресурсную деградацию на сервере {server.name}: {alert.title}"

            for run in recent_runs[:2]:
                if run.status in {run.STATUS_FAILED, run.STATUS_STOPPED}:
                    reasons.append(f"Недавний агентный run завершился статусом {run.status}")
                    _promote("warning")
                    if severity != "critical":
                        role = "post_change_verifier"
                        objective = f"Понять, почему недавний агентный run на сервере {server.name} завершился ошибкой"

            if severity == "critical":
                critical_count += 1
            elif severity == "warning":
                warning_count += 1
            else:
                continue

            card = self.memory_store._get_server_card_sync(server.id)
            memory_excerpt = [*card.recent_incidents[:2], *card.known_risks[:2], *card.recent_changes[:2]]
            drafts.append(
                WatcherDraft(
                    server_id=server.id,
                    server_name=server.name,
                    severity=severity,
                    recommended_role=role,
                    objective=objective,
                    reasons=reasons[:6],
                    memory_excerpt=memory_excerpt[:6],
                )
            )

        drafts.sort(key=lambda draft: (-severity_rank.get(draft.severity, 0), draft.server_name.lower()))

        return {
            "generated_at": timezone.now().isoformat(),
            "summary": {
                "scanned_servers": len(server_ids),
                "critical": critical_count,
                "warning": warning_count,
                "drafts": len(drafts),
            },
            "scanned_server_ids": server_ids,
            "drafts": [draft.to_dict() for draft in drafts],
        }

    def persist_queryset(self, servers_qs, *, limit: int = 25) -> dict:
        from servers.models import ServerWatcherDraft

        payload = self.scan_queryset(servers_qs, limit=limit)
        scanned_server_ids = list(payload.get("scanned_server_ids") or [])
        now = timezone.now()
        seen_keys: set[tuple[int, str]] = set()
        created = 0
        updated = 0
        reopened = 0
        resolved = 0

        for draft in payload.get("drafts") or []:
            fingerprint = self._build_fingerprint(draft)
            seen_keys.add((int(draft["server_id"]), fingerprint))
            existing = ServerWatcherDraft.objects.filter(server_id=draft["server_id"], fingerprint=fingerprint).first()

            if existing is None:
                ServerWatcherDraft.objects.create(
                    server_id=draft["server_id"],
                    fingerprint=fingerprint,
                    severity=draft["severity"],
                    recommended_role=draft["recommended_role"],
                    objective=draft["objective"],
                    reasons=draft["reasons"],
                    memory_excerpt=draft["memory_excerpt"],
                    metadata={"source": "watcher_scan", "server_name": draft["server_name"]},
                    status=ServerWatcherDraft.STATUS_OPEN,
                    last_seen_at=now,
                )
                created += 1
                continue

            existing.severity = draft["severity"]
            existing.recommended_role = draft["recommended_role"]
            existing.objective = draft["objective"]
            existing.reasons = draft["reasons"]
            existing.memory_excerpt = draft["memory_excerpt"]
            existing.metadata = {**(existing.metadata or {}), "source": "watcher_scan", "server_name": draft["server_name"]}
            existing.last_seen_at = now
            if existing.status == ServerWatcherDraft.STATUS_RESOLVED:
                existing.status = ServerWatcherDraft.STATUS_OPEN
                existing.resolved_at = None
                reopened += 1
            existing.save(
                update_fields=[
                    "severity",
                    "recommended_role",
                    "objective",
                    "reasons",
                    "memory_excerpt",
                    "metadata",
                    "last_seen_at",
                    "status",
                    "resolved_at",
                ]
            )
            updated += 1

        stale_records = ServerWatcherDraft.objects.filter(
            server_id__in=scanned_server_ids,
            status__in=[ServerWatcherDraft.STATUS_OPEN, ServerWatcherDraft.STATUS_ACKNOWLEDGED],
        )
        for record in stale_records:
            key = (record.server_id, record.fingerprint)
            if key in seen_keys:
                continue
            record.status = ServerWatcherDraft.STATUS_RESOLVED
            record.resolved_at = now
            record.save(update_fields=["status", "resolved_at"])
            resolved += 1

        payload["persisted"] = {
            "created": created,
            "updated": updated,
            "reopened": reopened,
            "resolved": resolved,
        }
        return payload

    def list_persisted_queryset(self, servers_qs, *, statuses: list[str] | None = None, limit: int = 100) -> dict:
        from servers.models import ServerWatcherDraft

        server_ids = list(servers_qs.values_list("id", flat=True))
        qs = ServerWatcherDraft.objects.filter(server_id__in=server_ids).select_related("server", "acknowledged_by")
        if statuses:
            qs = qs.filter(status__in=statuses)

        draft_rows = list(qs.order_by("-last_seen_at")[:limit])
        summary = {
            "open": 0,
            "acknowledged": 0,
            "resolved": 0,
            "suppressed": 0,
            "total": len(draft_rows),
        }
        for item in draft_rows:
            summary[item.status] = summary.get(item.status, 0) + 1

        return {
            "summary": summary,
            "drafts": [self._serialize_record(item) for item in draft_rows],
        }

    def acknowledge_draft(self, draft_id: int, *, user, servers_qs) -> dict | None:
        from servers.models import ServerWatcherDraft

        server_ids = list(servers_qs.values_list("id", flat=True))
        draft = (
            ServerWatcherDraft.objects.filter(id=draft_id, server_id__in=server_ids)
            .select_related("server", "acknowledged_by")
            .first()
        )
        if draft is None:
            return None

        draft.status = ServerWatcherDraft.STATUS_ACKNOWLEDGED
        draft.acknowledged_at = timezone.now()
        draft.acknowledged_by = user
        draft.save(update_fields=["status", "acknowledged_at", "acknowledged_by"])
        return self._serialize_record(draft)

    @staticmethod
    def _build_fingerprint(draft: dict) -> str:
        normalized = "|".join(
            [
                str(draft.get("server_id") or ""),
                str(draft.get("severity") or ""),
                str(draft.get("recommended_role") or ""),
                str(draft.get("objective") or "").strip().lower(),
                "|".join(str(item).strip().lower() for item in (draft.get("reasons") or [])[:4]),
            ]
        )
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _serialize_record(record) -> dict:
        return {
            "id": record.id,
            "server_id": record.server_id,
            "server_name": record.server.name,
            "severity": record.severity,
            "recommended_role": record.recommended_role,
            "objective": record.objective,
            "reasons": list(record.reasons or []),
            "memory_excerpt": list(record.memory_excerpt or []),
            "status": record.status,
            "acknowledged_at": record.acknowledged_at.isoformat() if record.acknowledged_at else None,
            "acknowledged_by": record.acknowledged_by.username if record.acknowledged_by_id else "",
            "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
            "first_seen_at": record.first_seen_at.isoformat() if record.first_seen_at else None,
            "last_seen_at": record.last_seen_at.isoformat() if record.last_seen_at else None,
            "metadata": record.metadata or {},
        }
