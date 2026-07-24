"""Pilot package-maintenance pipeline template."""

PILOT_LINUX_PACKAGE_MAINTENANCE_TEMPLATE = {
    "slug": "pilot-linux-package-maintenance",
    "name": "Pilot: Linux Package Maintenance",
    "description": "Check package update state, review risk, update explicit package list after approval, verify packages and report.",
    "icon": "PKG",
    "category": "Pilot OPS",
    "tags": ["pilot", "linux", "packages", "maintenance", "approval"],
    "nodes": [
        {
            "id": "manual",
            "type": "trigger/manual",
            "position": {"x": 120, "y": 80},
            "data": {"label": "Start package maintenance"},
        },
        {
            "id": "package_snapshot",
            "type": "ops/server_snapshot",
            "position": {"x": 120, "y": 220},
            "data": {
                "label": "Read package state",
                "server_id": "",
                "sections": ["overview", "packages", "services", "disk"],
                "on_failure": "abort",
            },
        },
        {
            "id": "review",
            "type": "agent/llm_query",
            "position": {"x": 120, "y": 370},
            "data": {
                "label": "Review package update risk",
                "provider": "openai",
                "model": "gpt-5-mini",
                "system_prompt": "You are a Linux maintenance reviewer. Require approval before package changes and avoid full system upgrades.",
                "prompt": (
                    "Review package maintenance evidence and the explicit package request.\n\n"
                    "Requested packages: {packages}\n\n"
                    "Package/server state:\n{package_snapshot_output}\n\n"
                    "Return risk, service impact, exact package action, rollback note and post-update verification checklist."
                ),
                "include_all_outputs": False,
            },
        },
        {
            "id": "approval",
            "type": "logic/human_approval",
            "position": {"x": 120, "y": 520},
            "data": {
                "label": "Approve package update",
                "manual_link_only": True,
                "timeout_minutes": 120,
                "message": "Linux package update requires approval.\n\n{review_output}\n\nApprove: {approve_url}\nReject: {reject_url}",
            },
        },
        {
            "id": "apply_updates",
            "type": "ops/package_action",
            "position": {"x": 120, "y": 690},
            "data": {
                "label": "Update explicit packages",
                "server_id": "",
                "action": "update",
                "packages": "{packages}",
                "verify": True,
                "on_failure": "abort",
            },
        },
        {
            "id": "verify_packages",
            "type": "ops/package_action",
            "position": {"x": 120, "y": 850},
            "data": {
                "label": "Verify package state",
                "server_id": "",
                "action": "list_updates",
                "verify": False,
                "on_failure": "continue",
            },
        },
        {
            "id": "report",
            "type": "output/report",
            "position": {"x": 120, "y": 1010},
            "data": {
                "label": "Package maintenance report",
                "template": "# Linux package maintenance report\n\n## Package state\n{package_snapshot_output}\n\n## Review\n{review_output}\n\n## Approval\n{approval_output}\n\n## Update\n{apply_updates_output}\n\n## Verification\n{verify_packages_output}",
            },
        },
        {
            "id": "rejected",
            "type": "output/report",
            "position": {"x": 520, "y": 690},
            "data": {
                "label": "Package update rejected",
                "template": "# Package update rejected\n\n{approval_error}\n\n## Review\n{review_output}",
            },
        },
        {
            "id": "timed_out",
            "type": "output/report",
            "position": {"x": 520, "y": 850},
            "data": {
                "label": "Package update timed out",
                "template": "# Package update timed out\n\nNo approval was received.\n\n## Review\n{review_output}",
            },
        },
    ],
    "edges": [
        {
            "id": "e-manual-snapshot",
            "source": "manual",
            "target": "package_snapshot",
            "sourceHandle": "out",
            "animated": True,
        },
        {
            "id": "e-snapshot-review",
            "source": "package_snapshot",
            "target": "review",
            "sourceHandle": "success",
            "animated": True,
        },
        {
            "id": "e-review-approval",
            "source": "review",
            "target": "approval",
            "sourceHandle": "success",
            "animated": True,
        },
        {
            "id": "e-approval-update",
            "source": "approval",
            "target": "apply_updates",
            "sourceHandle": "approved",
            "label": "approved",
        },
        {
            "id": "e-approval-rejected",
            "source": "approval",
            "target": "rejected",
            "sourceHandle": "rejected",
            "label": "rejected",
        },
        {
            "id": "e-approval-timeout",
            "source": "approval",
            "target": "timed_out",
            "sourceHandle": "timeout",
            "label": "timeout",
        },
        {
            "id": "e-update-verify",
            "source": "apply_updates",
            "target": "verify_packages",
            "sourceHandle": "success",
            "animated": True,
        },
        {
            "id": "e-verify-report",
            "source": "verify_packages",
            "target": "report",
            "sourceHandle": "out",
            "animated": True,
        },
    ],
}
