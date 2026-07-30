"""Assistant actions for the servers app: agents, runs, server overview.

F-08a: the action handlers live in ``assistant_actions_agents`` (list/create)
and ``assistant_actions_runs`` (run control + overview). This module keeps the
runtime-context provider, the registration entry point and the public API.
"""

from __future__ import annotations

from app.assistant_actions import (
    AssistantActionSpec,
    register_action,
    register_runtime_context_provider,
)
from app.runtime_limits import ACTIVE_AGENT_RUN_STATUSES
from core_ui.access import feature_allowed_for_user
from core_ui.projects import active_project_for_user
from servers.assistant_actions_agents import create_agent, list_agents
from servers.assistant_actions_runs import (
    agent_report,
    approve_agent_plan,
    reply_to_agent,
    run_agent,
    server_overview,
    stop_agent,
)
from servers.models import AgentRun, ServerAgent
from servers.views.server_helpers import _accessible_servers_queryset

__all__ = [
    "agent_report",
    "approve_agent_plan",
    "build_assistant_runtime_context",
    "create_agent",
    "list_agents",
    "register_assistant_actions",
    "reply_to_agent",
    "run_agent",
    "server_overview",
    "stop_agent",
]


def build_assistant_runtime_context(user) -> dict:
    context: dict = {"agents": [], "servers": []}
    if feature_allowed_for_user(user, "agents"):
        agents = list(
            ServerAgent.objects.filter(user=user, project=active_project_for_user(user))
            .prefetch_related("servers")
            .order_by("-updated_at", "-id")[:30]
        )
        active_runs = {}
        for run in AgentRun.objects.filter(agent__in=agents, status__in=ACTIVE_AGENT_RUN_STATUSES).order_by(
            "agent_id", "-started_at", "-id"
        ):
            active_runs.setdefault(run.agent_id, run)
        context["agents"] = [
            {
                "id": agent.id,
                "name": agent.name,
                "mode": agent.mode,
                "agent_type": agent.agent_type,
                "goal": (agent.goal or agent.ai_prompt or "")[:500],
                "server_ids": list(agent.servers.values_list("id", flat=True)[:8]),
                "server_names": list(agent.servers.values_list("name", flat=True)[:8]),
                "is_enabled": bool(agent.is_enabled),
                "active_run_id": active_runs[agent.id].id if agent.id in active_runs else None,
                "active_run_status": active_runs[agent.id].status if agent.id in active_runs else "",
            }
            for agent in agents
        ]

    if feature_allowed_for_user(user, "servers"):
        servers = list(_accessible_servers_queryset(user).order_by("-updated_at", "-id")[:30])
        context["servers"] = [
            {
                "id": server.id,
                "name": server.name,
                "host": server.host,
                "username": server.username,
                "server_type": server.server_type,
                "is_active": bool(server.is_active),
                "detected_os": server.detected_os,
            }
            for server in servers
        ]
    return context


def register_assistant_actions() -> None:
    register_runtime_context_provider("servers", build_assistant_runtime_context)
    specs = [
        AssistantActionSpec(
            action_type="agents.list",
            label="List agents",
            description="List configured agents and runtime overview.",
            required_feature="agents",
            risk="read",
            handler=list_agents,
        ),
        AssistantActionSpec(
            action_type="agent.create",
            label="Create agent",
            description=(
                "Create a custom agent from scratch (no templates). Pass name, mode=full, goal, "
                "system_prompt (detailed), ai_prompt, optional server_ids. Backend scaffolds missing "
                "text and auto-picks servers when omitted."
            ),
            required_feature="agents",
            risk="internal_write",
            requires_confirmation=True,
            input_schema={
                "required": ["mode", "goal", "system_prompt"],
                "properties": {
                    "name": {"type": "string", "description": "Human title in Russian, e.g. «Деплой из Git в Docker»"},
                    "mode": {"type": "string", "enum": ["mini", "full", "multi"]},
                    "goal": {
                        "type": "string",
                        "description": (
                            "One sentence: what the agent accomplishes, on what target, and the success "
                            "criterion. E.g. «Развернуть приложение из Git-репозитория в Docker на сервере "
                            "и убедиться, что контейнер здоров»."
                        ),
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": (
                            "The agent's operating manual — this is what it actually follows, so make it "
                            "concrete (5+ sentences): numbered steps to reach the goal, which commands/tools "
                            "to run and in what order, how to verify each step, when to ask_user (missing "
                            "creds / ambiguous choice), what the final report must contain, and safety rules "
                            "(no destructive commands without need, never print secrets). Runtime inputs like "
                            "a repo URL are given at run time — do NOT hardcode or ask for them here."
                        ),
                    },
                    "ai_prompt": {
                        "type": "string",
                        "description": "Short 1-2 sentence runtime directive restating the goal.",
                    },
                    "description": {"type": "string", "description": "User task if goal not expanded yet"},
                    "server_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional; auto from pin/@/sole server",
                    },
                },
            },
            handler=create_agent,
        ),
        AssistantActionSpec(
            action_type="agent.run",
            label="Run agent",
            description="Launch an existing agent.",
            required_feature="agents",
            risk="mutating",
            requires_confirmation=True,
            input_schema={"required": ["agent_id"]},
            handler=run_agent,
        ),
        AssistantActionSpec(
            action_type="agent.stop",
            label="Stop agent",
            description="Stop an active agent run.",
            required_feature="agents",
            risk="mutating",
            requires_confirmation=True,
            input_schema={"required": ["agent_id"]},
            handler=stop_agent,
        ),
        AssistantActionSpec(
            action_type="agent.reply",
            label="Reply to agent",
            description="Reply to a waiting agent run.",
            required_feature="agents",
            risk="mutating",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "run_id": {"type": "integer"},
                    "agent_id": {"type": "integer"},
                    "answer": {"type": "string"},
                },
                "required": ["run_id", "answer"],
            },
            handler=reply_to_agent,
        ),
        AssistantActionSpec(
            action_type="agent.approve_plan",
            label="Approve agent plan",
            description=(
                "Approve a multi-agent plan review and start plan execution. "
                "Pass run_id from agent.run (integer). agent_id is accepted as fallback "
                "when the run is in plan_review."
            ),
            required_feature="agents",
            risk="mutating",
            requires_confirmation=True,
            input_schema={
                "type": "object",
                "properties": {
                    "run_id": {"type": "integer", "description": "AgentRun id awaiting plan approval"},
                    "agent_id": {"type": "integer", "description": "Fallback: resolve latest plan_review run"},
                },
                "required": ["run_id"],
            },
            handler=approve_agent_plan,
        ),
        AssistantActionSpec(
            action_type="agent.report",
            label="Get agent report",
            description="Read the canonical report for an agent run.",
            required_feature="agents",
            risk="read",
            input_schema={
                "type": "object",
                "properties": {
                    "run_id": {"type": "integer"},
                    "agent_id": {"type": "integer"},
                },
                "required": ["run_id"],
            },
            handler=agent_report,
        ),
        AssistantActionSpec(
            action_type="server.diagnostics.overview",
            label="Server overview",
            description="Run the read-only Linux UI overview for an accessible SSH server.",
            required_feature="servers",
            risk="read",
            input_schema={"required": ["server_id"]},
            handler=server_overview,
        ),
    ]
    for spec in specs:
        register_action(spec)
