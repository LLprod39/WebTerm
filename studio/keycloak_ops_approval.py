from __future__ import annotations


def build_ops_approval_node(environment_label: str) -> dict:
    return {
        "id": "await_execution_approval",
        "type": "logic/human_approval",
        "position": {"x": 480, "y": 960},
        "data": {
            "label": "8. Approve Execution",
            "manual_link_only": True,
            "timeout_minutes": 240,
            "message": (
                f"Keycloak {environment_label} task execution requires approval.\n\n"
                "## Normalized brief\n"
                "{normalize_request_output}\n\n"
                "## Execution plan\n"
                "{build_execution_plan_output}\n\n"
                "Approve: {approve_url}\n"
                "Reject: {reject_url}"
            ),
            "on_failure": "continue",
        },
    }


def build_ops_rejected_report_node(environment_label: str) -> dict:
    return {
        "id": "execution_rejected",
        "type": "output/report",
        "position": {"x": 80, "y": 1200},
        "data": {
            "label": "Execution Rejected",
            "template": (
                f"# Keycloak {environment_label} execution rejected\n\n"
                "{await_execution_approval_error}\n\n"
                "## Execution plan\n"
                "{build_execution_plan_output}"
            ),
        },
    }


def build_ops_timeout_report_node(environment_label: str) -> dict:
    return {
        "id": "execution_approval_timed_out",
        "type": "output/report",
        "position": {"x": 880, "y": 1200},
        "data": {
            "label": "Execution Approval Timed Out",
            "template": (
                f"# Keycloak {environment_label} execution approval timed out\n\n"
                "{await_execution_approval_error}\n\n"
                "## Execution plan\n"
                "{build_execution_plan_output}"
            ),
        },
    }


def build_keycloak_ops_edges() -> list[dict]:
    return [
        {"id": "e1", "source": "start_manual", "target": "entry_join", "sourceHandle": "out", "animated": True},
        {"id": "e2", "source": "start_webhook", "target": "entry_join", "sourceHandle": "out", "animated": True},
        {"id": "e3", "source": "entry_join", "target": "environment_preflight", "sourceHandle": "out", "animated": True},
        {"id": "e4", "source": "environment_preflight", "target": "normalize_request", "sourceHandle": "success", "animated": True},
        {"id": "e5", "source": "normalize_request", "target": "discovery_split", "sourceHandle": "success", "animated": True},
        {"id": "e6", "source": "discovery_split", "target": "discover_clients_roles", "sourceHandle": "out", "animated": True},
        {"id": "e7", "source": "discovery_split", "target": "discover_users", "sourceHandle": "out", "animated": True},
        {"id": "e8", "source": "discovery_split", "target": "discover_groups_roles", "sourceHandle": "out", "animated": True},
        {"id": "e9", "source": "discover_clients_roles", "target": "discover_protocol_mappers", "sourceHandle": "success", "animated": True},
        {"id": "e10", "source": "discover_clients_roles", "target": "discoveries_ready", "sourceHandle": "success", "animated": True},
        {"id": "e11", "source": "discover_clients_roles", "target": "discoveries_ready", "sourceHandle": "error", "animated": True},
        {"id": "e12", "source": "discover_users", "target": "discoveries_ready", "sourceHandle": "success", "animated": True},
        {"id": "e13", "source": "discover_users", "target": "discoveries_ready", "sourceHandle": "error", "animated": True},
        {"id": "e14", "source": "discover_groups_roles", "target": "discoveries_ready", "sourceHandle": "success", "animated": True},
        {"id": "e15", "source": "discover_groups_roles", "target": "discoveries_ready", "sourceHandle": "error", "animated": True},
        {"id": "e16", "source": "discover_protocol_mappers", "target": "discoveries_ready", "sourceHandle": "success", "animated": True},
        {"id": "e17", "source": "discover_protocol_mappers", "target": "discoveries_ready", "sourceHandle": "error", "animated": True},
        {"id": "e18", "source": "discoveries_ready", "target": "build_execution_plan", "sourceHandle": "out", "animated": True},
        {"id": "e19", "source": "build_execution_plan", "target": "await_execution_approval", "sourceHandle": "success", "animated": True},
        {"id": "e20", "source": "await_execution_approval", "target": "execution_split", "sourceHandle": "approved", "animated": True},
        {"id": "e21", "source": "await_execution_approval", "target": "execution_rejected", "sourceHandle": "rejected", "animated": True},
        {"id": "e22", "source": "await_execution_approval", "target": "execution_approval_timed_out", "sourceHandle": "timeout", "animated": True},
        {"id": "e23", "source": "execution_split", "target": "execute_identity_actions", "sourceHandle": "out", "animated": True},
        {"id": "e24", "source": "execution_split", "target": "execute_platform_actions", "sourceHandle": "out", "animated": True},
        {"id": "e25", "source": "execute_identity_actions", "target": "verify_identity_state", "sourceHandle": "success", "animated": True},
        {"id": "e26", "source": "execute_platform_actions", "target": "verify_platform_state", "sourceHandle": "success", "animated": True},
        {"id": "e27", "source": "verify_identity_state", "target": "verification_merge", "sourceHandle": "success", "animated": True},
        {"id": "e28", "source": "verify_identity_state", "target": "verification_merge", "sourceHandle": "error", "animated": True},
        {"id": "e29", "source": "verify_platform_state", "target": "verification_merge", "sourceHandle": "success", "animated": True},
        {"id": "e30", "source": "verify_platform_state", "target": "verification_merge", "sourceHandle": "error", "animated": True},
        {"id": "e31", "source": "verification_merge", "target": "final_report", "sourceHandle": "out", "animated": True},
    ]
