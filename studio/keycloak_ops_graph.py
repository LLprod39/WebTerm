from __future__ import annotations

from .keycloak_ops_approval import (
    build_ops_approval_node,
    build_ops_rejected_report_node,
    build_ops_timeout_report_node,
)
from .keycloak_ops_prompts import (
    _discovery_clients_goal,
    _discovery_groups_roles_goal,
    _discovery_protocol_mappers_goal,
    _discovery_users_goal,
    _identity_execution_goal,
    _identity_verification_goal,
    _normalize_prompt,
    _plan_prompt,
    _platform_execution_goal,
    _platform_verification_goal,
)
from .keycloak_provisioning_config import (
    KEYCLOAK_CLIENT_DISCOVERY_TOOLS,
    KEYCLOAK_GROUP_ROLE_DISCOVERY_TOOLS,
    KEYCLOAK_IDENTITY_EXECUTION_TOOLS,
    KEYCLOAK_IDENTITY_VERIFY_TOOLS,
    KEYCLOAK_PLATFORM_EXECUTION_TOOLS,
    KEYCLOAK_PLATFORM_VERIFY_TOOLS,
    KEYCLOAK_PROTOCOL_MAPPER_DISCOVERY_TOOLS,
    KEYCLOAK_USER_DISCOVERY_TOOLS,
    TASK_WEBHOOK_CONTEXT_MAP,
    _json_payload,
)


def build_keycloak_ops_nodes(mcp_server_id: int, *, fixed_profile: str, environment_label: str) -> list[dict]:
    return [
        {
            "id": "start_manual",
            "type": "trigger/manual",
            "position": {"x": 340, "y": 40},
            "data": {
                "label": f"Run {environment_label} Keycloak Task",
                "is_active": True,
                "description": (
                    "Universal manual Keycloak flow. Paste any free-form Keycloak request into the Run dialog, "
                    "and the pipeline will normalize, discover, plan, execute, and verify."
                ),
            },
        },
        {
            "id": "start_webhook",
            "type": "trigger/webhook",
            "position": {"x": 820, "y": 40},
            "data": {
                "label": f"Webhook {environment_label} Keycloak Task",
                "is_active": True,
                "webhook_payload_map": TASK_WEBHOOK_CONTEXT_MAP,
            },
        },
        {
            "id": "entry_join",
            "type": "logic/merge",
            "position": {"x": 580, "y": 110},
            "data": {
                "label": "Selected Trigger Entry",
                "mode": "any",
            },
        },
        {
            "id": "environment_preflight",
            "type": "agent/mcp_call",
            "position": {"x": 480, "y": 180},
            "data": {
                "label": "1. Environment Preflight",
                "mcp_server_id": mcp_server_id,
                "tool_name": "keycloak_current_environment",
                "arguments_text": _json_payload({"profile": fixed_profile}),
                "on_failure": "abort",
            },
        },
        {
            "id": "normalize_request",
            "type": "agent/llm_query",
            "position": {"x": 480, "y": 360},
            "data": {
                "label": "2. Normalize Request",
                "provider": "openai",
                "model": "gpt-5-mini",
                "system_prompt": (
                    "You are a careful Keycloak operations planner. "
                    "Turn broad free-form Keycloak requests into strict execution briefs without inventing missing values."
                ),
                "prompt": _normalize_prompt(fixed_profile, environment_label),
                "include_all_outputs": False,
                "on_failure": "abort",
            },
        },
        {
            "id": "discovery_split",
            "type": "logic/parallel",
            "position": {"x": 480, "y": 470},
            "data": {
                "label": "Discovery Fan-Out",
            },
        },
        {
            "id": "discover_clients_roles",
            "type": "agent/react",
            "position": {"x": 100, "y": 580},
            "data": {
                "label": "3. Discover Clients & Client Roles",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 24,
                "allowed_tools": KEYCLOAK_CLIENT_DISCOVERY_TOOLS,
                "system_prompt": (
                    "You are a cautious Keycloak client discovery agent. "
                    "Prefer read-only checks, deterministic reasoning, and structured outputs."
                ),
                "goal": _discovery_clients_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "discover_users",
            "type": "agent/react",
            "position": {"x": 360, "y": 580},
            "data": {
                "label": "4. Discover Users",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 24,
                "allowed_tools": KEYCLOAK_USER_DISCOVERY_TOOLS,
                "system_prompt": (
                    "You are a cautious Keycloak user discovery agent. "
                    "Prefer read-only checks, deterministic reasoning, and structured outputs."
                ),
                "goal": _discovery_users_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "discover_groups_roles",
            "type": "agent/react",
            "position": {"x": 620, "y": 580},
            "data": {
                "label": "5. Discover Groups & Realm Roles",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 24,
                "allowed_tools": KEYCLOAK_GROUP_ROLE_DISCOVERY_TOOLS,
                "system_prompt": (
                    "You are a cautious Keycloak group and realm-role discovery agent. "
                    "Prefer read-only checks, deterministic reasoning, and structured outputs."
                ),
                "goal": _discovery_groups_roles_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "discover_protocol_mappers",
            "type": "agent/react",
            "position": {"x": 880, "y": 580},
            "data": {
                "label": "6. Discover Protocol Mappers",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 24,
                "allowed_tools": KEYCLOAK_PROTOCOL_MAPPER_DISCOVERY_TOOLS,
                "system_prompt": (
                    "You are a cautious Keycloak protocol-mapper discovery agent. "
                    "Prefer read-only checks, deterministic reasoning, and structured outputs."
                ),
                "goal": _discovery_protocol_mappers_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "discoveries_ready",
            "type": "logic/merge",
            "position": {"x": 480, "y": 720},
            "data": {
                "label": "Discoveries Ready",
                "mode": "all",
            },
        },
        {
            "id": "build_execution_plan",
            "type": "agent/llm_query",
            "position": {"x": 480, "y": 840},
            "data": {
                "label": "7. Build Safe Execution Plan",
                "provider": "openai",
                "model": "gpt-5-mini",
                "system_prompt": (
                    "You are a careful IAM planner. "
                    "Convert normalized and discovered Keycloak state into a safe execution plan."
                ),
                "prompt": _plan_prompt(fixed_profile, environment_label),
                "include_all_outputs": False,
                "on_failure": "abort",
            },
        },
        {
            "id": "execution_split",
            "type": "logic/parallel",
            "position": {"x": 480, "y": 1080},
            "data": {
                "label": "Execution Fan-Out",
            },
        },
        build_ops_approval_node(environment_label),
        {
            "id": "execute_identity_actions",
            "type": "agent/react",
            "position": {"x": 240, "y": 1200},
            "data": {
                "label": "9. Execute Identity Actions",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 60,
                "allowed_tools": KEYCLOAK_IDENTITY_EXECUTION_TOOLS,
                "system_prompt": (
                    "You are a Keycloak identity operator. Work only through attached MCP tools. "
                    "Be strict, deterministic, and stop instead of guessing."
                ),
                "goal": _identity_execution_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "execute_platform_actions",
            "type": "agent/react",
            "position": {"x": 720, "y": 1200},
            "data": {
                "label": "10. Execute Platform Actions",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 60,
                "allowed_tools": KEYCLOAK_PLATFORM_EXECUTION_TOOLS,
                "system_prompt": (
                    "You are a Keycloak platform operator. Work only through attached MCP tools. "
                    "Be strict, deterministic, and stop instead of guessing."
                ),
                "goal": _platform_execution_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "verify_identity_state",
            "type": "agent/react",
            "position": {"x": 240, "y": 1440},
            "data": {
                "label": "11. Verify Identity State",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 24,
                "allowed_tools": KEYCLOAK_IDENTITY_VERIFY_TOOLS,
                "system_prompt": (
                    "You are a read-only Keycloak identity verification agent. "
                    "Check the final state and do not mutate anything."
                ),
                "goal": _identity_verification_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "verify_platform_state",
            "type": "agent/react",
            "position": {"x": 720, "y": 1440},
            "data": {
                "label": "12. Verify Platform State",
                "provider": "openai",
                "model": "gpt-5-mini",
                "mcp_server_ids": [mcp_server_id],
                "max_iterations": 24,
                "allowed_tools": KEYCLOAK_PLATFORM_VERIFY_TOOLS,
                "system_prompt": (
                    "You are a read-only Keycloak platform verification agent. "
                    "Check the final state and do not mutate anything."
                ),
                "goal": _platform_verification_goal(fixed_profile, environment_label),
                "on_failure": "abort",
            },
        },
        {
            "id": "verification_merge",
            "type": "logic/merge",
            "position": {"x": 480, "y": 1580},
            "data": {
                "label": "Verification Ready",
                "mode": "all",
            },
        },
        {
            "id": "final_report",
            "type": "output/report",
            "position": {"x": 480, "y": 1700},
            "data": {
                "label": "13. Final Report",
                "template": (
                    f"# Keycloak {environment_label} Execution Report\n\n"
                    f"- fixed_profile: {fixed_profile}\n"
                    "- requester: {requester}\n"
                    "- task: {task}\n"
                    "- allow_existing_user: {allow_existing_user}\n\n"
                    "## Environment Preflight\n"
                    "{environment_preflight_output}\n\n"
                    "## Normalized Brief\n"
                    "{normalize_request_output}\n\n"
                    "## Discovery: Clients & Client Roles\n"
                    "- status: {discover_clients_roles_status}\n"
                    "- error: {discover_clients_roles_error}\n\n"
                    "{discover_clients_roles_output}\n\n"
                    "## Discovery: Users\n"
                    "- status: {discover_users_status}\n"
                    "- error: {discover_users_error}\n\n"
                    "{discover_users_output}\n\n"
                    "## Discovery: Groups & Realm Roles\n"
                    "- status: {discover_groups_roles_status}\n"
                    "- error: {discover_groups_roles_error}\n\n"
                    "{discover_groups_roles_output}\n\n"
                    "## Discovery: Protocol Mappers\n"
                    "- status: {discover_protocol_mappers_status}\n"
                    "- error: {discover_protocol_mappers_error}\n\n"
                    "{discover_protocol_mappers_output}\n\n"
                    "## Execution Plan\n"
                    "{build_execution_plan_output}\n\n"
                    "## Approval\n"
                    "- status: {await_execution_approval_status}\n"
                    "- output: {await_execution_approval_output}\n"
                    "- error: {await_execution_approval_error}\n\n"
                    "## Execution: Identity Actions\n"
                    "- status: {execute_identity_actions_status}\n"
                    "- error: {execute_identity_actions_error}\n\n"
                    "{execute_identity_actions_output}\n\n"
                    "## Execution: Platform Actions\n"
                    "- status: {execute_platform_actions_status}\n"
                    "- error: {execute_platform_actions_error}\n\n"
                    "{execute_platform_actions_output}\n\n"
                    "## Verification: Identity State\n"
                    "- status: {verify_identity_state_status}\n"
                    "- error: {verify_identity_state_error}\n\n"
                    "{verify_identity_state_output}\n\n"
                    "## Verification: Platform State\n"
                    "- status: {verify_platform_state_status}\n"
                    "- error: {verify_platform_state_error}\n\n"
                    "{verify_platform_state_output}\n"
                ),
            },
        },
        build_ops_rejected_report_node(environment_label),
        build_ops_timeout_report_node(environment_label),
    ]
