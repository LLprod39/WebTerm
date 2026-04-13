from __future__ import annotations

from .models import CURRENT_PIPELINE_GRAPH_VERSION, Pipeline

WEBHOOK_SMOKE_PIPELINE_NAME = "Webhook Smoke Test"
WEBHOOK_SMOKE_DESCRIPTION = (
    "Minimal Studio V2 webhook pipeline for end-to-end verification. "
    "It receives a JSON payload, maps key fields into run context, classifies severity, "
    "and writes a final report so you can confirm webhook trigger, branching, and reporting."
)

WEBHOOK_SMOKE_CRITICAL_PAYLOAD = {
    "event": "disk_alert",
    "severity": "critical",
    "source": "monitoring",
    "message": "Disk usage above 95% on prod-db-01",
    "ticket_id": "SMOKE-CRIT-1",
}

WEBHOOK_SMOKE_NORMAL_PAYLOAD = {
    "event": "deploy_notice",
    "severity": "info",
    "source": "release-bot",
    "message": "Release 2026.04.10 completed successfully",
    "ticket_id": "SMOKE-INFO-1",
}


def build_webhook_smoke_nodes() -> list[dict]:
    return [
        {
            "id": "webhook_start",
            "type": "trigger/webhook",
            "position": {"x": 320, "y": 60},
            "data": {
                "label": "Webhook Trigger",
                "is_active": True,
                "webhook_payload_map": {
                    "event_name": "event",
                    "severity": "severity",
                    "source": "source",
                    "message": "message",
                    "ticket_id": "ticket_id",
                },
            },
        },
        {
            "id": "payload_report",
            "type": "output/report",
            "position": {"x": 320, "y": 220},
            "data": {
                "label": "Payload Snapshot",
                "template": (
                    "# Webhook Payload Snapshot\n\n"
                    "- event: {event_name}\n"
                    "- severity: {severity}\n"
                    "- source: {source}\n"
                    "- ticket_id: {ticket_id}\n\n"
                    "SEVERITY: {severity}\n\n"
                    "## Message\n"
                    "{message}\n"
                ),
            },
        },
        {
            "id": "severity_check",
            "type": "logic/condition",
            "position": {"x": 320, "y": 390},
            "data": {
                "label": "Critical Severity?",
                "source_node_id": "payload_report",
                "check_type": "contains",
                "check_value": "SEVERITY: critical",
            },
        },
        {
            "id": "critical_report",
            "type": "output/report",
            "position": {"x": 120, "y": 560},
            "data": {
                "label": "Critical Branch Report",
                "template": (
                    "# Webhook Smoke Result\n\n"
                    "Branch selected: `critical`\n\n"
                    "- event: {event_name}\n"
                    "- severity: {severity}\n"
                    "- source: {source}\n"
                    "- ticket_id: {ticket_id}\n\n"
                    "Message:\n{message}\n"
                ),
            },
        },
        {
            "id": "normal_report",
            "type": "output/report",
            "position": {"x": 520, "y": 560},
            "data": {
                "label": "Normal Branch Report",
                "template": (
                    "# Webhook Smoke Result\n\n"
                    "Branch selected: `normal`\n\n"
                    "- event: {event_name}\n"
                    "- severity: {severity}\n"
                    "- source: {source}\n"
                    "- ticket_id: {ticket_id}\n\n"
                    "Message:\n{message}\n"
                ),
            },
        },
    ]


def build_webhook_smoke_edges() -> list[dict]:
    return [
        {
            "id": "e1",
            "source": "webhook_start",
            "target": "payload_report",
            "sourceHandle": "out",
            "animated": True,
        },
        {
            "id": "e2",
            "source": "payload_report",
            "target": "severity_check",
            "sourceHandle": "success",
            "animated": True,
        },
        {
            "id": "e3",
            "source": "severity_check",
            "target": "critical_report",
            "sourceHandle": "true",
            "animated": True,
            "label": "critical",
        },
        {
            "id": "e4",
            "source": "severity_check",
            "target": "normal_report",
            "sourceHandle": "false",
            "animated": True,
            "label": "normal",
        },
    ]


WEBHOOK_SMOKE_TEMPLATE = {
    "slug": "webhook-smoke-test",
    "name": WEBHOOK_SMOKE_PIPELINE_NAME,
    "description": WEBHOOK_SMOKE_DESCRIPTION,
    "icon": "🧪",
    "category": "Testing",
    "tags": ["webhook", "smoke", "testing", "studio"],
    "nodes": build_webhook_smoke_nodes(),
    "edges": build_webhook_smoke_edges(),
    "graph_version": CURRENT_PIPELINE_GRAPH_VERSION,
}


def ensure_webhook_smoke_pipeline(user) -> Pipeline:
    pipeline, _ = Pipeline.objects.update_or_create(
        owner=user,
        name=WEBHOOK_SMOKE_PIPELINE_NAME,
        defaults={
            "description": WEBHOOK_SMOKE_DESCRIPTION,
            "icon": "🧪",
            "tags": ["webhook", "smoke", "testing", "studio"],
            "nodes": build_webhook_smoke_nodes(),
            "edges": build_webhook_smoke_edges(),
            "graph_version": CURRENT_PIPELINE_GRAPH_VERSION,
            "is_shared": False,
        },
    )
    pipeline.sync_triggers_from_nodes()
    return pipeline
