"""Pilot pipeline templates for maintenance and recovery workflows."""


PILOT_MAINTENANCE_TEMPLATES = [
{
        "slug": "pilot-linux-disk-cleanup",
        "name": "Pilot: Linux Disk Cleanup",
        "description": "Inspect disk pressure, review cleanup risk, approve bounded tmp cleanup, verify disk state and report.",
        "icon": "DSK",
        "category": "Pilot OPS",
        "tags": ["pilot", "linux", "disk", "cleanup", "approval"],
        "nodes": [
            {"id": "manual", "type": "trigger/manual", "position": {"x": 120, "y": 80}, "data": {"label": "Start disk cleanup"}},
            {
                "id": "inspect_disk",
                "type": "ops/disk_cleanup",
                "position": {"x": 120, "y": 220},
                "data": {
                    "label": "Inspect disk usage",
                    "server_id": "",
                    "action": "inspect",
                    "dry_run": True,
                    "on_failure": "abort",
                },
            },
            {
                "id": "review",
                "type": "agent/llm_query",
                "position": {"x": 120, "y": 370},
                "data": {
                    "label": "Review cleanup risk",
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "system_prompt": "You are a Linux operations reviewer. Prefer bounded cleanup and never delete arbitrary paths.",
                    "prompt": (
                        "Review disk pressure and cleanup candidates.\n\n"
                        "{inspect_disk_output}\n\n"
                        "Return risk level, expected reclaimed areas, services that might be affected, exact cleanup action and verification plan."
                    ),
                    "include_all_outputs": False,
                },
            },
            {
                "id": "approval",
                "type": "logic/human_approval",
                "position": {"x": 120, "y": 520},
                "data": {
                    "label": "Approve disk cleanup",
                    "manual_link_only": True,
                    "timeout_minutes": 60,
                    "message": "Disk cleanup requires approval.\n\n{review_output}\n\nApprove: {approve_url}\nReject: {reject_url}",
                },
            },
            {
                "id": "cleanup",
                "type": "ops/disk_cleanup",
                "position": {"x": 120, "y": 690},
                "data": {
                    "label": "Cleanup old tmp files",
                    "server_id": "",
                    "action": "tmp_cleanup",
                    "dry_run": False,
                    "verify": True,
                    "min_age_days": 7,
                    "max_entries": 50,
                    "on_failure": "abort",
                },
            },
            {
                "id": "verify_disk",
                "type": "ops/disk_cleanup",
                "position": {"x": 120, "y": 850},
                "data": {
                    "label": "Verify disk state",
                    "server_id": "",
                    "action": "inspect",
                    "dry_run": True,
                    "on_failure": "continue",
                },
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 120, "y": 1010},
                "data": {
                    "label": "Disk cleanup report",
                    "template": "# Linux disk cleanup report\n\n## Before\n{inspect_disk_output}\n\n## Review\n{review_output}\n\n## Approval\n{approval_output}\n\n## Cleanup\n{cleanup_output}\n\n## Verification\n{verify_disk_output}",
                },
            },
            {"id": "rejected", "type": "output/report", "position": {"x": 520, "y": 690}, "data": {"label": "Disk cleanup rejected", "template": "# Disk cleanup rejected\n\n{approval_error}\n\n## Review\n{review_output}"}},
            {"id": "timed_out", "type": "output/report", "position": {"x": 520, "y": 850}, "data": {"label": "Disk cleanup timed out", "template": "# Disk cleanup timed out\n\nNo approval was received.\n\n## Review\n{review_output}"}},
        ],
        "edges": [
            {"id": "e-manual-inspect", "source": "manual", "target": "inspect_disk", "sourceHandle": "out", "animated": True},
            {"id": "e-inspect-review", "source": "inspect_disk", "target": "review", "sourceHandle": "success", "animated": True},
            {"id": "e-review-approval", "source": "review", "target": "approval", "sourceHandle": "success", "animated": True},
            {"id": "e-approval-cleanup", "source": "approval", "target": "cleanup", "sourceHandle": "approved", "label": "approved"},
            {"id": "e-approval-rejected", "source": "approval", "target": "rejected", "sourceHandle": "rejected", "label": "rejected"},
            {"id": "e-approval-timeout", "source": "approval", "target": "timed_out", "sourceHandle": "timeout", "label": "timeout"},
            {"id": "e-cleanup-verify", "source": "cleanup", "target": "verify_disk", "sourceHandle": "success", "animated": True},
            {"id": "e-verify-report", "source": "verify_disk", "target": "report", "sourceHandle": "out", "animated": True},
        ],
    },
{
        "slug": "pilot-backup-restore-check",
        "name": "Pilot: Backup Restore Check",
        "description": "Read-only backup freshness and latest archive integrity check, with AI review and report.",
        "icon": "BKP",
        "category": "Pilot OPS",
        "tags": ["pilot", "linux", "backup", "restore", "read-only"],
        "nodes": [
            {"id": "manual", "type": "trigger/manual", "position": {"x": 120, "y": 80}, "data": {"label": "Start backup check"}},
            {
                "id": "inspect_backup",
                "type": "ops/backup_restore_check",
                "position": {"x": 120, "y": 220},
                "data": {
                    "label": "Inspect backup directory",
                    "server_id": "",
                    "action": "inspect",
                    "path": "{backup_path}",
                    "max_depth": 2,
                    "max_files": 20,
                    "max_age_hours": 24,
                    "on_failure": "abort",
                },
            },
            {
                "id": "verify_latest",
                "type": "ops/backup_restore_check",
                "position": {"x": 120, "y": 370},
                "data": {
                    "label": "Verify latest backup archive",
                    "server_id": "",
                    "action": "verify_latest",
                    "path": "{backup_path}",
                    "max_depth": 2,
                    "max_files": 20,
                    "max_age_hours": 24,
                    "on_failure": "continue",
                },
            },
            {
                "id": "review",
                "type": "agent/llm_query",
                "position": {"x": 120, "y": 520},
                "data": {
                    "label": "Review backup readiness",
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "system_prompt": "You are a backup reliability reviewer. Do not claim restore succeeded unless restore evidence exists.",
                    "prompt": (
                        "Review backup freshness and latest archive verification.\n\n"
                        "Backup path: {backup_path}\n"
                        "Accepted age hours: 24\n\n"
                        "Inspection:\n{inspect_backup_output}\n\n"
                        "Verification:\n{verify_latest_output}\n\n"
                        "Return readiness, stale/missing risks, restore confidence, and next manual restore drill recommendation."
                    ),
                    "include_all_outputs": False,
                },
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 120, "y": 690},
                "data": {
                    "label": "Backup check report",
                    "template": "# Backup restore check report\n\n## Inspection\n{inspect_backup_output}\n\n## Archive verification\n{verify_latest_output}\n\n## Review\n{review_output}",
                },
            },
        ],
        "edges": [
            {"id": "e-manual-inspect", "source": "manual", "target": "inspect_backup", "sourceHandle": "out", "animated": True},
            {"id": "e-inspect-verify", "source": "inspect_backup", "target": "verify_latest", "sourceHandle": "success", "animated": True},
            {"id": "e-verify-review", "source": "verify_latest", "target": "review", "sourceHandle": "out", "animated": True},
            {"id": "e-review-report", "source": "review", "target": "report", "sourceHandle": "success", "animated": True},
        ],
    },
{
        "slug": "pilot-service-config-validate-restart",
        "name": "Pilot: Service Config Validate And Restart",
        "description": "Collect service evidence, review config risk, approve restart, run structured service action, verify HTTP health and report.",
        "icon": "SVC",
        "category": "Pilot OPS",
        "tags": ["pilot", "linux", "service", "restart", "approval"],
        "nodes": [
            {"id": "manual", "type": "trigger/manual", "position": {"x": 120, "y": 80}, "data": {"label": "Start service maintenance"}},
            {
                "id": "snapshot",
                "type": "ops/server_snapshot",
                "position": {"x": 120, "y": 220},
                "data": {
                    "label": "Collect service snapshot",
                    "server_id": "",
                    "sections": ["overview", "services", "logs", "disk", "network"],
                    "on_failure": "abort",
                },
            },
            {
                "id": "review",
                "type": "agent/llm_query",
                "position": {"x": 120, "y": 370},
                "data": {
                    "label": "Review restart risk",
                    "provider": "openai",
                    "model": "gpt-5-mini",
                    "system_prompt": "You are a Linux service operations reviewer. Require approval before restart/reload.",
                    "prompt": (
                        "Review the service snapshot for service '{service_name}'.\n\n"
                        "{snapshot_output}\n\n"
                        "Return config/risk notes, expected impact, restart command, verification URL and rollback note."
                    ),
                    "include_all_outputs": False,
                },
            },
            {
                "id": "approval",
                "type": "logic/human_approval",
                "position": {"x": 120, "y": 520},
                "data": {
                    "label": "Approve service restart",
                    "manual_link_only": True,
                    "timeout_minutes": 60,
                    "message": "Service restart requires approval.\n\n{review_output}\n\nApprove: {approve_url}\nReject: {reject_url}",
                },
            },
            {
                "id": "restart",
                "type": "ops/service_action",
                "position": {"x": 120, "y": 690},
                "data": {
                    "label": "Restart service",
                    "server_id": "",
                    "service": "{service_name}",
                    "action": "restart",
                    "preflight_commands": ["systemctl is-active {service_name} || true"],
                    "verification_commands": ["systemctl is-active {service_name}"],
                    "on_failure": "abort",
                },
            },
            {
                "id": "http_check",
                "type": "ops/http_check",
                "position": {"x": 120, "y": 850},
                "data": {
                    "label": "Verify HTTP health",
                    "url": "{healthcheck_url}",
                    "method": "GET",
                    "expected_status": [200, 204],
                    "retries": 5,
                    "timeout_seconds": 5,
                    "body_contains": "",
                    "on_failure": "continue",
                },
            },
            {
                "id": "report",
                "type": "output/report",
                "position": {"x": 120, "y": 1010},
                "data": {
                    "label": "Service maintenance report",
                    "template": "# Service maintenance report\n\n## Snapshot\n{snapshot_output}\n\n## Review\n{review_output}\n\n## Approval\n{approval_output}\n\n## Restart\n{restart_output}\n\n## HTTP check\n{http_check_output}",
                },
            },
            {"id": "rejected", "type": "output/report", "position": {"x": 520, "y": 690}, "data": {"label": "Service restart rejected", "template": "# Service restart rejected\n\n{approval_error}\n\n## Review\n{review_output}"}},
            {"id": "timed_out", "type": "output/report", "position": {"x": 520, "y": 850}, "data": {"label": "Service restart timed out", "template": "# Service restart timed out\n\nNo approval was received.\n\n## Review\n{review_output}"}},
        ],
        "edges": [
            {"id": "e-manual-snapshot", "source": "manual", "target": "snapshot", "sourceHandle": "out", "animated": True},
            {"id": "e-snapshot-review", "source": "snapshot", "target": "review", "sourceHandle": "success", "animated": True},
            {"id": "e-review-approval", "source": "review", "target": "approval", "sourceHandle": "success", "animated": True},
            {"id": "e-approval-restart", "source": "approval", "target": "restart", "sourceHandle": "approved", "label": "approved"},
            {"id": "e-approval-rejected", "source": "approval", "target": "rejected", "sourceHandle": "rejected", "label": "rejected"},
            {"id": "e-approval-timeout", "source": "approval", "target": "timed_out", "sourceHandle": "timeout", "label": "timeout"},
            {"id": "e-restart-http", "source": "restart", "target": "http_check", "sourceHandle": "success", "animated": True},
            {"id": "e-http-report", "source": "http_check", "target": "report", "sourceHandle": "out", "animated": True},
        ],
    },
]
