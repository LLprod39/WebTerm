from __future__ import annotations

from django.utils import timezone

from app.agent_kernel.domain.roles import ROLE_SPECS
from servers.models import ServerAgent, ServerWatcherDraft

ROLE_TO_AGENT_TYPE = {
    "deploy_operator": ServerAgent.TYPE_DEPLOY_WATCHER,
    "infra_scout": ServerAgent.TYPE_INFRA_SCOUT,
    "log_investigator": ServerAgent.TYPE_LOG_INVESTIGATOR,
    "security_patrol": ServerAgent.TYPE_SECURITY_PATROL,
}


def _build_goal(draft: ServerWatcherDraft) -> str:
    role_slug = str(draft.recommended_role or "custom").strip() or "custom"
    signals = "\n".join(f"- {item}" for item in list(draft.reasons or [])[:6]) or "- No signals recorded"
    memory_items = "\n".join(f"- {item}" for item in list(draft.memory_excerpt or [])[:6]) or "- No memory context available"
    return (
        f"[ROLE={role_slug}]\n"
        f"{draft.objective}\n\n"
        f"Сигналы watcher:\n{signals}\n\n"
        f"Память по серверу:\n{memory_items}\n\n"
        "Действуй как DevOps/SRE-оператор, начинай с плана, подтверждай факты, не объявляй успех без verification."
    )


def _build_system_prompt(role_slug: str) -> str:
    role_spec = ROLE_SPECS.get(role_slug, ROLE_SPECS["custom"])
    return f"{role_spec.system_hint}\n\nПравила верификации:\n" + "\n".join(
        f"- {item}" for item in role_spec.verification_rules
    )


def ensure_watcher_agent(*, user, draft: ServerWatcherDraft) -> ServerAgent:
    role_slug = str(draft.recommended_role or "custom").strip() or "custom"
    role_spec = ROLE_SPECS.get(role_slug, ROLE_SPECS["custom"])
    agent_type = ROLE_TO_AGENT_TYPE.get(role_slug, ServerAgent.TYPE_CUSTOM)
    agent_name = f"Watcher · {draft.server.name} · {role_spec.title}"

    agent, _created = ServerAgent.objects.get_or_create(
        user=user,
        name=agent_name,
        defaults={
            "mode": ServerAgent.MODE_FULL,
            "agent_type": agent_type,
            "goal": _build_goal(draft),
            "ai_prompt": draft.objective,
            "system_prompt": _build_system_prompt(role_slug),
            "max_iterations": 10,
            "allow_multi_server": False,
            "tools_config": {},
            "stop_conditions": [],
            "session_timeout_seconds": 900,
            "max_connections": 1,
            "schedule_minutes": 0,
            "is_enabled": False,
        },
    )

    agent.mode = ServerAgent.MODE_FULL
    agent.agent_type = agent_type
    agent.goal = _build_goal(draft)
    agent.ai_prompt = draft.objective
    agent.system_prompt = _build_system_prompt(role_slug)
    agent.max_iterations = max(agent.max_iterations or 0, 10)
    agent.allow_multi_server = False
    agent.session_timeout_seconds = max(agent.session_timeout_seconds or 0, 900)
    agent.max_connections = 1
    agent.is_enabled = False
    agent.save()
    agent.servers.set([draft.server])
    return agent


def mark_watcher_draft_launched(*, draft: ServerWatcherDraft, user, agent: ServerAgent, run) -> None:
    metadata = dict(draft.metadata or {})
    metadata["last_launch_run_id"] = run.id
    metadata["last_launch_agent_id"] = agent.id
    metadata["last_launched_at"] = timezone.now().isoformat()
    metadata["launch_count"] = int(metadata.get("launch_count") or 0) + 1
    draft.metadata = metadata
    draft.status = ServerWatcherDraft.STATUS_ACKNOWLEDGED
    if draft.acknowledged_at is None:
        draft.acknowledged_at = timezone.now()
    draft.acknowledged_by = user
    draft.save(update_fields=["metadata", "status", "acknowledged_at", "acknowledged_by"])
