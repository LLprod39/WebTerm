from __future__ import annotations

from typing import Any

from studio.keycloak_provisioning import (
    KEYCLOAK_IDENTITY_EXECUTION_TOOLS,
    KEYCLOAK_IDENTITY_VERIFY_TOOLS,
    KEYCLOAK_PLATFORM_EXECUTION_TOOLS,
    KEYCLOAK_PLATFORM_VERIFY_TOOLS,
    TASK_WEBHOOK_CONTEXT_MAP,
)

KEYCLOAK_TERMS = ("keycloak", "киклок", "keycloack", "kc", "iam")


def _text(value: Any) -> str:
    return str(value or "").strip()


def is_keycloak_request(message: str) -> bool:
    lowered = _text(message).lower()
    return any(term in lowered for term in KEYCLOAK_TERMS)


def _pick_keycloak_mcp(context: dict[str, Any]) -> dict[str, Any] | None:
    candidates = context.get("available_mcp_servers") if isinstance(context.get("available_mcp_servers"), list) else []
    current_user_id = context.get("current_user_id")
    matches: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        haystack = " ".join(_text(item.get(field)).lower() for field in ("name", "description", "url", "transport"))
        if "keycloak" in haystack or "киклок" in haystack:
            matches.append(item)
    if not matches:
        return None
    owned = [item for item in matches if item.get("owner_id") == current_user_id]
    healthy_owned = [item for item in owned if item.get("last_test_ok") is not False]
    healthy_any = [item for item in matches if item.get("last_test_ok") is not False]
    return (healthy_owned or owned or healthy_any or matches)[0]


def _pick_keycloak_skills(context: dict[str, Any], message: str) -> list[dict[str, Any]]:
    skills = context.get("available_skills") if isinstance(context.get("available_skills"), list) else []
    lowered = _text(message).lower()
    selected: list[dict[str, Any]] = []
    for item in skills:
        if not isinstance(item, dict):
            continue
        haystack = " ".join(_text(item.get(field)).lower() for field in ("slug", "name", "service", "category"))
        if "keycloak" not in haystack:
            continue
        slug = _text(item.get("slug"))
        if not slug:
            continue
        if slug.endswith("-prod-profile") and not any(token in lowered for token in ("prod", "прод", "production")):
            continue
        if slug.endswith("-test-profile") and not any(token in lowered for token in ("test", "тест", "dev", "stage")):
            continue
        selected.append(item)
    safety = [item for item in selected if "safety" in _text(item.get("slug"))]
    profiles = [item for item in selected if "profile" in _text(item.get("slug"))]
    others = [item for item in selected if item not in safety and item not in profiles]
    return [*safety, *profiles, *others][:4]


def _profile_expression(message: str) -> str:
    lowered = _text(message).lower()
    if any(token in lowered for token in ("test", "тест", "dev", "stage")):
        return "test"
    if any(token in lowered for token in ("prod", "прод", "production")):
        return "prod"
    return "{profile}"


def _node(ref: str, node_type: str, label: str, data: dict[str, Any], x: int, y: int) -> dict[str, Any]:
    return {"ref": ref, "type": node_type, "label": label, "data": {"label": label, **data}, "x_offset": x, "y_offset": y}


def _edge(source: str, target: str, handle: str = "out") -> dict[str, str]:
    return {"source": source, "target": target, "source_handle": handle}


def build_keycloak_draft_response(
    *,
    user_message: str,
    assistant_context: dict[str, Any],
    fallback_reason: str,
) -> dict[str, Any] | None:
    if not is_keycloak_request(user_message):
        return None

    mcp = _pick_keycloak_mcp(assistant_context)
    mcp_id = mcp.get("id") if mcp else None
    skills = _pick_keycloak_skills(assistant_context, user_message)
    skill_slugs = [_text(item.get("slug")) for item in skills if _text(item.get("slug"))]
    profile = _profile_expression(user_message)
    remove_node_ids = [
        _text(item.get("id"))
        for item in (assistant_context.get("graph_nodes") or [])
        if isinstance(item, dict) and _text(item.get("id"))
    ]
    resource_notes = []
    missing = []
    if mcp:
        resource_notes.append(f"Selected MCP server: {mcp.get('name')} #{mcp_id}.")
    else:
        missing.append("Keycloak Admin MCP server")
    if skill_slugs:
        resource_notes.append("Attached Keycloak skills: " + ", ".join(skill_slugs) + ".")
    else:
        missing.append("Keycloak safety/profile skill")

    agent_common = {
        "provider": "openai",
        "model": "gpt-5-mini",
        "mcp_server_ids": [mcp_id] if mcp_id else [],
        "skill_slugs": skill_slugs,
        "max_iterations": 30,
    }
    nodes = [
        _node("start_webhook", "trigger/webhook", "Keycloak Request Webhook", {"is_active": True, "webhook_payload_map": TASK_WEBHOOK_CONTEXT_MAP}, 0, 0),
        _node("start_manual", "trigger/manual", "Manual Keycloak Request", {"is_active": True}, 0, 160),
        _node("entry_join", "logic/merge", "Request Intake", {"mode": "any"}, 260, 80),
        _node(
            "environment_preflight",
            "agent/mcp_call",
            "MCP: Keycloak Preflight",
            {"mcp_server_id": mcp_id, "tool_name": "keycloak_current_environment", "arguments_text": f'{{"profile": "{profile}"}}', "on_failure": "abort"},
            520,
            80,
        ),
        _node(
            "normalize_request",
            "agent/llm_query",
            "Normalize IAM Ticket",
            {
                "system_prompt": "Normalize Keycloak service-desk requests into strict JSON. Do not invent users, clients, roles, groups, or profile.",
                "prompt": (
                    "Original request: {task}\nWebhook payload: {payload}\nPreflight: {environment_preflight_output}\n\n"
                    "Return JSON with profile, requester, ticket_id, intent, users, clients, roles, groups, required_actions, "
                    "requested_mode, blocking_issues, and approval_summary."
                ),
                "include_all_outputs": False,
                "on_failure": "abort",
            },
            780,
            80,
        ),
        _node(
            "await_approval",
            "logic/human_approval",
            "Approve Keycloak Change",
            {
                "timeout_minutes": 240,
                "message": "Approve Keycloak request {ticket_id}?\n\n{normalize_request_output}\n\nAPPROVE: {approve_url}\nREJECT: {reject_url}",
            },
            1040,
            80,
        ),
        _node(
            "execute_keycloak_task",
            "agent/react",
            "Execute Keycloak Task",
            {
                **agent_common,
                "allowed_tools": [*KEYCLOAK_IDENTITY_EXECUTION_TOOLS, *KEYCLOAK_PLATFORM_EXECUTION_TOOLS],
                "system_prompt": "You are a strict Keycloak operator. Use only attached MCP tools and attached Keycloak skills. Never switch profile.",
                "goal": (
                    f"Execute the approved Keycloak ticket against profile '{profile}'. "
                    "Use normalized JSON and preflight output. Perform only explicit requested actions, verify exact targets before mutation, "
                    "skip ambiguous targets, and return markdown with Summary, Actions, Skipped, Verification, Errors."
                ),
                "instructions": "Preflight first, execute through Keycloak MCP only, verify after each mutation, do not guess.",
                "expected_output": "Markdown execution report with per-target results.",
                "on_failure": "abort",
            },
            1300,
            80,
        ),
        _node(
            "verify_keycloak_state",
            "agent/react",
            "Verify Keycloak State",
            {
                **agent_common,
                "max_iterations": 18,
                "allowed_tools": [*KEYCLOAK_IDENTITY_VERIFY_TOOLS, *KEYCLOAK_PLATFORM_VERIFY_TOOLS],
                "system_prompt": "Read-only Keycloak verifier. Use attached MCP tools only.",
                "goal": "Verify the final Keycloak state claimed by execute_keycloak_task_output. Do not mutate anything.",
                "instructions": "Use read-only MCP tools and produce Verified, Not Verified, Skipped, Errors.",
                "expected_output": "Markdown verification report.",
            },
            1560,
            80,
        ),
        _node("report_gate", "logic/merge", "Report Gate", {"mode": "any"}, 1820, 80),
        _node(
            "telegram_report",
            "output/telegram",
            "Telegram Report",
            {
                "message": (
                    "Keycloak request report\nTicket: {ticket_id}\nRequester: {requester}\n\n"
                    "Execution:\n{execute_keycloak_task_output}\n\nVerification:\n{verify_keycloak_state_output}"
                ),
            },
            2080,
            80,
        ),
    ]
    edges = [
        _edge("start_webhook", "entry_join"),
        _edge("start_manual", "entry_join"),
        _edge("entry_join", "environment_preflight"),
        _edge("environment_preflight", "normalize_request", "success"),
        _edge("normalize_request", "await_approval", "success"),
        _edge("await_approval", "execute_keycloak_task", "approved"),
        _edge("await_approval", "report_gate", "rejected"),
        _edge("await_approval", "report_gate", "timeout"),
        _edge("execute_keycloak_task", "verify_keycloak_state", "success"),
        _edge("execute_keycloak_task", "report_gate", "error"),
        _edge("verify_keycloak_state", "report_gate", "success"),
        _edge("verify_keycloak_state", "report_gate", "error"),
        _edge("report_gate", "telegram_report"),
    ]
    return {
        "reply": "LLM provider is unavailable, so I generated a resource-aware Keycloak MCP draft locally.",
        "requirements": [user_message],
        "assumptions": ["Service-desk Keycloak requests arrive by webhook or manual run.", "Mutating Keycloak changes require human approval before execution."],
        "questions": [] if mcp_id else ["Connect a Keycloak Admin MCP server before applying this draft."],
        "resource_plan": {"servers": [], "agents": [], "mcp_servers": [mcp] if mcp else [], "skills": skills, "missing": missing, "notes": resource_notes},
        "target_node_id": None,
        "node_patch": {},
        "graph_patch": {"anchor_node_id": None, "nodes": nodes, "edges": edges, "update_nodes": [], "remove_node_ids": remove_node_ids, "remove_edge_ids": []},
        "node_explanations": {
            "environment_preflight": "Calls Keycloak MCP first, so the workflow knows the active profile/environment.",
            "execute_keycloak_task": "Runs the approved IAM task through attached Keycloak MCP and skills.",
            "telegram_report": "Sends the execution and verification report to Telegram.",
        },
        "confidence": 0.72 if mcp_id else 0.48,
        "warnings": [f"LLM provider fallback was used. Reason: {fallback_reason[:500]}"],
        "patch_summary": "Keycloak MCP ticket workflow with approval and Telegram reporting",
        "suggested_next_actions": ["Review selected Keycloak MCP/skills", "Set Telegram bot/chat defaults if needed", "Apply the draft"],
    }
