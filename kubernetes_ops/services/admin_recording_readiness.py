from __future__ import annotations

from typing import Any

from django.db import OperationalError, ProgrammingError

from kubernetes_ops.services.admin_recording import recording_retention_inventory


def build_admin_recording_retention_report() -> dict[str, Any]:
    try:
        inventory = recording_retention_inventory()
    except (OperationalError, ProgrammingError):
        return {
            "status": "missing",
            "available": False,
            "command": "python manage.py migrate kubernetes_ops",
            "summary": {},
            "detail": "Kubernetes Admin Mode recording tables are not ready.",
        }
    summary = inventory["summary"]
    return {
        "status": "ready",
        "available": True,
        "command": "python manage.py cleanup_kubernetes_admin_recordings --apply",
        "dry_run_command": "python manage.py cleanup_kubernetes_admin_recordings",
        "inventory_command": "python manage.py cleanup_kubernetes_admin_recordings --inventory",
        "summary": summary,
        "metadata_expired_by_operation": inventory["metadata_expired_by_operation"],
        "transcript_expired_by_operation": inventory["transcript_expired_by_operation"],
        "detail": (
            "Admin recording retention cleanup is available: "
            f"metadata_expired={summary['metadata_expired_count']}, "
            f"transcript_expired={summary['transcript_expired_count']}, "
            f"transcript_event_expired={summary['transcript_event_expired_count']}."
        ),
    }


def kubernetes_admin_recording_retention_check() -> dict[str, Any]:
    report = build_admin_recording_retention_report()
    return {
        "id": "admin_recording_retention",
        "status": report["status"],
        "detail": report["detail"],
        "required": False,
    }
