from __future__ import annotations

import re
from typing import Any

from studio.services.pipeline_assistant_interview import augment_response_with_interview_questions
from studio.services.pipeline_template_recommendations import (
    build_template_graph_patch,
    build_template_resource_plan,
    get_pilot_pipeline_template,
    recommend_pilot_pipeline_templates,
)

STRUCTURED_RESPONSE_KEYS = {
    "reply",
    "requirements",
    "assumptions",
    "questions",
    "resource_plan",
    "target_node_id",
    "node_patch",
    "graph_patch",
    "node_explanations",
    "confidence",
    "warnings",
    "patch_summary",
    "suggested_next_actions",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def is_provider_error_response(raw_text: str, parsed: dict[str, Any] | None = None) -> bool:
    text = _text(raw_text)
    lowered = text.lower()
    if lowered.startswith("error from ") and " api:" in lowered:
        return True
    if lowered.startswith("llm error:"):
        return True
    return bool(parsed and "error" in parsed and not any(key in parsed for key in STRUCTURED_RESPONSE_KEYS))


def provider_error_summary(raw_text: str, parsed: dict[str, Any] | None = None) -> str:
    if parsed and parsed.get("error"):
        return f"LLM provider error: {_text(parsed.get('error'))[:500]}"
    text = _text(raw_text).replace("\n", " ")
    return text[:700] or "LLM provider returned an empty error response."


def should_use_draft_fallback(
    *,
    assistant_context: dict[str, Any],
    known_node_types: dict[str, str] | None,
    user_message: str = "",
) -> bool:
    if assistant_context.get("draft_mode") is False:
        return False
    intent = str(assistant_context.get("intent") or "").lower()
    if intent not in {"create", "edit", ""}:
        return False
    if intent == "edit":
        return False
    return not any(_text(node_type) for node_type in (known_node_types or {}).values())


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    if not slug:
        return fallback
    if not re.match(r"^[a-z_]", slug):
        slug = f"{fallback}_{slug}"
    return slug[:48].strip("_") or fallback


def _choose_trigger(message: str) -> tuple[str, str, dict[str, Any]]:
    lowered = message.lower()
    if any(token in lowered for token in ("webhook", "payload", "telegram", "бот", "bot")):
        return (
            "trigger/webhook",
            "Webhook Trigger",
            {
                "label": "Webhook Trigger",
                "is_active": True,
                "webhook_payload_map": {"task": "task", "message": "message", "payload": "payload"},
            },
        )
    if any(token in lowered for token in ("monitoring", "alert", "алерт", "docker", "container", "контейнер")):
        return (
            "trigger/monitoring",
            "Monitoring Trigger",
            {
                "label": "Monitoring Trigger",
                "is_active": True,
                "monitoring_filters": {},
            },
        )
    if any(token in lowered for token in ("daily", "ежеднев", "schedule", "cron", "каждый день", "health-check")):
        return (
            "trigger/schedule",
            "Daily Schedule",
            {
                "label": "Daily Schedule",
                "is_active": True,
                "cron_expression": "0 9 * * *",
            },
        )
    return ("trigger/manual", "Manual Trigger", {"label": "Manual Trigger", "is_active": True})


def _choose_output(message: str) -> tuple[str, str, dict[str, Any]]:
    lowered = message.lower()
    if "telegram" in lowered or "телеграм" in lowered:
        return (
            "output/telegram",
            "Telegram Summary",
            {
                "label": "Telegram Summary",
                "message": "Automation result:\n{runbook_step_output}",
            },
        )
    if "email" in lowered or "почт" in lowered:
        return (
            "output/email",
            "Email Summary",
            {
                "label": "Email Summary",
                "subject": "WebTerm automation result",
                "body": "{runbook_step_output}",
            },
        )
    if "webhook" in lowered and any(token in lowered for token in ("send", "отправ", "callback", "result")):
        return (
            "output/webhook",
            "Webhook Callback",
            {
                "label": "Webhook Callback",
                "payload_template": {"summary": "{runbook_step_output}"},
            },
        )
    return (
        "output/report",
        "Runbook Report",
        {
            "label": "Runbook Report",
            "template": "## Automation result\n\n{runbook_step_output}",
        },
    )


def _needs_approval(message: str) -> bool:
    lowered = message.lower()
    return any(
        token in lowered
        for token in (
            "approval",
            "approve",
            "подтверж",
            "разреш",
            "восстанов",
            "restart",
            "remove",
            "delete",
            "безопасн",
        )
    )


def build_template_draft_response(
    *,
    user_message: str,
    assistant_context: dict[str, Any],
    fallback_reason: str,
) -> dict[str, Any] | None:
    recommendations = assistant_context.get("template_recommendations")
    if not isinstance(recommendations, list) or not recommendations:
        recommendations = recommend_pilot_pipeline_templates(
            user_message=user_message,
            pipeline_name=_text(assistant_context.get("pipeline_name")),
            limit=1,
        )
    first = recommendations[0] if recommendations and isinstance(recommendations[0], dict) else None
    template = get_pilot_pipeline_template(_text(first.get("slug")) if first else "")
    if template is None:
        return None

    pipeline_name = _text(assistant_context.get("pipeline_name")) or "Operations runbook"
    template_name = _text(template.get("name")) or _text(template.get("slug")) or "Pilot template"
    graph_patch = build_template_graph_patch(template, assistant_context=assistant_context)
    resource_plan = build_template_resource_plan(template, assistant_context=assistant_context)
    warning = (
        "LLM provider did not return a usable structured draft, so WebTerm generated a pilot template "
        f"skeleton locally. Reason: {fallback_reason[:500]}"
    )
    return augment_response_with_interview_questions(
        {
            "reply": (
                f"LLM provider is unavailable, so I used `{template_name}` as the skeleton for `{pipeline_name}`. "
                "Review MCP servers, arguments and approvals before applying."
            ),
            "selected_template": {
                "slug": _text(template.get("slug")),
                "name": template_name,
                "source": "pilot_template_fallback",
            },
            "template_recommendations": recommendations,
            "requirements": [user_message],
            "assumptions": [
                f"Pilot template selected: {template.get('slug')}.",
                "Template approval, verification and report branches were preserved.",
            ],
            "questions": [],
            "resource_plan": resource_plan,
            "target_node_id": None,
            "node_patch": {},
            "graph_patch": graph_patch,
            "node_explanations": {
                _text(node.get("ref")): "Step copied from the matched pilot template skeleton."
                for node in graph_patch.get("nodes", [])
                if isinstance(node, dict) and _text(node.get("ref"))
            },
            "confidence": 0.62,
            "warnings": [warning],
            "patch_summary": f"Pilot template skeleton: {template_name}",
            "suggested_next_actions": [
                "Review selected resources",
                "Fill service-specific arguments",
                "Apply the draft",
            ],
        }
    )


def build_deterministic_draft_response(
    *,
    user_message: str,
    assistant_context: dict[str, Any],
    fallback_reason: str,
) -> dict[str, Any]:
    message = _text(user_message) or "Build a safe operations automation."
    template_response = build_template_draft_response(
        user_message=message,
        assistant_context=assistant_context,
        fallback_reason=fallback_reason,
    )
    if template_response is not None:
        return template_response
    pipeline_name = _text(assistant_context.get("pipeline_name")) or "Operations runbook"
    trigger_type, trigger_label, trigger_data = _choose_trigger(message)
    output_type, output_label, output_data = _choose_output(message)
    approval_required = _needs_approval(message)

    trigger_ref = _slug(trigger_label, "start")
    runbook_ref = "runbook_step"
    output_ref = _slug(output_label, "summary")
    nodes = [
        {
            "ref": trigger_ref,
            "type": trigger_type,
            "label": trigger_label,
            "data": trigger_data,
            "x_offset": 0,
            "y_offset": 0,
        },
        {
            "ref": runbook_ref,
            "type": "agent/react",
            "label": "AI Runbook Step",
            "data": {
                "label": "AI Runbook Step",
                "goal": (
                    f"Execute this WebTerm automation safely: {message[:900]}. "
                    "Prefer read-only diagnostics first and clearly report missing resources."
                ),
                "system_prompt": (
                    "You are a careful WebTerm DevOps agent. Use configured resources only, "
                    "avoid destructive operations without explicit approval, and keep an audit-friendly summary."
                ),
                "instructions": (
                    "1. Read trigger payload and prior context.\n"
                    "2. Identify the target task and required resources.\n"
                    "3. Run safe diagnostics first.\n"
                    "4. If a mutating action is needed, stop unless approval is present.\n"
                    "5. Return evidence, result, and next action."
                ),
                "expected_output": "Short markdown summary with status, evidence, risks, and next action.",
            },
            "x_offset": 280,
            "y_offset": 0,
        },
    ]
    edges = [{"source": trigger_ref, "target": runbook_ref, "source_handle": "out"}]

    final_source = runbook_ref
    if approval_required:
        approval_ref = "operator_approval"
        nodes.append(
            {
                "ref": approval_ref,
                "type": "logic/human_approval",
                "label": "Operator Approval",
                "data": {
                    "label": "Operator Approval",
                    "prompt": "Approve the remediation/action step after reviewing diagnostics.",
                    "timeout_minutes": 30,
                },
                "x_offset": 560,
                "y_offset": 0,
            }
        )
        edges.append({"source": runbook_ref, "target": approval_ref, "source_handle": "success"})
        final_source = approval_ref

    nodes.append(
        {
            "ref": output_ref,
            "type": output_type,
            "label": output_label,
            "data": output_data,
            "x_offset": 840 if approval_required else 560,
            "y_offset": 0,
        }
    )
    edges.append(
        {
            "source": final_source,
            "target": output_ref,
            "source_handle": "approved" if approval_required else "success",
        }
    )

    warning = (
        "LLM provider did not return a usable structured draft, so WebTerm generated a safe starter DAG locally. "
        f"Reason: {fallback_reason[:500]}"
    )
    return augment_response_with_interview_questions(
        {
            "reply": (
                f"LLM provider is unavailable, so I generated a safe starter DAG for `{pipeline_name}` locally. "
                "Review resources and prompts before applying."
            ),
            "requirements": [message],
            "assumptions": [
                "Fallback mode uses a conservative trigger, one AI runbook step, and a final summary output.",
                "No server, MCP, or skill resource is attached automatically.",
            ],
            "questions": [],
            "resource_plan": {
                "servers": [],
                "agents": [],
                "mcp_servers": [],
                "skills": [],
                "missing": [],
                "notes": ["Attach concrete servers, MCP tools, or skills after reviewing the draft."],
                "available": {
                    "servers": assistant_context.get("available_servers") or [],
                    "agents": assistant_context.get("available_agents") or [],
                    "mcp_servers": assistant_context.get("available_mcp_servers") or [],
                    "skills": assistant_context.get("available_skills") or [],
                },
            },
            "target_node_id": None,
            "node_patch": {},
            "graph_patch": {
                "anchor_node_id": None,
                "nodes": nodes,
                "edges": edges,
                "update_nodes": [],
                "remove_node_ids": [],
                "remove_edge_ids": [],
            },
            "node_explanations": {
                trigger_ref: "Entry point selected from the automation request.",
                runbook_ref: "Safe AI runbook step with diagnostics-first instructions.",
                output_ref: "Final summary output for the operator.",
            },
            "confidence": 0.45,
            "warnings": [warning],
            "patch_summary": "Local fallback starter DAG",
            "suggested_next_actions": ["Review generated node prompts", "Attach required resources", "Apply the draft"],
        }
    )


def build_provider_free_draft_response(
    *,
    user_message: str,
    assistant_context: dict[str, Any],
) -> dict[str, Any]:
    response = build_template_draft_response(
        user_message=user_message,
        assistant_context=assistant_context,
        fallback_reason="Provider-free deterministic compiler requested.",
    ) or build_deterministic_draft_response(
        user_message=user_message,
        assistant_context=assistant_context,
        fallback_reason="Provider-free deterministic compiler requested.",
    )
    selected_template = (
        response.get("selected_template") if isinstance(response.get("selected_template"), dict) else None
    )
    template_name = _text(selected_template.get("name")) if selected_template else ""
    pipeline_name = _text(assistant_context.get("pipeline_name")) or "Operations runbook"
    if selected_template:
        response["selected_template"] = {
            **selected_template,
            "source": "pilot_template_compiler",
        }
    response["reply"] = (
        f"Used local deterministic compiler for `{pipeline_name}`"
        + (f" with `{template_name}`." if template_name else ".")
        + " No LLM provider was called; review resources, arguments and approvals before applying."
    )
    response["warnings"] = ["Generated by local deterministic compiler without calling an LLM provider."]
    response["confidence"] = max(float(response.get("confidence") or 0), 0.72)
    return augment_response_with_interview_questions(response)


def handle_unusable_llm_response(
    *,
    raw_text: str,
    parsed: dict[str, Any],
    user_message: str,
    assistant_context: dict[str, Any],
    known_node_types: dict[str, str] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    provider_error = is_provider_error_response(raw_text, parsed)
    if parsed and not provider_error:
        return None, None

    if provider_error:
        reason = provider_error_summary(raw_text, parsed)
    else:
        reason = "LLM provider returned unstructured output."

    if should_use_draft_fallback(
        assistant_context=assistant_context,
        known_node_types=known_node_types,
        user_message=user_message,
    ):
        return (
            build_deterministic_draft_response(
                user_message=user_message,
                assistant_context=assistant_context,
                fallback_reason=reason,
            ),
            None,
        )
    return None, reason if provider_error else None
